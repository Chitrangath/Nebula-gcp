"""Receipt recovery keeps settled jobs independent of historical scan lag."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from eth_abi import encode
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from web3 import Web3

from app.config import settings
from app.database import get_db
from app.main import create_app
from app.models import (
    BlockchainEvent,
    ChainCursor,
    ChainTransaction,
    Job,
    JobAttempt,
    Lease,
    Node,
    Payment,
    SupportedModel,
    User,
)
from app.security import get_current_user
from app.services.blockchain_events import CriticalReconciliationError, EventPoller, reconcile_job_state
from app.services.blockchain_service import FakeBlockchainBackend, load_abi
from app.services.settlement_coordinator import SettlementCoordinator
from app.services.storage import InMemoryStorage
from app.services.tx_signer import FakeSigner
from app.utils import uuid_to_bytes32

CONTRACT = "0x" + "ab" * 20
GENESIS = "0x" + "ab" * 32
TX_HASH = "0x" + "cd" * 32
BLOCK_HASH = b"\xee" * 32
SETTLEMENT_BLOCK = 300_000
SETTLEMENT_TIMESTAMP = 1_790_000_000


class ReceiptChain(FakeBlockchainBackend):
    """RPC boundary with canonical receipt evidence and unavailable log history."""

    def __init__(self) -> None:
        super().__init__(chain_id=421614)
        self._block_number = SETTLEMENT_BLOCK + 20
        self.block_hash = BLOCK_HASH
        self.allow_history = False
        self.log_ranges = []

    def get_abi(self):
        return load_abi()

    def get_logs(self, filter_params):
        if not self.allow_history:
            raise AssertionError("Settled job recovery must not wait for historical get_logs")
        self.log_ranges.append((filter_params["fromBlock"], filter_params["toBlock"]))
        return [
            log
            for receipt in self._receipts.values()
            for log in receipt["logs"]
            if filter_params["fromBlock"] <= log["blockNumber"] <= filter_params["toBlock"]
        ]

    def get_block(self, block_identifier):
        number = self._block_number if block_identifier == "latest" else int(block_identifier)
        return {
            "number": number,
            "hash": bytes.fromhex(GENESIS[2:]) if number == 0 else self.block_hash,
            "timestamp": SETTLEMENT_TIMESTAMP,
        }


async def funded_job(db, *, status="settling", lease_status="active"):
    user = User(id=uuid.uuid4(), wallet_address="0x" + "11" * 20, role="user")
    provider = User(id=uuid.uuid4(), wallet_address="0x" + "22" * 20, role="provider")
    model = SupportedModel(id="resnet50", name="ResNet50", price_base_units=50_000)
    node = Node(
        id=uuid.uuid4(),
        provider_id=provider.id,
        gpu_name="RTX 3050",
        vram_gb=4,
        status="online",
        api_key_hash="a" * 64,
        active_leases=1 if lease_status == "active" else 0,
    )
    job_id = uuid.uuid4()
    lease_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    job = Job(
        id=job_id,
        user_id=user.id,
        model_id=model.id,
        chain_job_id=uuid_to_bytes32(job_id),
        assigned_node_id=node.id,
        current_lease_id=lease_id,
        status=status,
        price_base_units=50_000,
        deadline=now + timedelta(hours=1),
        current_attempt=1,
    )
    lease = Lease(
        id=lease_id,
        job_id=job.id,
        node_id=node.id,
        lease_id=uuid_to_bytes32(lease_id),
        expires_at=now + timedelta(minutes=30),
        status=lease_status,
    )
    attempt = JobAttempt(
        id=uuid.uuid4(),
        job_id=job.id,
        node_id=node.id,
        lease_id=lease.id,
        attempt_number=1,
        status="running" if lease_status == "active" else "failed",
    )
    db.add_all([user, provider, model, node, job, lease, attempt])
    db.add(
        ChainTransaction(
            id=uuid.uuid4(),
            chain_id=421614,
            chain_instance_id=GENESIS,
            contract_address=CONTRACT,
            job_id=job.id,
            tx_hash="0x" + "01" * 32,
            tx_type="createJob",
            from_address=user.wallet_address,
            to_address=CONTRACT,
            status="confirmed",
            idempotency_key=f"createJob:{job.id}",
        )
    )
    await db.commit()
    return user, provider, node, job, lease, attempt


async def settlement_intent(db, job, lease, *, status="confirmed"):
    intent = ChainTransaction(
        id=uuid.uuid4(),
        chain_id=421614,
        chain_instance_id=GENESIS,
        contract_address=CONTRACT,
        job_id=job.id,
        lease_id=lease.id,
        tx_hash=TX_HASH,
        tx_type="verifyJob",
        from_address="0x" + "33" * 20,
        to_address=CONTRACT,
        status=status,
        block_number=SETTLEMENT_BLOCK,
        block_hash="0x" + BLOCK_HASH.hex(),
        idempotency_key=f"verifyJob:{job.id}",
    )
    db.add(intent)
    await db.commit()
    return intent


def coordinator(chain, **kwargs):
    return SettlementCoordinator(
        blockchain=chain,
        signer=FakeSigner(address="0x" + "33" * 20, chain_id=421614),
        storage=InMemoryStorage(),
        contract_address=CONTRACT,
        chain_id=421614,
        **kwargs,
    )


def settled_receipt(job, provider):
    chain_job_id = bytes.fromhex(job.chain_job_id[2:])
    common = {
        "address": Web3.to_checksum_address(CONTRACT),
        "blockNumber": SETTLEMENT_BLOCK,
        "blockHash": BLOCK_HASH,
        "transactionHash": bytes.fromhex(TX_HASH[2:]),
        "transactionIndex": 0,
        "removed": False,
    }
    return {
        "status": 1,
        "to": Web3.to_checksum_address(CONTRACT),
        "transactionHash": bytes.fromhex(TX_HASH[2:]),
        "blockNumber": SETTLEMENT_BLOCK,
        "blockHash": BLOCK_HASH,
        "logs": [
            {
                **common,
                "logIndex": 0,
                "topics": [
                    Web3.keccak(text="PaymentCredited(bytes32,address,uint256)"),
                    chain_job_id,
                    encode(["address"], [provider.wallet_address]),
                ],
                "data": encode(["uint256"], [50_000]),
            },
            {
                **common,
                "logIndex": 1,
                "topics": [
                    Web3.keccak(text="JobSettled(bytes32,bool,uint256)"),
                    chain_job_id,
                ],
                "data": encode(["bool", "uint256"], [True, SETTLEMENT_TIMESTAMP]),
            },
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("intent_status", ["submitted", "confirmed", "finalized"])
@pytest.mark.parametrize("lease_status", ["active", "expired"])
async def test_confirmed_settlement_releases_gpu_and_updates_job_without_scan_catchup(
    db, monkeypatch, intent_status, lease_status
):
    user, provider, node, job, lease, attempt = await funded_job(db, lease_status=lease_status)
    chain = ReceiptChain()
    chain._receipts[TX_HASH] = settled_receipt(job, provider)
    cursor = ChainCursor(
        id=uuid.uuid4(),
        chain_id=421614,
        chain_instance_id=GENESIS,
        contract_address=CONTRACT,
        last_scanned_block=1_000,
        last_scanned_block_hash="0x" + "ee" * 32,
    )
    db.add(cursor)
    await settlement_intent(db, job, lease, status=intent_status)
    monkeypatch.setattr(settings, "NEBULA_PAYMENT_CONTRACT", CONTRACT)
    monkeypatch.setattr(settings, "CHAIN_ID", 421614)
    app = create_app(blockchain=chain, storage=InMemoryStorage())

    async def test_db():
        yield db

    app.dependency_overrides[get_db] = test_db
    app.dependency_overrides[get_current_user] = lambda: user
    settlement = coordinator(chain)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await settlement.run_once(db)
        response = await client.get(f"/v1/jobs/{job.id}")
        assert response.status_code == 200
        detail = response.json()
        assert detail["status"] == "completed"
        assert detail["on_chain_state"] == "Settled"
        assert detail["current_lease_status"] == "completed"
        assert detail["provider_payment_credit_status"] == "credited"
        app.dependency_overrides[get_current_user] = lambda: provider
        nodes = (await client.get("/v1/nodes")).json()
        assert nodes[0]["active_leases"] == 0
        assert nodes[0]["active_lease"] is None
        await settlement.run_once(db)
        credits = (await client.get("/v1/earnings")).json()["credits"]
        assert len(credits) == 1
        assert credits[0]["amount_base_units"] == "50000"
    await db.refresh(cursor)
    assert cursor.last_scanned_block == 1_000
    await db.refresh(attempt)
    assert attempt.status == "completed"
    assert len((await db.execute(select(Payment))).scalars().all()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,lease_status", [("running", "active"), ("verifying", "active"), ("retry_pending", "failed")]
)
async def test_reconciliation_does_not_replay_old_assignment_over_local_progress(db, status, lease_status):
    _, provider, node, job, lease, attempt = await funded_job(db, status=status, lease_status=lease_status)
    for index, event_name in enumerate(("JobCreated", "ProviderAssigned")):
        db.add(
            BlockchainEvent(
                id=uuid.uuid4(),
                chain_id=421614,
                chain_instance_id=GENESIS,
                contract_address=CONTRACT,
                job_id=job.id,
                transaction_hash="0x" + f"{index + 1:02x}" * 32,
                log_index=0,
                block_number=index + 1,
                block_hash="0x" + "ee" * 32,
                event_name=event_name,
                confirmation_status="finalized",
                event_data={"jobId": job.chain_job_id, "provider": provider.wallet_address, "leaseId": lease.lease_id},
            )
        )
    await db.commit()
    await reconcile_job_state(db, job.id)
    await db.refresh(job)
    await db.refresh(lease)
    await db.refresh(attempt)
    await db.refresh(node)
    assert job.status == status
    assert lease.status == lease_status
    assert attempt.status == ("running" if lease_status == "active" else "failed")
    assert node.active_leases == (1 if lease_status == "active" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_evidence", ["wrong_emitter", "wrong_job", "noncanonical", "unconfirmed", "wrong_target", "wrong_hash"]
)
async def test_untrusted_settlement_receipt_cannot_complete_job_or_credit_funds(db, invalid_evidence):
    _, provider, _, job, lease, _ = await funded_job(db)
    await settlement_intent(db, job, lease, status="submitted")
    chain = ReceiptChain()
    receipt = settled_receipt(job, provider)
    confirmations = 1
    if invalid_evidence == "wrong_emitter":
        for log in receipt["logs"]:
            log["address"] = Web3.to_checksum_address("0x" + "44" * 20)
    elif invalid_evidence == "wrong_job":
        for log in receipt["logs"]:
            log["topics"][1] = b"\x44" * 32
    elif invalid_evidence == "noncanonical":
        receipt["blockHash"] = b"\x44" * 32
        for log in receipt["logs"]:
            log["blockHash"] = receipt["blockHash"]
    elif invalid_evidence == "unconfirmed":
        chain._block_number = SETTLEMENT_BLOCK
        confirmations = 3
    elif invalid_evidence == "wrong_target":
        receipt["to"] = Web3.to_checksum_address("0x" + "44" * 20)
    else:
        receipt["transactionHash"] = b"\x44" * 32
    chain._receipts[TX_HASH] = receipt
    await coordinator(chain, confirmations=confirmations).run_once(db)
    await db.refresh(job)
    await db.refresh(lease)
    assert job.status == "settling"
    assert lease.status == "active"
    assert (await db.execute(select(Payment))).scalars().all() == []
    assert (await db.execute(select(BlockchainEvent))).scalars().all() == []


@pytest.mark.asyncio
async def test_first_receipt_retains_history_start_and_scanner_replay_is_idempotent(db):
    _, provider, _, job, lease, _ = await funded_job(db)
    await settlement_intent(db, job, lease)
    chain = ReceiptChain()
    chain._receipts[TX_HASH] = settled_receipt(job, provider)
    await coordinator(chain, deployment_block=777).run_once(db)
    cursor = (await db.execute(select(ChainCursor))).scalar_one()
    assert cursor.last_scanned_block == 776

    chain.allow_history = True
    poller = EventPoller(
        blockchain=chain,
        chain_id=421614,
        contract_address=CONTRACT,
        deployment_block=777,
        block_range=10,
    )
    await poller.run_once(db)
    assert chain.log_ranges == [(777, 786)]
    assert cursor.last_scanned_block == 786

    # Once the ordinary historical scan eventually reaches this receipt,
    # the same logs must not create duplicate credit or alter final state.
    cursor.last_scanned_block = SETTLEMENT_BLOCK
    await db.commit()
    await poller.run_once(db)
    await db.refresh(job)
    await db.refresh(lease)
    assert job.status == "completed"
    assert lease.status == "completed"
    assert len((await db.execute(select(Payment))).scalars().all()) == 1
    assert len((await db.execute(select(BlockchainEvent))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_receipt_finalized_history_divergence_still_halts_scanner(db):
    _, provider, _, job, lease, _ = await funded_job(db)
    await settlement_intent(db, job, lease)
    chain = ReceiptChain()
    chain._receipts[TX_HASH] = settled_receipt(job, provider)
    await coordinator(chain, deployment_block=777).run_once(db)
    chain.block_hash = b"\x44" * 32
    chain.allow_history = True
    poller = EventPoller(
        blockchain=chain,
        chain_id=421614,
        contract_address=CONTRACT,
        deployment_block=777,
        block_range=10,
    )
    with pytest.raises(CriticalReconciliationError, match="finalized"):
        await poller.run_once(db)
    cursor = (await db.execute(select(ChainCursor))).scalar_one()
    assert cursor.halted is True


@pytest.mark.asyncio
async def test_receipt_nonfinal_reorg_does_not_skip_unscanned_history(db):
    _, provider, _, job, lease, _ = await funded_job(db)
    await settlement_intent(db, job, lease)
    chain = ReceiptChain()
    chain._block_number = SETTLEMENT_BLOCK
    chain._receipts[TX_HASH] = settled_receipt(job, provider)
    await coordinator(chain, deployment_block=777).run_once(db)
    cursor = (await db.execute(select(ChainCursor))).scalar_one()
    assert cursor.last_scanned_block == 776
    chain.block_hash = b"\x44" * 32
    chain.allow_history = True
    poller = EventPoller(
        blockchain=chain,
        chain_id=421614,
        contract_address=CONTRACT,
        deployment_block=777,
        block_range=10,
    )
    await poller.run_once(db)
    assert chain.log_ranges == [(777, 786)]
    assert cursor.last_scanned_block == 786


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_difference", [None, "chain", "genesis", "contract"])
async def test_unlinked_settlement_recovery_only_uses_this_jobs_chain_scope(db, scope_difference):
    _, _, _, job, lease, _ = await funded_job(db)
    event = BlockchainEvent(
        id=uuid.uuid4(),
        chain_id=31337 if scope_difference == "chain" else 421614,
        chain_instance_id="0x" + "44" * 32 if scope_difference == "genesis" else GENESIS,
        contract_address="0x" + "44" * 20 if scope_difference == "contract" else CONTRACT,
        job_id=None,
        transaction_hash=TX_HASH,
        log_index=1,
        block_number=SETTLEMENT_BLOCK,
        block_hash="0x" + BLOCK_HASH.hex(),
        event_name="JobSettled",
        confirmation_status="finalized",
        event_data={"jobId": job.chain_job_id, "valid": True, "timestamp": SETTLEMENT_TIMESTAMP},
    )
    db.add(event)
    await db.commit()
    await reconcile_job_state(db, job.id)
    await db.refresh(job)
    await db.refresh(lease)
    await db.refresh(event)
    if scope_difference is None:
        assert event.job_id == job.id
        assert job.status == "completed"
        assert lease.status == "completed"
    else:
        assert event.job_id is None
        assert job.status == "settling"
        assert lease.status == "active"


@pytest.mark.asyncio
async def test_late_proof_receipt_does_not_regress_settled_job(db):
    _, provider, _, job, lease, attempt = await funded_job(db)
    await settlement_intent(db, job, lease)
    chain = ReceiptChain()
    chain._receipts[TX_HASH] = settled_receipt(job, provider)
    settlement = coordinator(chain)
    await settlement.run_once(db)
    proof_hash = "0x" + "55" * 32
    proof_block = SETTLEMENT_BLOCK - 1
    common = {
        "address": Web3.to_checksum_address(CONTRACT),
        "blockNumber": proof_block,
        "blockHash": BLOCK_HASH,
        "transactionHash": bytes.fromhex(proof_hash[2:]),
        "transactionIndex": 0,
        "removed": False,
    }
    chain._receipts[proof_hash] = {
        "status": 1,
        "to": Web3.to_checksum_address(CONTRACT),
        "transactionHash": bytes.fromhex(proof_hash[2:]),
        "blockNumber": proof_block,
        "blockHash": BLOCK_HASH,
        "logs": [
            {
                **common,
                "logIndex": 0,
                "topics": [
                    Web3.keccak(text="ProofSubmitted(bytes32,bytes32,bytes32,bytes32,address)"),
                    bytes.fromhex(job.chain_job_id[2:]),
                ],
                "data": encode(
                    ["bytes32", "bytes32", "bytes32", "address"],
                    [
                        bytes.fromhex(lease.lease_id[2:]),
                        b"\x66" * 32,
                        b"\x77" * 32,
                        provider.wallet_address,
                    ],
                ),
            }
        ],
    }
    db.add(
        ChainTransaction(
            id=uuid.uuid4(),
            chain_id=421614,
            chain_instance_id=GENESIS,
            contract_address=CONTRACT,
            job_id=job.id,
            lease_id=lease.id,
            tx_hash=proof_hash,
            tx_type="submitProof",
            from_address="0x" + "33" * 20,
            to_address=CONTRACT,
            status="submitted",
            idempotency_key=f"submitProof:{attempt.id}",
        )
    )
    await db.commit()
    await settlement.run_once(db)
    await db.refresh(job)
    await db.refresh(lease)
    assert job.status == "completed"
    assert lease.status == "completed"
    assert len((await db.execute(select(Payment))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_old_finalized_proof_cannot_starve_new_settlement_receipt(db):
    _, provider, _, job, lease, attempt = await funded_job(db)
    db.add(
        ChainTransaction(
            id=uuid.uuid4(),
            chain_id=421614,
            chain_instance_id=GENESIS,
            contract_address=CONTRACT,
            job_id=job.id,
            lease_id=lease.id,
            tx_hash="0x" + "55" * 32,
            tx_type="submitProof",
            from_address="0x" + "33" * 20,
            to_address=CONTRACT,
            status="finalized",
            idempotency_key=f"submitProof:{attempt.id}",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    await settlement_intent(db, job, lease)
    chain = ReceiptChain()
    chain._receipts[TX_HASH] = settled_receipt(job, provider)
    await coordinator(chain, batch_size=1).run_once(db)
    await db.refresh(job)
    assert job.status == "completed"


@pytest.mark.asyncio
async def test_confirmed_terminal_event_completes_job_despite_old_pending_event(db):
    _, _, _, job, lease, _ = await funded_job(db)
    for event_name, status, block in [("JobCreated", "pending", 1), ("JobSettled", "finalized", SETTLEMENT_BLOCK)]:
        db.add(
            BlockchainEvent(
                id=uuid.uuid4(),
                chain_id=421614,
                chain_instance_id=GENESIS,
                contract_address=CONTRACT,
                job_id=job.id,
                transaction_hash="0x" + ("01" if block == 1 else "cd") * 32,
                log_index=0,
                block_number=block,
                block_hash="0x" + BLOCK_HASH.hex(),
                event_name=event_name,
                confirmation_status=status,
                event_data={"jobId": job.chain_job_id, "valid": True, "timestamp": SETTLEMENT_TIMESTAMP},
            )
        )
    await db.commit()
    await reconcile_job_state(db, job.id)
    await db.refresh(job)
    await db.refresh(lease)
    assert job.status == "completed"
    assert lease.status == "completed"
