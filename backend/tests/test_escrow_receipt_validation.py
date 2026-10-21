"""Escrow confirmation trusts only canonical chain transaction/receipt data."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from eth_abi import encode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from web3 import Web3

from app.models import ChainTransaction, SupportedModel, User
from app.services.blockchain_service import load_abi
from app.services.escrow_confirmation import EscrowReceiptError, ReceiptConfirmer, confirm_escrow_receipt
from app.services.job_service import create_job
from app.utils import uuid_to_bytes32


class ReceiptChain:
    def __init__(self, transaction, receipt, block_number=12):
        self.transaction = transaction
        self.receipt = receipt
        self.block_number = block_number

    def get_chain_id(self):
        return 31337

    def get_block_number(self):
        return self.block_number

    def get_block(self, block_identifier):
        return {"number": block_identifier, "hash": b"\x99" * 32, "timestamp": 0}

    def get_transaction(self, tx_hash):
        return self.transaction

    def get_transaction_receipt(self, tx_hash):
        return self.receipt

    def get_abi(self):
        return load_abi()

    def call_contract(self, to, data):
        event = self.receipt["logs"][0]
        decoded = Web3().eth.contract(abi=load_abi()).events.JobCreated().process_log(event)["args"]
        return encode(
            [
                "address",
                "address",
                "bytes32",
                "bytes32",
                "bytes32",
                "bytes32",
                "uint256",
                "uint64",
                "uint64",
                "uint64",
                "uint64",
                "uint8",
            ],
            [
                decoded["user"],
                "0x" + "00" * 20,
                decoded["fingerprint"],
                b"\0" * 32,
                b"\0" * 32,
                b"\0" * 32,
                decoded["amount"],
                0,
                decoded["timestamp"] + 86_400,
                decoded["timestamp"],
                0,
                1,
            ],
        )


def _job_created_log(contract, chain_job_id, user, fingerprint, amount):
    return {
        "address": contract,
        "topics": [
            Web3.keccak(text="JobCreated(bytes32,address,bytes32,uint256,uint256)"),
            bytes.fromhex(chain_job_id[2:]),
            bytes.fromhex(user[2:]).rjust(32, b"\x00"),
        ],
        "data": "0x"
        + encode(
            ["bytes32", "uint256", "uint256"],
            [bytes.fromhex(fingerprint), amount, 1_000],
        ).hex(),
        "blockNumber": 10,
        "transactionHash": b"\x11" * 32,
        "transactionIndex": 0,
        "blockHash": b"\x22" * 32,
        "logIndex": 0,
        "removed": False,
    }


@pytest.mark.asyncio
async def test_real_receipt_is_authoritative_and_idempotent(db: AsyncSession):
    user = User(id=uuid.uuid4(), wallet_address=Web3.to_checksum_address("0x" + "12" * 20), role="user")
    model = SupportedModel(id="resnet50", name="R", price_base_units=50_000)
    db.add_all([user, model])
    job_id = uuid.uuid4()
    fingerprint = hashlib.sha256(b"fp").hexdigest()
    chain_job_id = uuid_to_bytes32(job_id)
    job = await create_job(
        db,
        job_id=job_id,
        user_id=user.id,
        model_id=model.id,
        chain_job_id=chain_job_id,
        price_base_units=50_000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    job.expected_fingerprint = fingerprint
    contract = Web3.to_checksum_address("0x" + "ab" * 20)
    tx_hash = "0x" + "11" * 32
    receipt = {
        "status": 1,
        "blockNumber": 10,
        "blockHash": b"\x22" * 32,
        "logs": [_job_created_log(contract, chain_job_id, user.wallet_address, fingerprint, 50_000)],
    }
    chain = ReceiptChain({"from": user.wallet_address, "to": contract, "chainId": 31337}, receipt)

    confirmed = await confirm_escrow_receipt(
        db,
        blockchain=chain,
        job=job,
        authenticated_wallet=user.wallet_address,
        tx_hash=tx_hash,
        expected_chain_id=31337,
        expected_contract=contract,
        confirmations_required=2,
    )
    assert confirmed.status == "queued"
    assert int(confirmed.blockchain_escrow_amount) == 50_000
    assert confirmed.deadline == datetime.fromtimestamp(87_400, timezone.utc)

    repeated = await confirm_escrow_receipt(
        db,
        blockchain=chain,
        job=job,
        authenticated_wallet=user.wallet_address,
        tx_hash=tx_hash,
        expected_chain_id=31337,
        expected_contract=contract,
        confirmations_required=2,
    )
    assert repeated.id == job.id


@pytest.mark.asyncio
async def test_mismatched_receipt_never_queues_job(db: AsyncSession):
    user = User(id=uuid.uuid4(), wallet_address=Web3.to_checksum_address("0x" + "12" * 20), role="user")
    model = SupportedModel(id="resnet50", name="R", price_base_units=50_000)
    db.add_all([user, model])
    job_id = uuid.uuid4()
    job = await create_job(
        db,
        job_id=job_id,
        user_id=user.id,
        model_id=model.id,
        chain_job_id=uuid_to_bytes32(job_id),
        price_base_units=50_000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    job.expected_fingerprint = hashlib.sha256(b"fp").hexdigest()
    contract = Web3.to_checksum_address("0x" + "ab" * 20)
    chain = ReceiptChain(
        {"from": Web3.to_checksum_address("0x" + "34" * 20), "to": contract, "chainId": 31337},
        {"status": 1, "blockNumber": 10, "blockHash": b"\x22" * 32, "logs": []},
    )
    with pytest.raises(EscrowReceiptError, match="sender"):
        await confirm_escrow_receipt(
            db,
            blockchain=chain,
            job=job,
            authenticated_wallet=user.wallet_address,
            tx_hash="0x" + "11" * 32,
            expected_chain_id=31337,
            expected_contract=contract,
            confirmations_required=1,
        )
    assert job.status == "pending_blockchain"


@pytest.mark.asyncio
async def test_transaction_hash_cannot_confirm_two_jobs_on_same_chain_instance(db: AsyncSession):
    user = User(id=uuid.uuid4(), wallet_address=Web3.to_checksum_address("0x" + "12" * 20), role="user")
    model = SupportedModel(id="resnet50", name="R", price_base_units=50_000)
    db.add_all([user, model])
    other_job = await create_job(
        db,
        job_id=uuid.uuid4(),
        user_id=user.id,
        model_id=model.id,
        chain_job_id=uuid_to_bytes32(uuid.uuid4()),
        price_base_units=50_000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    job_id = uuid.uuid4()
    fingerprint = hashlib.sha256(b"fp").hexdigest()
    chain_job_id = uuid_to_bytes32(job_id)
    job = await create_job(
        db,
        job_id=job_id,
        user_id=user.id,
        model_id=model.id,
        chain_job_id=chain_job_id,
        price_base_units=50_000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    job.expected_fingerprint = fingerprint
    contract = Web3.to_checksum_address("0x" + "ab" * 20)
    tx_hash = "0x" + "11" * 32
    db.add(
        ChainTransaction(
            id=uuid.uuid4(),
            chain_id=31337,
            chain_instance_id="0x" + "99" * 32,
            contract_address=contract,
            job_id=other_job.id,
            tx_hash=tx_hash,
            tx_type="createJob",
            from_address=user.wallet_address,
            to_address=contract,
            idempotency_key="existing-create:" + uuid.uuid4().hex,
            status="confirmed",
        )
    )
    await db.flush()
    receipt = {
        "status": 1,
        "blockNumber": 10,
        "blockHash": b"\x22" * 32,
        "logs": [_job_created_log(contract, chain_job_id, user.wallet_address, fingerprint, 50_000)],
    }
    chain = ReceiptChain({"from": user.wallet_address, "to": contract, "chainId": 31337}, receipt)

    with pytest.raises(EscrowReceiptError, match="already confirmed another job"):
        await confirm_escrow_receipt(
            db,
            blockchain=chain,
            job=job,
            authenticated_wallet=user.wallet_address,
            tx_hash=tx_hash,
            expected_chain_id=31337,
            expected_contract=contract,
            confirmations_required=1,
        )
    assert job.status == "pending_blockchain"


@pytest.mark.asyncio
async def test_pending_escrow_is_resumed_by_receipt_confirmer(db: AsyncSession):
    user = User(id=uuid.uuid4(), wallet_address=Web3.to_checksum_address("0x" + "12" * 20), role="user")
    model = SupportedModel(id="resnet50", name="R", price_base_units=50_000)
    db.add_all([user, model])
    job_id = uuid.uuid4()
    fingerprint = hashlib.sha256(b"fp").hexdigest()
    chain_job_id = uuid_to_bytes32(job_id)
    job = await create_job(
        db,
        job_id=job_id,
        user_id=user.id,
        model_id=model.id,
        chain_job_id=chain_job_id,
        price_base_units=50_000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    job.expected_fingerprint = fingerprint
    contract = Web3.to_checksum_address("0x" + "ab" * 20)
    tx_hash = "0x" + "11" * 32
    chain = ReceiptChain(
        {"from": user.wallet_address, "to": contract, "chainId": 31337},
        None,
    )

    pending = await confirm_escrow_receipt(
        db,
        blockchain=chain,
        job=job,
        authenticated_wallet=user.wallet_address,
        tx_hash=tx_hash,
        expected_chain_id=31337,
        expected_contract=contract,
        confirmations_required=2,
    )
    await db.commit()
    intent = (await db.execute(select(ChainTransaction).where(ChainTransaction.job_id == job.id))).scalar_one()
    assert pending.status == "pending_blockchain"
    assert intent.status == "submitted"

    chain.receipt = {
        "status": 1,
        "blockNumber": 10,
        "blockHash": b"\x22" * 32,
        "logs": [_job_created_log(contract, chain_job_id, user.wallet_address, fingerprint, 50_000)],
    }
    confirmer = ReceiptConfirmer(
        blockchain=chain,
        chain_id=31337,
        contract_address=contract,
        confirmations_required=2,
    )
    assert await confirmer.run_once(db) == {"confirmed": 1, "pending": 0, "rejected": 0}
    await db.refresh(job)
    await db.refresh(intent)
    assert job.status == "queued"
    assert intent.status == "confirmed"


@pytest.mark.asyncio
async def test_receipt_confirmer_terminally_rejects_mismatched_mined_receipt(db: AsyncSession):
    user = User(id=uuid.uuid4(), wallet_address=Web3.to_checksum_address("0x" + "12" * 20), role="user")
    model = SupportedModel(id="resnet50", name="R", price_base_units=50_000)
    db.add_all([user, model])
    job_id = uuid.uuid4()
    fingerprint = hashlib.sha256(b"fp").hexdigest()
    chain_job_id = uuid_to_bytes32(job_id)
    job = await create_job(
        db,
        job_id=job_id,
        user_id=user.id,
        model_id=model.id,
        chain_job_id=chain_job_id,
        price_base_units=50_000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    job.expected_fingerprint = fingerprint
    contract = Web3.to_checksum_address("0x" + "ab" * 20)
    tx_hash = "0x" + "11" * 32
    chain = ReceiptChain({"from": user.wallet_address, "to": contract, "chainId": 31337}, None)

    await confirm_escrow_receipt(
        db,
        blockchain=chain,
        job=job,
        authenticated_wallet=user.wallet_address,
        tx_hash=tx_hash,
        expected_chain_id=31337,
        expected_contract=contract,
        confirmations_required=1,
    )
    await db.commit()
    chain.receipt = {
        "status": 1,
        "blockNumber": 10,
        "blockHash": b"\x22" * 32,
        "logs": [_job_created_log(contract, chain_job_id, user.wallet_address, "00" * 32, 50_000)],
    }
    confirmer = ReceiptConfirmer(
        blockchain=chain,
        chain_id=31337,
        contract_address=contract,
        confirmations_required=1,
    )

    assert await confirmer.run_once(db) == {"confirmed": 0, "pending": 0, "rejected": 1}
    intent = (await db.execute(select(ChainTransaction).where(ChainTransaction.job_id == job.id))).scalar_one()
    assert intent.status == "reverted"
    assert intent.error == "EscrowReceiptError"
    assert job.status == "pending_blockchain"


@pytest.mark.asyncio
async def test_receipt_confirmer_retries_when_registered_transaction_is_temporarily_unavailable(db: AsyncSession):
    user = User(id=uuid.uuid4(), wallet_address=Web3.to_checksum_address("0x" + "12" * 20), role="user")
    model = SupportedModel(id="resnet50", name="R", price_base_units=50_000)
    db.add_all([user, model])
    job_id = uuid.uuid4()
    job = await create_job(
        db,
        job_id=job_id,
        user_id=user.id,
        model_id=model.id,
        chain_job_id=uuid_to_bytes32(job_id),
        price_base_units=50_000,
        deadline=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    job.expected_fingerprint = hashlib.sha256(b"fp").hexdigest()
    contract = Web3.to_checksum_address("0x" + "ab" * 20)
    chain = ReceiptChain({"from": user.wallet_address, "to": contract, "chainId": 31337}, None)
    await confirm_escrow_receipt(
        db,
        blockchain=chain,
        job=job,
        authenticated_wallet=user.wallet_address,
        tx_hash="0x" + "11" * 32,
        expected_chain_id=31337,
        expected_contract=contract,
        confirmations_required=1,
    )
    await db.commit()
    chain.transaction = None
    confirmer = ReceiptConfirmer(
        blockchain=chain,
        chain_id=31337,
        contract_address=contract,
        confirmations_required=1,
    )

    assert await confirmer.run_once(db) == {"confirmed": 0, "pending": 1, "rejected": 0}
    intent = (await db.execute(select(ChainTransaction).where(ChainTransaction.job_id == job.id))).scalar_one()
    assert intent.status == "submitted"
