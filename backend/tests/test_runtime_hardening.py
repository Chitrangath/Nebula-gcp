"""Regression tests for durable chain outbox and automatic reorg safety."""

import uuid

import pytest
from sqlalchemy import select

from app.models import BlockchainEvent, ChainCursor, ChainTransaction, ReconciliationIncident
from app.services.blockchain_events import CriticalReconciliationError, EventPoller
from app.services.blockchain_service import FakeBlockchainBackend
from app.services.chain_outbox import prepare_and_broadcast, rebroadcast_prepared
from app.services.tx_signer import FakeSigner
from app.utils import uuid_to_bytes32


def _intent() -> ChainTransaction:
    return ChainTransaction(
        id=uuid.uuid4(),
        chain_id=31337,
        contract_address="0x" + "ab" * 20,
        tx_type="verifyJob",
        from_address="0x" + "cd" * 20,
        to_address="0x" + "ab" * 20,
        idempotency_key="verifyJob:" + uuid.uuid4().hex,
        status="pending",
    )


@pytest.mark.asyncio
async def test_outbox_persists_hash_payload_and_nonce_before_broadcast(db):
    intent = _intent()
    db.add(intent)
    await db.commit()
    chain = FakeBlockchainBackend(chain_id=31337)
    signer = FakeSigner(address=intent.from_address, chain_id=31337)
    observed = {}

    def fail_after_observing(raw):
        observed["row"] = intent
        raise ConnectionError("simulated response loss")

    signer.broadcast_raw_transaction = fail_after_observing
    sent = await prepare_and_broadcast(
        db,
        intent_id=intent.id,
        blockchain=chain,
        signer=signer,
        chain_id=31337,
        build_transaction=lambda nonce, gas_price: {
            "to": intent.to_address,
            "data": b"\x12\x34",
            "chainId": 31337,
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 100_000,
        },
    )

    persisted = (await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent.id))).scalar_one()
    assert sent is False
    assert observed["row"].tx_hash is not None
    assert persisted.status == "submitted"
    assert persisted.nonce == 0
    assert persisted.transaction_payload["data"] == "0x1234"


@pytest.mark.asyncio
async def test_outbox_restart_rebroadcasts_identical_prepared_hash(db):
    intent = _intent()
    db.add(intent)
    await db.commit()
    chain = FakeBlockchainBackend(chain_id=31337)
    signer = FakeSigner(address=intent.from_address, chain_id=31337)
    original_broadcast = signer.broadcast_raw_transaction
    signer.broadcast_raw_transaction = lambda raw: (_ for _ in ()).throw(ConnectionError())
    await prepare_and_broadcast(
        db,
        intent_id=intent.id,
        blockchain=chain,
        signer=signer,
        chain_id=31337,
        build_transaction=lambda nonce, gas_price: {
            "to": intent.to_address,
            "data": b"\xaa",
            "chainId": 31337,
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 100_000,
        },
    )
    expected = intent.tx_hash
    signer.broadcast_raw_transaction = original_broadcast

    assert await rebroadcast_prepared(db, intent_id=intent.id, blockchain=chain, signer=signer)
    assert signer._tx_hashes[-1] == expected


@pytest.mark.asyncio
async def test_outbox_does_not_rebroadcast_after_nonce_was_consumed(db):
    intent = _intent()
    db.add(intent)
    await db.commit()
    chain = FakeBlockchainBackend(chain_id=31337)
    signer = FakeSigner(address=intent.from_address, chain_id=31337)
    signer.broadcast_raw_transaction = lambda raw: (_ for _ in ()).throw(ConnectionError())
    await prepare_and_broadcast(
        db,
        intent_id=intent.id,
        blockchain=chain,
        signer=signer,
        chain_id=31337,
        build_transaction=lambda nonce, gas_price: {
            "to": intent.to_address,
            "data": b"\xbb",
            "chainId": 31337,
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 100_000,
        },
    )
    chain._nonces[intent.from_address.lower()] = int(intent.nonce) + 1

    assert not await rebroadcast_prepared(db, intent_id=intent.id, blockchain=chain, signer=signer)
    await db.refresh(intent)
    assert intent.status == "replaced"
    assert intent.error == "signer nonce already consumed by another transaction"


