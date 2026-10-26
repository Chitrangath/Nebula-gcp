"""Restart-safe proof verification and on-chain settlement coordinator."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChainTransaction, Job, JobAttempt, Lease, Proof
from app.services.blockchain_events import EventPoller
from app.services.blockchain_service import (
    BlockchainBackend,
    build_submit_proof_tx,
    build_verify_job_tx,
    decode_receipt_logs,
    read_contract_job,
)
from app.services.chain_outbox import get_chain_instance_id, prepare_and_broadcast, rebroadcast_prepared
from app.services.proof_verifier import Verdict, verify_proof
from app.services.retry_policy import apply_attempt_failure
from app.services.storage import StorageBackend
from app.services.tx_signer import TransactionSigner


class SettlementCoordinator:
    """Moves persisted proof work through verification and two chain intents."""

    def __init__(
        self,
        *,
        blockchain: BlockchainBackend,
        signer: TransactionSigner,
        storage: StorageBackend,
        contract_address: str,
        chain_id: int,
        batch_size: int = 25,
        claim_ttl_seconds: int = 300,
        deployment_block: int = 0,
        confirmations: int = 1,
        finality: int = 10,
    ):
        self.blockchain = blockchain
        self.signer = signer
        self.storage = storage
        self.contract_address = contract_address
        self.chain_id = chain_id
        self.batch_size = batch_size
        self.claim_ttl_seconds = claim_ttl_seconds
        self.event_poller = EventPoller(
            blockchain=blockchain, chain_id=chain_id, contract_address=contract_address,
            deployment_block=deployment_block, confirmations=confirmations, finality=finality,
        )

    async def run_once(self, db: AsyncSession) -> dict[str, int]:
        verified = await self._verify_queued(db)
        await db.commit()  # all intents exist durably before any broadcast
        submitted = await self._broadcast_pending(db)
        await db.commit()
        confirmed = await self._confirm_submitted(db)
        await db.commit()
        # Confirmation may create verifyJob intents; broadcast and confirm them.
        submitted += await self._broadcast_pending(db)
        await db.commit()
        confirmed += await self._confirm_submitted(db)
        await db.commit()
        return {"verified": verified, "broadcast": submitted, "confirmed": confirmed}

    async def _verify_queued(self, db: AsyncSession) -> int:
        await db.commit()
        chain_instance_id = get_chain_instance_id(self.blockchain)
        stale_before = datetime.now(timezone.utc) - timedelta(seconds=self.claim_ttl_seconds)
        query = await db.execute(
            select(Proof.id)
            .join(JobAttempt, Proof.job_attempt_id == JobAttempt.id)
            .join(Job, JobAttempt.job_id == Job.id)
            .where(
                Proof.valid.is_(None),
                or_(
                    Proof.verification_status == "queued",
                    (Proof.verification_status == "processing") & (Proof.verification_started_at < stale_before),
                ),
                Job.status == "verifying",
                Job.chain_transactions.any(
                    (ChainTransaction.tx_type == "createJob")
                    & (ChainTransaction.chain_id == self.chain_id)
                    & (ChainTransaction.contract_address == self.contract_address)
                    & (ChainTransaction.chain_instance_id == chain_instance_id)
                ),
            )
            .order_by(Proof.created_at)
            .limit(self.batch_size)
            .with_for_update(of=Proof, skip_locked=True)
        )
        proof_ids = list(query.scalars().all())
        for proof_id in proof_ids:
            proof = (await db.execute(select(Proof).where(Proof.id == proof_id))).scalar_one()
            proof.verification_status = "processing"
            proof.verification_started_at = datetime.now(timezone.utc)
        # Release claims before object I/O. Other coordinators observe
        # `processing`; a crashed claim becomes eligible after the TTL.
        await db.commit()
        count = 0
        for proof_id in proof_ids:
            proof = (await db.execute(select(Proof).where(Proof.id == proof_id))).scalar_one()
            attempt = (await db.execute(select(JobAttempt).where(JobAttempt.id == proof.job_attempt_id))).scalar_one()
            job = (await db.execute(select(Job).where(Job.id == attempt.job_id))).scalar_one()
            lease = (await db.execute(select(Lease).where(Lease.id == attempt.lease_id))).scalar_one()
            if not proof.envelope or not job.result_file_key:
                proof.valid = False
                proof.verification_status = "verified"
                proof.verification_error = "Incomplete queued proof"
                proof.verified_at = datetime.now(timezone.utc)
                await apply_attempt_failure(db, lease, reason=proof.verification_error)
                count += 1
                await db.commit()
                continue
            # Object I/O occurs before the verifier takes its PostgreSQL row lock.
            await db.commit()
            try:
                result_bytes = await self.storage.get_object(job.result_file_key)
            except (KeyError, FileNotFoundError):
                proof = (await db.execute(select(Proof).where(Proof.id == proof_id).with_for_update())).scalar_one()
                proof.valid = False
                proof.verification_status = "verified"
                proof.verification_error = "Result object not found"
                proof.verified_at = datetime.now(timezone.utc)
                lease = (await db.execute(select(Lease).where(Lease.id == attempt.lease_id))).scalar_one()
                await apply_attempt_failure(db, lease, reason=proof.verification_error)
                count += 1
                await db.commit()
                continue
            proof = (await db.execute(select(Proof).where(Proof.id == proof_id).with_for_update())).scalar_one()
            if proof.verification_status != "processing" or proof.valid is not None:
                await db.commit()
                continue
            attempt = (await db.execute(select(JobAttempt).where(JobAttempt.id == proof.job_attempt_id))).scalar_one()
            job = (await db.execute(select(Job).where(Job.id == attempt.job_id))).scalar_one()
            lease = (await db.execute(select(Lease).where(Lease.id == attempt.lease_id))).scalar_one()
            envelope = proof.envelope
            result = await verify_proof(
                db,
                job_id=str(job.id),
                attempt_id=str(attempt.id),
                lease_id=str(lease.id),
                fingerprint_hex=proof.fingerprint_hash,
                merkle_root_hex=proof.merkle_root,
                output_hash_hex=proof.output_hash,
                merkle_proof=[],
                trace_hashes=[bytes.fromhex(value.removeprefix("0x")) for value in proof.trace_hashes or []],
                checkpoint_names=envelope["checkpoint_names"],
                signature_bytes=bytes.fromhex(proof.signature.removeprefix("0x")),
                signer_address=proof.signer_address,
                proof_timestamp=int(proof.proof_timestamp.replace(tzinfo=timezone.utc).timestamp()),
                protocol_version=proof.protocol_version,
                chain_id=int(envelope["chain_id"]),
                contract_address=envelope["verifying_contract"],
                model_id=job.model_id,
                queued_proof_id=str(proof.id),
                canonical_result_bytes=result_bytes,
            )
            proof.valid = result.verdict == Verdict.VALID
            proof.verification_status = "verified"
            proof.verification_error = result.error
            proof.verified_at = datetime.now(timezone.utc)
            attempt.fingerprint_hash = proof.fingerprint_hash
            attempt.merkle_root = proof.merkle_root
            attempt.output_hash = proof.output_hash
            attempt.signature = proof.signature
            intent_key = f"submitProof:{attempt.id}"
            prior = await db.execute(select(ChainTransaction).where(ChainTransaction.idempotency_key == intent_key))
            if prior.scalar_one_or_none() is None:
                db.add(
                    ChainTransaction(
                        id=uuid.uuid4(),
                        chain_id=self.chain_id,
                        contract_address=self.contract_address,
                        job_id=job.id,
                        lease_id=lease.id,
                        tx_type="submitProof",
                        from_address=self.signer.get_address(),
                        to_address=self.contract_address,
                        idempotency_key=intent_key,
                        status="pending",
                    )
                )
            count += 1
            await db.flush()
        return count

    async def _broadcast_pending(self, db: AsyncSession) -> int:
        await db.commit()
        chain_instance_id = get_chain_instance_id(self.blockchain)
        prepared = await db.execute(
            select(ChainTransaction.id).where(
                ChainTransaction.status == "submitted",
                ChainTransaction.tx_type.in_(["submitProof", "verifyJob"]),
                ChainTransaction.transaction_payload.is_not(None),
                ChainTransaction.chain_id == self.chain_id,
                ChainTransaction.chain_instance_id == chain_instance_id,
                ChainTransaction.contract_address == self.contract_address,
            )
        )
        prepared_ids = list(prepared.scalars().all())
        await db.commit()
        for intent_id in prepared_ids:
            await rebroadcast_prepared(
                db,
                intent_id=intent_id,
                blockchain=self.blockchain,
                signer=self.signer,
            )

        query = await db.execute(
            select(ChainTransaction.id)
            .where(
                ChainTransaction.status == "pending",
                ChainTransaction.tx_type.in_(["submitProof", "verifyJob"]),
                ChainTransaction.chain_id == self.chain_id,
                ChainTransaction.contract_address == self.contract_address,
                or_(
                    ChainTransaction.chain_instance_id.is_(None),
                    ChainTransaction.chain_instance_id == chain_instance_id,
                ),
            )
            .order_by(ChainTransaction.created_at)
            .limit(self.batch_size)
        )
        intent_ids = list(query.scalars().all())
        await db.commit()
        count = 0
        for intent_id in intent_ids:
            intent = (
                await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id))
            ).scalar_one_or_none()
            if intent is None or intent.status != "pending":
                await db.commit()
                continue
            job = (await db.execute(select(Job).where(Job.id == intent.job_id))).scalar_one()
            proof = (
                (
                    await db.execute(
                        select(Proof)
                        .join(JobAttempt, Proof.job_attempt_id == JobAttempt.id)
                        .where(JobAttempt.job_id == job.id)
                        .order_by(Proof.created_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            lease = (await db.execute(select(Lease).where(Lease.id == intent.lease_id))).scalar_one()
            tx_type = intent.tx_type
            job_id = bytes.fromhex(job.chain_job_id.removeprefix("0x"))
            lease_id = bytes.fromhex(lease.lease_id.removeprefix("0x"))

            # Contract state is authoritative and must be checked immediately
            # before broadcast. This catches user timeout-refund wins and chain
            # success that occurred while the runner was down.
            await db.commit()
            chain_job = read_contract_job(self.blockchain, self.contract_address, job_id)
            state = int(chain_job["state"])
            expected_state = 2 if tx_type == "submitProof" else 3
            chain_timestamp = int(self.blockchain.get_block("latest")["timestamp"])
            if tx_type == "submitProof" and (
                chain_timestamp > int(chain_job["lease_expires_at"]) or chain_timestamp > int(chain_job["job_deadline"])
            ):
                intent = (
                    await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id).with_for_update())
                ).scalar_one()
                if intent.status != "pending":
                    await db.commit()
                    continue
                intent.status = "replaced"
                intent.error = "lease or job deadline expired before proof broadcast"
                lease = (
                    await db.execute(select(Lease).where(Lease.id == intent.lease_id).with_for_update())
                ).scalar_one()
                await apply_attempt_failure(db, lease, reason=intent.error, status="expired")
                await db.commit()
                continue
            if state != expected_state:
                intent = (
                    await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id).with_for_update())
                ).scalar_one()
                if intent.status != "pending":
                    await db.commit()
                    continue
                if state in (4, 5) or (tx_type == "submitProof" and state == 3):
                    intent.status = "replaced"
                    intent.error = {
                        3: "proof already submitted on-chain",
                        4: "job already settled on-chain",
                        5: "job already refunded on-chain",
                    }[state]
                    await db.commit()
                else:
                    await db.commit()
                continue
            if tx_type == "submitProof" and bytes(chain_job["lease_id"]) != lease_id:
                intent = (
                    await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id).with_for_update())
                ).scalar_one()
                if intent.status == "pending":
                    intent.status = "replaced"
                    intent.error = "on-chain lease no longer matches proof lease"
                await db.commit()
                continue

            merkle_root = bytes.fromhex(proof.merkle_root.removeprefix("0x"))
            output_hash = bytes.fromhex(proof.output_hash.removeprefix("0x"))
            verdict = bool(proof.valid)

            def build(nonce: int, gas_price: int):
                common = {
                    "contract_address": self.contract_address,
                    "chain_id": self.chain_id,
                    "nonce": nonce,
                    "gas_price": gas_price,
                    "gas_limit": 500_000,
                    "job_id": job_id,
                }
                if tx_type == "submitProof":
                    return build_submit_proof_tx(
                        **common,
                        lease_id=lease_id,
                        merkle_root=merkle_root,
                        output_hash=output_hash,
                    )
                return build_verify_job_tx(**common, is_valid=verdict)

            if await prepare_and_broadcast(
                db,
                intent_id=intent_id,
                blockchain=self.blockchain,
                signer=self.signer,
                chain_id=self.chain_id,
                build_transaction=build,
            ):
                count += 1
        return count

    async def _confirm_submitted(self, db: AsyncSession) -> int:
        await db.commit()
        chain_instance_id = get_chain_instance_id(self.blockchain)
        query = await db.execute(
            select(ChainTransaction.id)
            .join(Job, Job.id == ChainTransaction.job_id)
            .where(
                or_(
                    ChainTransaction.status.in_(("submitted", "confirmed")),
                    (ChainTransaction.status == "finalized")
                    & (ChainTransaction.tx_type == "verifyJob")
                    & Job.status.notin_(("completed", "refunded")),
                ),
                ChainTransaction.tx_type.in_(["submitProof", "verifyJob"]),
                ChainTransaction.chain_id == self.chain_id,
                ChainTransaction.chain_instance_id == chain_instance_id,
                ChainTransaction.contract_address == self.contract_address,
            )
            .order_by(ChainTransaction.created_at)
            .limit(self.batch_size)
        )
        intent_ids = list(query.scalars().all())
        await db.commit()
        count = 0
        for intent_id in intent_ids:
            intent_snapshot = (
                await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id))
            ).scalar_one_or_none()
            if intent_snapshot is None or not intent_snapshot.tx_hash:
                await db.commit()
                continue
            tx_hash = intent_snapshot.tx_hash
            await db.commit()
            receipt = self.blockchain.get_transaction_receipt(tx_hash)
            if receipt is None:
                continue
            if str(receipt.get("to", "")).lower() != self.contract_address.lower():
                continue
            raw_hash = receipt["transactionHash"]
            receipt_hash = "0x" + raw_hash.hex() if isinstance(raw_hash, bytes) else str(raw_hash)
            if receipt_hash.lower() != tx_hash.lower():
                continue
            intent = (
                await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id).with_for_update())
            ).scalar_one()
            if intent.status not in ("submitted", "confirmed", "finalized"):
                await db.commit()
                continue
            previous_status = intent.status
            if int(receipt.get("status", 0)) != 1:
                intent.status = "reverted"
                await db.commit()
                continue
            events = decode_receipt_logs(receipt, self.blockchain.get_abi())
            required = "ProofSubmitted" if intent.tx_type == "submitProof" else "JobSettled"
            if not any(event["event"] == required for event in events):
                intent.status = "reverted"
                intent.error = f"missing {required} event"
                await db.commit()
                continue
            # Confirmation must project actual canonical receipt events as
            # well as the outbox status. Otherwise Job/Lease stay settling/
            # active until a historical scanner catches up, potentially days.
            if not await self.event_poller.ingest_receipt(
                db, receipt, job_id=intent.job_id, required_event=required,
            ):
                continue
            intent = (await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id))).scalar_one()
            intent.block_number = int(receipt["blockNumber"])
            block_hash = receipt["blockHash"]
            intent.block_hash = "0x" + block_hash.hex() if isinstance(block_hash, bytes) else str(block_hash)
            if intent.tx_type == "submitProof":
                job = (await db.execute(select(Job).where(Job.id == intent.job_id))).scalar_one()
                if job.status not in ("completed", "refunded"):
                    job.status = "settling"
                key = f"verifyJob:{intent.job_id}"
                prior = await db.execute(select(ChainTransaction).where(ChainTransaction.idempotency_key == key))
                if prior.scalar_one_or_none() is None:
                    db.add(
                        ChainTransaction(
                            id=uuid.uuid4(),
                            chain_id=self.chain_id,
                            contract_address=self.contract_address,
                            job_id=intent.job_id,
                            lease_id=intent.lease_id,
                            tx_type="verifyJob",
                            from_address=self.signer.get_address(),
                            to_address=self.contract_address,
                            idempotency_key=key,
                            status="pending",
                        )
                    )
            if intent.status != previous_status:
                count += 1
            await db.commit()
        return count
