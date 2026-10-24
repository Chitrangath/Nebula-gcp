"""BE-003 provider-scoped earnings contract tests."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from eth_abi import encode
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from web3 import Web3

from app.main import app
from app.models import BlockchainEvent, Job, Payment, SupportedModel, User
from app.services.blockchain_events import CriticalReconciliationError, EventPoller
from app.services.blockchain_service import FakeBlockchainBackend
from tests.conftest import seed_authed_user


@pytest.mark.asyncio
async def test_provider_earnings_returns_only_owned_credit_history(db):
    provider_id, token = await seed_authed_user(db)
    provider = (await db.execute(select(User).where(User.id == provider_id))).scalar_one()
    provider.role = "provider"
    other_provider = User(
        id=uuid.uuid4(),
        wallet_address="0x" + "22" * 20,
        role="provider",
    )
    customer = User(
        id=uuid.uuid4(),
        wallet_address="0x" + "33" * 20,
        role="user",
    )
    model = SupportedModel(id="earnings-model", name="Earnings", price_base_units=100)
    db.add_all([other_provider, customer, model])
    await db.flush()
    jobs = [
        Job(
            id=uuid.uuid4(),
            user_id=customer.id,
            model_id=model.id,
            chain_job_id="0x" + f"{index:064x}",
            price_base_units=100,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        for index in (1, 2, 3)
    ]
    db.add_all(jobs)
    await db.flush()
    first_created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    second_created_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    withdrawn_at = datetime.now(timezone.utc)
    db.add_all(
        [
            Payment(
                job_id=jobs[0].id,
                user_id=customer.id,
                provider_id=provider.id,
                amount_base_units=75,
                payment_type="provider_credit",
                status="credited",
                blockchain_tx_hash="0x" + "aa" * 32,
                created_at=first_created_at,
            ),
            Payment(
                job_id=jobs[1].id,
                user_id=customer.id,
                provider_id=provider.id,
                amount_base_units=50,
                payment_type="provider_credit",
                status="withdrawn",
                blockchain_tx_hash="0x" + "bb" * 32,
                withdrawal_tx_hash="0x" + "dd" * 32,
                created_at=second_created_at,
                withdrawn_at=withdrawn_at,
            ),
            Payment(
                job_id=jobs[2].id,
                user_id=customer.id,
                provider_id=other_provider.id,
                amount_base_units=999,
                payment_type="provider_credit",
                status="credited",
                blockchain_tx_hash="0x" + "cc" * 32,
            ),
        ]
    )
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/earnings", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "provider_id": str(provider.id),
        "total_credited_base_units": "125",
        "total_withdrawn_base_units": "50",
        "pending_withdrawal_base_units": None,
        "pending_withdrawal_status": "unavailable",
        "credits": [
            {
                "job_id": str(jobs[1].id),
                "amount_base_units": "50",
                "status": "withdrawn",
                "blockchain_tx_hash": "0x" + "bb" * 32,
                "withdrawal_tx_hash": "0x" + "dd" * 32,
                "credited_at": None,
                "withdrawn_at": withdrawn_at.isoformat().replace("+00:00", "Z"),
            },
            {
                "job_id": str(jobs[0].id),
                "amount_base_units": "75",
                "status": "credited",
                "blockchain_tx_hash": "0x" + "aa" * 32,
                "withdrawal_tx_hash": None,
                "credited_at": None,
                "withdrawn_at": None,
            },
        ],
    }


@pytest.mark.asyncio
async def test_earnings_rejects_non_provider(db):
    _, token = await seed_authed_user(db)
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/earnings", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "about:blank",
        "title": "Request failed",
        "status": 403,
        "detail": "Provider role required",
        "instance": "/v1/earnings",
    }


@pytest.mark.asyncio
async def test_provider_earnings_reads_pending_withdrawal_safely(db, monkeypatch):
    provider_id, token = await seed_authed_user(db)
    provider = (await db.execute(select(User).where(User.id == provider_id))).scalar_one()
    provider.role = "provider"
    provider.wallet_address = "0x" + "99" * 20
    await db.commit()
    contract = "0x" + "88" * 20
    blockchain = FakeBlockchainBackend()
    blockchain.set_contract_result(contract, encode(["uint256"], [321]))
    monkeypatch.setattr(app.state, "blockchain", blockchain)
    monkeypatch.setattr("app.routers.earnings.settings.NEBULA_PAYMENT_CONTRACT", contract)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/earnings", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["pending_withdrawal_base_units"] == "321"
    assert response.json()["pending_withdrawal_status"] == "current"


@pytest.mark.asyncio
async def test_withdrawal_event_projects_real_provider_credit_history(db):
    provider = User(wallet_address="0x" + "aa" * 20, role="provider")
    customer = User(wallet_address="0x" + "bb" * 20, role="user")
    model = SupportedModel(id="withdrawal-model", name="Withdrawal", price_base_units=100)
    db.add_all([provider, customer, model])
    await db.flush()
    job = Job(
        user_id=customer.id,
        model_id=model.id,
        chain_job_id="0x" + "12" * 32,
        price_base_units=100,
        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(job)
    await db.flush()
    payment = Payment(
        job_id=job.id,
        user_id=customer.id,
        provider_id=provider.id,
        amount_base_units=100,
        payment_type="provider_credit",
        status="credited",
        blockchain_tx_hash="0x" + "13" * 32,
        credited_at=datetime.now(timezone.utc),
    )
    event = BlockchainEvent(
        chain_id=421614,
        chain_instance_id="0x" + "14" * 32,
        contract_address="0x" + "15" * 20,
        transaction_hash="0x" + "16" * 32,
        log_index=0,
        block_number=123,
        block_hash="0x" + "17" * 32,
        event_name="WithdrawalCompleted",
        event_data={"provider": provider.wallet_address, "amount": 100, "_blockTimestamp": 1_700_000_000},
        confirmation_status="finalized",
    )
    credit_event = BlockchainEvent(
        chain_id=event.chain_id,
        chain_instance_id=event.chain_instance_id,
        contract_address=event.contract_address,
        transaction_hash=payment.blockchain_tx_hash,
        log_index=0,
        block_number=122,
        block_hash="0x" + "17" * 32,
        event_name="PaymentCredited",
        event_data={"provider": provider.wallet_address, "amount": 100},
        job_id=job.id,
        confirmation_status="finalized",
    )
    db.add_all([payment, credit_event, event])
    await db.flush()
    poller = EventPoller(
        blockchain=FakeBlockchainBackend(),
        chain_id=421614,
        contract_address=event.contract_address,
        deployment_block=0,
    )
    poller.chain_instance_id = event.chain_instance_id

    event.confirmation_status = "confirmed"
    await poller._project(db, event)
    assert payment.status == "credited"

    event.confirmation_status = "finalized"
    await poller._project(db, event)
    await poller._project(db, event)

    assert payment.status == "withdrawn"
    assert payment.withdrawal_tx_hash == event.transaction_hash
    assert payment.withdrawn_at == datetime.fromtimestamp(1_700_000_000, timezone.utc)


class WithdrawalReplayBackend(FakeBlockchainBackend):
    """Return an actual ABI-encoded historical withdrawal through the RPC seam."""

    def __init__(self, contract: str, provider: str, amount: int = 100):
        super().__init__()
        self.contract = contract
        self.provider = provider
        self.amount = amount

    def get_block_number(self):
        return 40

    def get_block(self, block_identifier):
        return {"number": block_identifier, "hash": b"\xab" * 32, "timestamp": 1_700_000_000}

    def get_abi(self):
        return json.loads((Path(__file__).parents[1] / "app/nebula_abi.json").read_text())

    def get_logs(self, filter_params):
        return [{
            "address": self.contract,
            "topics": [
                Web3.keccak(text="WithdrawalCompleted(address,uint256)"),
                bytes.fromhex(self.provider[2:]).rjust(32, b"\0"),
            ],
            "data": encode(["uint256"], [self.amount]),
            "blockNumber": 20,
            "blockHash": b"\xab" * 32,
            "transactionHash": b"\xcc" * 32,
            "transactionIndex": 0,
            "logIndex": 2,
        }]


async def seed_withdrawal_replay(db, credit_positions):
    provider_id, token = await seed_authed_user(db)
    provider = (await db.execute(select(User).where(User.id == provider_id))).scalar_one()
    provider.role = "provider"
    provider.wallet_address = "0x" + "aa" * 20
    model = SupportedModel(id="withdrawal-replay", name="Withdrawal replay", price_base_units=100)
    db.add(model)
    await db.flush()
    contract = "0x" + "88" * 20
    for (block, log_index), tx_byte in zip(credit_positions, ("11", "22", "33")[:len(credit_positions)], strict=True):
        job_id = uuid.uuid4()
        db.add(Job(
            id=job_id,
            user_id=provider_id,
            model_id=model.id,
            chain_job_id="0x" + job_id.hex + "00" * 16,
            price_base_units=100,
            deadline=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        await db.flush()
        db.add(Payment(
            job_id=job_id,
            user_id=provider_id,
            provider_id=provider_id,
            amount_base_units=100,
            payment_type="provider_credit",
            status="credited",
            blockchain_tx_hash="0x" + tx_byte * 32,
        ))
        db.add(BlockchainEvent(
            chain_id=421614,
            chain_instance_id="0x" + "ab" * 32,
            contract_address=contract,
            transaction_hash="0x" + tx_byte * 32,
            log_index=log_index,
            block_number=block,
            block_hash="0x" + "ab" * 32,
            event_name="PaymentCredited",
            event_data={"provider": provider.wallet_address, "amount": 100},
            job_id=job_id,
            confirmation_status="finalized",
        ))
    await db.commit()
    return contract, provider.wallet_address, token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "credit_positions",
    [((10, 0), (30, 0)), ((20, 1), (20, 3))],
    ids=("different-blocks", "same-block-log-order"),
)
async def test_historical_withdrawal_leaves_later_provider_credits_available(db, credit_positions):
    contract, provider_address, token = await seed_withdrawal_replay(db, credit_positions)
    poller = EventPoller(
        blockchain=WithdrawalReplayBackend(contract, provider_address),
        chain_id=421614,
        contract_address=contract,
        deployment_block=20,
        block_range=1,
        finality=1,
    )

    await poller.run_once(db)
    await db.commit()
    await poller.run_once(db)
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/earnings", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["total_credited_base_units"] == "200"
    assert body["total_withdrawn_base_units"] == "100"
    credits = {credit["blockchain_tx_hash"]: credit for credit in body["credits"]}
    assert credits["0x" + "11" * 32]["status"] == "withdrawn"
    assert credits["0x" + "11" * 32]["withdrawal_tx_hash"] == "0x" + "cc" * 32
    assert credits["0x" + "22" * 32]["status"] == "credited"
    assert credits["0x" + "22" * 32]["withdrawal_tx_hash"] is None


@pytest.mark.asyncio
async def test_historical_withdrawal_amount_mismatch_still_halts_projection(db):
    contract, provider_address, token = await seed_withdrawal_replay(db, ((10, 0), (30, 0)))
    poller = EventPoller(
        blockchain=WithdrawalReplayBackend(contract, provider_address, amount=99),
        chain_id=421614,
        contract_address=contract,
        deployment_block=20,
        block_range=1,
        finality=1,
    )

    with pytest.raises(CriticalReconciliationError, match="does not reconcile"):
        await poller.run_once(db)
    await db.rollback()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/earnings", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["total_withdrawn_base_units"] == "0"
    assert {credit["status"] for credit in response.json()["credits"]} == {"credited"}


@pytest.mark.asyncio
async def test_recorded_legacy_withdrawal_is_projected_before_newer_withdrawal(db):
    contract, provider_address, token = await seed_withdrawal_replay(db, ((4, 0), (10, 0), (30, 0)))
    # The old runner recorded this withdrawal and advanced its cursor without
    # projecting it; the new runner starts well after that historical block.
    db.add(BlockchainEvent(
        chain_id=421614,
        chain_instance_id="0x" + "ab" * 32,
        contract_address=contract,
        transaction_hash="0x" + "44" * 32,
        log_index=0,
        block_number=5,
        block_hash="0x" + "ab" * 32,
        event_name="WithdrawalCompleted",
        event_data={"provider": provider_address, "amount": 100, "_blockTimestamp": 1_699_999_990},
        confirmation_status="finalized",
    ))
    await db.commit()
    poller = EventPoller(
        blockchain=WithdrawalReplayBackend(contract, provider_address),
        chain_id=421614,
        contract_address=contract,
        deployment_block=20,
        block_range=1,
        finality=1,
    )

    await poller.run_once(db)
    await db.commit()
    await poller.run_once(db)
    await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/earnings", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["total_credited_base_units"] == "300"
    assert body["total_withdrawn_base_units"] == "200"
    credits = {credit["blockchain_tx_hash"]: credit for credit in body["credits"]}
    assert credits["0x" + "11" * 32]["withdrawal_tx_hash"] == "0x" + "44" * 32
    assert credits["0x" + "22" * 32]["withdrawal_tx_hash"] == "0x" + "cc" * 32
    assert credits["0x" + "33" * 32]["status"] == "credited"