@pytest.mark.asyncio
async def test_outbox_reprices_missing_legacy_transaction_after_rebroadcast_rejection(db):
    intent = _intent()
    db.add(intent)
    await db.commit()
    chain = FakeBlockchainBackend(chain_id=31337)
    signer = FakeSigner(address=intent.from_address, chain_id=31337)
    signer.broadcast_raw_transaction = lambda raw: (_ for _ in ()).throw(ConnectionError())
    await prepare_and_broadcast(
        db,
        intent_id=intent.id,
        blockchain=chain,
        signer=signer,
        chain_id=31337,
        build_transaction=lambda nonce, gas_price: {
            "to": intent.to_address,
            "data": b"\xcc",
            "chainId": 31337,
            "nonce": nonce,
            "gasPrice": 1,
            "gas": 100_000,
        },
    )
    original_hash = intent.tx_hash
    broadcasts = 0

    def reject_once_then_accept(raw):
        nonlocal broadcasts
        broadcasts += 1
        if broadcasts == 1:
            raise ConnectionError("underpriced")
        return signer._prepared[raw]

    signer.broadcast_raw_transaction = reject_once_then_accept

    assert await rebroadcast_prepared(db, intent_id=intent.id, blockchain=chain, signer=signer)
    await db.refresh(intent)
    assert broadcasts == 2
    assert intent.tx_hash != original_hash
    assert intent.nonce == 0
    assert intent.transaction_payload["gasPrice"] > chain.get_gas_price()
    assert intent.error is None


@pytest.mark.asyncio
async def test_outbox_recovers_dropped_prepared_intent_when_nonce_is_unconsumed(db):
    intent = _intent()
    db.add(intent)
    await db.commit()
    chain = FakeBlockchainBackend(chain_id=31337)
    signer = FakeSigner(address=intent.from_address, chain_id=31337)
    original_broadcast = signer.broadcast_raw_transaction
    signer.broadcast_raw_transaction = lambda raw: (_ for _ in ()).throw(ConnectionError())
    await prepare_and_broadcast(
        db,
        intent_id=intent.id,
        blockchain=chain,
        signer=signer,
        chain_id=31337,
        build_transaction=lambda nonce, gas_price: {
            "to": intent.to_address,
            "data": b"\xdd",
            "chainId": 31337,
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 100_000,
        },
    )
    intent.status = "dropped"
    await db.commit()
    signer.broadcast_raw_transaction = original_broadcast

    assert await rebroadcast_prepared(db, intent_id=intent.id, blockchain=chain, signer=signer)
    await db.refresh(intent)
    assert intent.status == "submitted"


class ChangedBlockBackend(FakeBlockchainBackend):
    def __init__(self, block_hash: bytes):
        super().__init__(chain_id=31337)
        self._block_number = 10
        self.block_hash = block_hash

    def get_block(self, block_identifier):
        return {"number": block_identifier, "hash": self.block_hash, "timestamp": 0}


class HistoricalEventBackend(ChangedBlockBackend):
    def get_logs(self, filter_params):
        return [{"historical": True}]


class DuplicateEventBackend(HistoricalEventBackend):
    def get_logs(self, filter_params):
        return [{"duplicate": True}, {"duplicate": True}]


@pytest.mark.asyncio
async def test_historical_event_for_unknown_job_is_durable_and_does_not_block_cursor(db, monkeypatch):
    """A fresh database can catch up across events created by an older deployment."""
    contract = "0x" + "ab" * 20
    unknown_job_id = uuid.uuid4()
    monkeypatch.setattr(
        "app.services.blockchain_events.decode_receipt_logs",
        lambda receipt, abi: [
            {
                "event": "JobCreated",
                "args": {"jobId": bytes.fromhex(uuid_to_bytes32(unknown_job_id)[2:])},
                "logIndex": 0,
                "transactionHash": b"\x11" * 32,
                "blockNumber": 10,
                "blockHash": b"\x22" * 32,
            }
        ],
    )
    poller = EventPoller(
        blockchain=HistoricalEventBackend(b"\x22" * 32),
        chain_id=31337,
        contract_address=contract,
        deployment_block=10,
        confirmations=1,
        finality=1,
    )

    result = await poller.run_once(db)
    await db.commit()

    event = (await db.execute(select(BlockchainEvent))).scalar_one()
    cursor = (await db.execute(select(ChainCursor))).scalar_one()
    assert result["events"] == 1
    assert event.job_id is None
    assert event.event_data["jobId"].startswith("0x")
    assert cursor.last_scanned_block == 10


