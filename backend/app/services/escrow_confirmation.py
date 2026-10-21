"""Authentic escrow receipt validation at the chain/HTTP seam."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from app.models import ChainTransaction, Job, User
from app.services.blockchain_service import BlockchainBackend, decode_receipt_logs, read_contract_job
from app.services.chain_outbox import get_chain_instance_id


class EscrowReceiptError(ValueError):
    """A transaction cannot establish escrow for the requested job."""

    def __init__(self, message: str, *, terminal: bool = True) -> None:
        super().__init__(message)
        self.terminal = terminal


def _hex(value) -> str:
    if isinstance(value, bytes):
        return "0x" + value.hex()
    text = str(value)
    return text if text.startswith("0x") else "0x" + text


async def confirm_escrow_receipt(
    db: AsyncSession,
    *,
    blockchain: BlockchainBackend,
    job: Job,
    authenticated_wallet: str,
    tx_hash: str,
    expected_chain_id: int,
    expected_contract: str,
    confirmations_required: int,
) -> Job:
    """Validate a mined JobCreated receipt and project it exactly once."""
    normalized_hash = _hex(tx_hash).lower()
    if job.status == "queued" and (job.blockchain_tx_hash or "").lower() == normalized_hash:
        return job
    if job.status != "pending_blockchain":
        raise EscrowReceiptError(f"Job status is {job.status}, expected pending_blockchain")
    if blockchain.get_chain_id() != expected_chain_id:
        raise EscrowReceiptError("configured chain ID does not match RPC chain", terminal=False)

    # End the request's implicit read transaction before all RPC calls.
    await db.commit()
    transaction = blockchain.get_transaction(normalized_hash)
    receipt = blockchain.get_transaction_receipt(normalized_hash)
    if transaction is None:
        raise EscrowReceiptError("transaction is not known by the configured chain", terminal=False)
    if transaction.get("chainId") is not None and int(transaction["chainId"]) != expected_chain_id:
        raise EscrowReceiptError("transaction chain ID does not match configured chain")

    sender = Web3.to_checksum_address(transaction["from"])
    target = Web3.to_checksum_address(transaction["to"])
    contract = Web3.to_checksum_address(expected_contract)
    if sender.lower() != authenticated_wallet.lower():
        raise EscrowReceiptError("transaction sender does not match authenticated wallet")
    if target.lower() != contract.lower():
        raise EscrowReceiptError("transaction target does not match configured contract")
    chain_instance_id = get_chain_instance_id(blockchain)

    prior = await db.execute(
        select(ChainTransaction.id).where(
            ChainTransaction.chain_id == expected_chain_id,
            ChainTransaction.chain_instance_id == chain_instance_id,
            ChainTransaction.contract_address == contract,
            ChainTransaction.tx_hash == normalized_hash,
            ChainTransaction.job_id != job.id,
        )
    )
    if prior.scalar_one_or_none():
        raise EscrowReceiptError("transaction hash already confirmed another job")

    own_intent = (
        await db.execute(
            select(ChainTransaction).where(
                ChainTransaction.job_id == job.id,
                ChainTransaction.tx_type == "createJob",
                ChainTransaction.chain_id == expected_chain_id,
                ChainTransaction.chain_instance_id == chain_instance_id,
                ChainTransaction.contract_address == contract,
            )
        )
    ).scalar_one_or_none()
    if own_intent and own_intent.tx_hash and own_intent.tx_hash.lower() != normalized_hash:
        raise EscrowReceiptError("a different escrow transaction is already registered for this job")
    if own_intent is None:
        own_intent = ChainTransaction(
            id=uuid.uuid4(),
            chain_id=expected_chain_id,
            chain_instance_id=chain_instance_id,
            contract_address=contract,
            job_id=job.id,
            tx_hash=normalized_hash,
            tx_type="createJob",
            from_address=sender,
            to_address=target,
            idempotency_key=f"createJob:{job.id}",
            status="submitted",
        )
        db.add(own_intent)
    job.blockchain_tx_hash = normalized_hash
    await db.flush()

    # A known transaction without a receipt remains durably pending. The
    # receipt-confirmation runner will resume it after mining/restart.
    if receipt is None:
        return job
    if int(receipt.get("status", 0)) != 1:
        own_intent.status = "reverted"
        await db.commit()
        raise EscrowReceiptError("transaction reverted")
    receipt_block = int(receipt["blockNumber"])
    confirmations = blockchain.get_block_number() - receipt_block + 1
    if confirmations < confirmations_required:
        return job

    events = decode_receipt_logs(receipt, blockchain.get_abi())
    matching = [
        event for event in events if event["event"] == "JobCreated" and event["address"].lower() == contract.lower()
    ]
    if len(matching) != 1:
        raise EscrowReceiptError("receipt must contain one JobCreated event from configured contract")
    args = matching[0]["args"]
    if _hex(args["jobId"]).lower() != job.chain_job_id.lower():
        raise EscrowReceiptError("JobCreated job ID does not match database UUID")
    if (
        _hex(args["fingerprint"]).removeprefix("0x").lower()
        != (job.expected_fingerprint or "").removeprefix("0x").lower()
    ):
        raise EscrowReceiptError("JobCreated fingerprint does not match backend fingerprint")
    amount = int(args["amount"])
    if amount != int(job.price_base_units):
        raise EscrowReceiptError("JobCreated amount does not match model price")
    created_at = int(args["timestamp"])
    chain_job = read_contract_job(
        blockchain,
        contract,
        bytes.fromhex(job.chain_job_id.removeprefix("0x")),
    )
    if str(chain_job["user"]).lower() != authenticated_wallet.lower():
        raise EscrowReceiptError("on-chain job owner does not match authenticated wallet")
    if bytes(chain_job["fingerprint"]) != bytes.fromhex((job.expected_fingerprint or "").removeprefix("0x")):
        raise EscrowReceiptError("on-chain job fingerprint does not match backend fingerprint")
    if int(chain_job["amount"]) != amount or int(chain_job["state"]) != 1:
        raise EscrowReceiptError("on-chain job state or amount is inconsistent with JobCreated")
    if int(chain_job["created_at"]) != created_at:
        raise EscrowReceiptError("on-chain job creation time is inconsistent with JobCreated")
    deadline = datetime.fromtimestamp(int(chain_job["job_deadline"]), timezone.utc)
    if deadline <= datetime.fromtimestamp(created_at, timezone.utc):
        raise EscrowReceiptError("invalid on-chain deadline")
    block_hash = _hex(receipt["blockHash"])
    own_intent.amount_base_units = amount
    own_intent.block_number = receipt_block
    own_intent.block_hash = block_hash
    own_intent.status = "confirmed"
    own_intent.error = None
    job.status = "queued"
    job.blockchain_tx_hash = normalized_hash
    job.blockchain_escrow_amount = amount
    job.deadline = deadline
    await db.flush()
    return job


class ReceiptConfirmer:
    """Bounded restart-safe confirmer for registered createJob transactions."""

    def __init__(
        self,
        *,
        blockchain: BlockchainBackend,
        chain_id: int,
        contract_address: str,
        confirmations_required: int,
        batch_size: int = 25,
    ) -> None:
        self.blockchain = blockchain
        self.chain_id = chain_id
        self.contract_address = Web3.to_checksum_address(contract_address)
        self.confirmations_required = confirmations_required
        self.batch_size = batch_size

    async def run_once(self, db: AsyncSession) -> dict[str, int]:
        await db.commit()
        chain_instance_id = get_chain_instance_id(self.blockchain)
        rows = await db.execute(
            select(ChainTransaction.id)
            .where(
                ChainTransaction.tx_type == "createJob",
                ChainTransaction.status == "submitted",
                ChainTransaction.chain_id == self.chain_id,
                ChainTransaction.chain_instance_id == chain_instance_id,
                ChainTransaction.contract_address == self.contract_address,
            )
            .order_by(ChainTransaction.created_at)
            .limit(self.batch_size)
        )
        intent_ids = list(rows.scalars().all())
        await db.commit()
        confirmed = 0
        pending = 0
        rejected = 0
        for intent_id in intent_ids:
            intent = (
                await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id))
            ).scalar_one_or_none()
            if intent is None or intent.status != "submitted" or not intent.tx_hash or not intent.job_id:
                await db.commit()
                continue
            job = (await db.execute(select(Job).where(Job.id == intent.job_id))).scalar_one()
            user = (await db.execute(select(User).where(User.id == job.user_id))).scalar_one()
            try:
                await confirm_escrow_receipt(
                    db,
                    blockchain=self.blockchain,
                    job=job,
                    authenticated_wallet=user.wallet_address,
                    tx_hash=intent.tx_hash,
                    expected_chain_id=self.chain_id,
                    expected_contract=self.contract_address,
                    confirmations_required=self.confirmations_required,
                )
            except EscrowReceiptError as exc:
                intent.error = type(exc).__name__
                if exc.terminal:
                    # Stop retrying a conclusively invalid mined transaction,
                    # while recording no receipt contents or wallet data.
                    intent.status = "reverted"
                    rejected += 1
                else:
                    # RPC visibility and configuration failures are retryable;
                    # preserve the submitted intent for a later runner cycle.
                    pending += 1
            else:
                if job.status == "queued":
                    confirmed += 1
                else:
                    pending += 1
            await db.commit()
        return {"confirmed": confirmed, "pending": pending, "rejected": rejected}