@pytest.mark.asyncio
async def test_duplicate_rpc_logs_are_ingested_once(db, monkeypatch):
    contract = "0x" + "ab" * 20
    monkeypatch.setattr(
        "app.services.blockchain_events.decode_receipt_logs",
        lambda receipt, abi: [
            {
                "event": "JobCreated",
                "args": {},
                "logIndex": 7,
                "transactionHash": b"\x33" * 32,
                "blockNumber": 10,
                "blockHash": b"\x22" * 32,
            }
        ],
    )
    poller = EventPoller(
        blockchain=DuplicateEventBackend(b"\x22" * 32),
        chain_id=31337,
        contract_address=contract,
        deployment_block=10,
        confirmations=1,
        finality=1,
    )

    result = await poller.run_once(db)
    await db.commit()

    assert result["events"] == 1
    assert (await db.execute(select(BlockchainEvent))).scalars().all().__len__() == 1


@pytest.mark.asyncio
async def test_conflicting_duplicate_rpc_logs_halt_ingestion(db, monkeypatch):
    contract = "0x" + "ab" * 20

    def decode(receipt, abi):
        marker = receipt["logs"][0]
        return [
            {
                "event": "JobCreated",
                "args": {"amount": 1 if marker.get("first") else 2},
                "logIndex": 7,
                "transactionHash": b"\x33" * 32,
                "blockNumber": 10,
                "blockHash": b"\x22" * 32,
            }
        ]

    monkeypatch.setattr("app.services.blockchain_events.decode_receipt_logs", decode)
    backend = DuplicateEventBackend(b"\x22" * 32)
    backend.get_logs = lambda filter_params: [{"first": True}, {"first": False}]
    poller = EventPoller(
        blockchain=backend,
        chain_id=31337,
        contract_address=contract,
        deployment_block=10,
    )

    with pytest.raises(CriticalReconciliationError, match="conflicting payloads"):
        await poller.run_once(db)


@pytest.mark.asyncio
async def test_nonfinal_reorg_orphans_event_and_rewinds_cursor(db):
    contract = "0x" + "ab" * 20
    event = BlockchainEvent(
        id=uuid.uuid4(),
        chain_id=31337,
        chain_instance_id="0x" + "33" * 32,
        contract_address=contract,
        transaction_hash="0x" + "11" * 32,
        log_index=0,
        block_number=10,
        block_hash="0x" + "22" * 32,
        event_name="JobCreated",
        event_data={},
        confirmation_status="confirmed",
    )
    cursor = ChainCursor(
        id=uuid.uuid4(),
        chain_id=31337,
        chain_instance_id="0x" + "33" * 32,
        contract_address=contract,
        last_scanned_block=10,
        last_scanned_block_hash=event.block_hash,
    )
    db.add_all([event, cursor])
    await db.commit()
    poller = EventPoller(
        blockchain=ChangedBlockBackend(b"\x33" * 32),
        chain_id=31337,
        contract_address=contract,
        deployment_block=1,
    )

    result = await poller.run_once(db)

    await db.refresh(event)
    assert result["reorged"] == 1
    assert event.confirmation_status == "orphaned"


@pytest.mark.asyncio
async def test_finalized_divergence_persists_incident_and_halts(db):
    contract = "0x" + "ab" * 20
    event = BlockchainEvent(
        id=uuid.uuid4(),
        chain_id=31337,
        chain_instance_id="0x" + "66" * 32,
        contract_address=contract,
        transaction_hash="0x" + "44" * 32,
        log_index=0,
        block_number=10,
        block_hash="0x" + "55" * 32,
        event_name="JobSettled",
        event_data={},
        confirmation_status="finalized",
    )
    cursor = ChainCursor(
        id=uuid.uuid4(),
        chain_id=31337,
        chain_instance_id="0x" + "66" * 32,
        contract_address=contract,
        last_scanned_block=10,
        last_scanned_block_hash=event.block_hash,
    )
    db.add_all([event, cursor])
    await db.commit()
    poller = EventPoller(
        blockchain=ChangedBlockBackend(b"\x66" * 32),
        chain_id=31337,
        contract_address=contract,
        deployment_block=1,
    )

    with pytest.raises(CriticalReconciliationError):
        await poller.run_once(db)

    incident = (await db.execute(select(ReconciliationIncident))).scalar_one()
    await db.refresh(cursor)
    assert incident.severity == "critical"
    assert cursor.halted is True
