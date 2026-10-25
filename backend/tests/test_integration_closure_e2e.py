"""Authoritative PostgreSQL + Anvil + ASGI Integration Closure journeys."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from eth_account import Account
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from web3 import Web3

from app.database import get_db
from app.main import create_app
from app.models import (
    AuthSession,
    BlockchainEvent,
    ChainTransaction,
    Job,
    JobAttempt,
    Lease,
    Node,
    Proof,
    SupportedModel,
    User,
)
from app.services import settlement_coordinator as settlement_coordinator_module
from app.services.assignment_dispatcher import AssignmentDispatcher
from app.services.auth_service import create_access_token, sha256_hex
from app.services.blockchain_events import EventPoller, reconcile_job_state
from app.services.blockchain_service import BlockchainBackend, Web3Backend, read_contract_job
from app.services.scheduler import schedule_next_job
from app.services.settlement_coordinator import SettlementCoordinator
from app.services.storage import InMemoryStorage
from app.services.tx_signer import Web3Signer
from tests.vectors import PNG_1X1

ROOT = Path(__file__).parents[2]
KEYS = [
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "0x7c8521182947e51e653e45f9d6f78b5b4f2f2070c2a6c7c27b3f3f5b6a7e8f90",
]


def deploy(w3, artifact, args=()):
    data = json.loads(artifact.read_text())
    c = w3.eth.contract(abi=data["abi"], bytecode=data["bytecode"]["object"])
    receipt = w3.eth.wait_for_transaction_receipt(c.constructor(*args).transact({"from": w3.eth.accounts[0]}))
    return w3.eth.contract(address=receipt.contractAddress, abi=data["abi"]), receipt.blockNumber


class ResponseAdapter:
    def __init__(self, response):
        self.response = response

    def raise_for_status(self):
        self.response.raise_for_status()

    async def json(self):
        return self.response.json()

    async def read(self):
        return self.response.content


class SessionAdapter:
    """Let the real protocol worker execute through FastAPI's ASGI transport."""

    def __init__(self, client):
        self.client = client
        self.requests = []

    async def request(self, method, url, **kwargs):
        path = "/" + url.split("/", 3)[-1]
        self.requests.append((method, path, kwargs))
        return ResponseAdapter(await self.client.request(method, path, **kwargs))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "journey",
    ["valid", "invalid", "timeout", "refund_race"],
    ids=[
        "valid-provider-payment",
        "invalid-user-refund",
        "paused-timeout-refund",
        "user-refund-wins-settlement-race",
    ],
)
async def test_golden_connected_journey(
    monkeypatch: pytest.MonkeyPatch,
    unused_tcp_port: int,
    journey: str,
) -> None:
    raw = os.environ.get("DATABASE_URL", "")
    pg = (raw.rsplit("/", 1)[0] + "/nebula_test") if raw.startswith("postgresql") else None
    if not pg:
        pytest.skip("requires configured nebula_test PostgreSQL")
    rpc = f"http://127.0.0.1:{unused_tcp_port}"
    chain_id = 100_000 + unused_tcp_port
    proc = subprocess.Popen(
        [
            "anvil",
            "--port",
            str(unused_tcp_port),
            "--chain-id",
            str(chain_id),
            "--mnemonic",
            "test test test test test test test test test test test junk",
            "--silent",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        w3 = Web3(Web3.HTTPProvider(rpc))
        deadline = time.monotonic() + 5
        while not w3.is_connected():
            if proc.poll() is not None:
                stderr = proc.stderr.read().strip() if proc.stderr is not None else "stderr unavailable"
                raise RuntimeError(f"Anvil exited during startup: {stderr}")
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Anvil did not become ready at {rpc}")
            time.sleep(0.05)
        assert proc.poll() is None
        assert w3.eth.chain_id == chain_id
        usdc, _ = deploy(w3, ROOT / "contracts/out/NebulaVerifiableAI.t.sol/MockUSDC.json")
        nebula, deployment = deploy(
            w3, ROOT / "contracts/out/NebulaVerifiableAI.sol/NebulaVerifiableAI.json", (usdc.address,)
        )
        chain = Web3Backend(rpc)
        storage = InMemoryStorage()
        signer = Web3Signer(rpc, KEYS[0])
        from app.config import settings

        monkeypatch.setattr(settings, "CHAIN_ID", chain_id)
        monkeypatch.setattr(settings, "NEBULA_PAYMENT_CONTRACT", nebula.address)
        monkeypatch.setattr(settings, "BACKEND_EXECUTOR_ADDRESS", w3.eth.accounts[0])
        engine = create_async_engine(pg)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        # Migration correctness is established by the dedicated PostgreSQL suite.
        # This journey never drops or resets a shared test database.
        async with factory() as db:
            user = (
                await db.execute(select(User).where(User.wallet_address == w3.eth.accounts[1].lower()))
            ).scalar_one_or_none() or User(id=uuid.uuid4(), wallet_address=w3.eth.accounts[1].lower(), role="user")
            provider = (
                await db.execute(select(User).where(User.wallet_address == w3.eth.accounts[2].lower()))
            ).scalar_one_or_none() or User(id=uuid.uuid4(), wallet_address=w3.eth.accounts[2].lower(), role="provider")
            worker = Account.create()
            api_key = "golden-worker-" + uuid.uuid4().hex
            model_bytes = b"fixture-model-v1"
            input_bytes = PNG_1X1
            model = (
                await db.execute(select(SupportedModel).where(SupportedModel.id == "resnet50"))
            ).scalar_one_or_none() or SupportedModel(
                id="resnet50",
                name="R",
                price_base_units=50000,
                vram_required_gb=1,
                model_hash_sha256=hashlib.sha256(model_bytes).hexdigest(),
                model_version="1.0",
                preprocessing_version="resnet50-v1",
                model_source_url="models/resnet50",
            )
            model.name = "R"
            model.price_base_units = 50000
            model.vram_required_gb = 1
            model.model_hash_sha256 = hashlib.sha256(model_bytes).hexdigest()
            model.model_version = "1.0"
            model.preprocessing_version = "resnet50-v1"
            model.model_source_url = "models/resnet50"
            model.max_input_size_mb = 1
            model.supported_formats = ["png"]
            model.input_type = "image"
            node = Node(
                id=uuid.uuid4(),
                provider_id=provider.id,
                status="online",
                vram_gb=24,
                last_heartbeat=datetime.now(timezone.utc),
                worker_signer_address=worker.address,
                api_key_hash=hashlib.sha256(api_key.encode()).hexdigest(),
            )
            token = create_access_token(str(user.id), user.wallet_address, "user")
            session = (
                await db.execute(select(AuthSession).where(AuthSession.token_hash == sha256_hex(token)))
            ).scalar_one_or_none()
            db.add_all([user, provider, model, node])
            if session is None:
                db.add(
                    AuthSession(
                        user_id=user.id,
                        token_hash=sha256_hex(token),
                        refresh_token_hash=sha256_hex(uuid.uuid4().hex),
                        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                    )
                )
            await db.commit()
            await storage.put_object("models/resnet50", model_bytes)
            app = create_app(blockchain=chain, storage=storage)

            async def override():
                async with factory() as request_db:
                    try:
                        yield request_db
                        await request_db.commit()
                    except Exception:
                        await request_db.rollback()
                        raise

            app.dependency_overrides[get_db] = override
            headers = {"Authorization": f"Bearer {token}"}
            client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
            create_response = await client.post(
                "/v1/jobs",
                headers=headers,
                data={
                    "model_id": "resnet50",
                    "deadline": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                },
                files={"input_file": ("golden.png", input_bytes, "image/png")},
            )
            assert create_response.status_code == 200, create_response.text
            created = create_response.json()
            job_uuid = uuid.UUID(created["id"])
            assert created["price_base_units"] == "50000"
            async with factory() as assertion_db:
                created_job = (await assertion_db.execute(select(Job).where(Job.id == job_uuid))).scalar_one()
                assert created_job.input_hash == hashlib.sha256(input_bytes).hexdigest()
                assert created_job.input_file_key == f"inputs/{job_uuid}/input.png"
                assert created_job.expected_fingerprint == created["fingerprint"]
                assert await storage.get_object(created_job.input_file_key) == input_bytes
            price = nebula.functions.jobPrice().call()
            mint_tx = usdc.functions.mint(w3.eth.accounts[1], price).transact({"from": w3.eth.accounts[0]})
            assert w3.eth.wait_for_transaction_receipt(mint_tx)["status"] == 1
            approve_tx = usdc.functions.approve(nebula.address, price).transact({"from": w3.eth.accounts[1]})
            assert w3.eth.wait_for_transaction_receipt(approve_tx)["status"] == 1
            tx = nebula.functions.createJob(
                bytes.fromhex(created["chain_job_id"][2:]), bytes.fromhex(created["fingerprint"])
            ).transact({"from": w3.eth.accounts[1]})
            w3.eth.wait_for_transaction_receipt(tx)
            w3.provider.make_request("evm_mine", [])
            assert (
                await client.post(f"/v1/jobs/{job_uuid}/confirm-escrow", headers=headers, json={"tx_hash": tx.hex()})
            ).status_code == 200
            for _ in range(100):
                scheduled = await schedule_next_job(db)
                if scheduled and scheduled[0].id == job_uuid:
                    break
            assert scheduled and scheduled[0].id == job_uuid
            await db.commit()
            dispatcher = AssignmentDispatcher(
                blockchain=chain, signer=signer, contract_address=nebula.address, chain_id=chain_id, rpc_url=rpc
            )
            await db.commit()

            async def dispatch_once():
                async with factory() as runner_db:
                    result = await dispatcher.dispatch_pending_assignments(runner_db)
                    await runner_db.commit()
                    return result

            dispatch_results = await asyncio.gather(dispatch_once(), dispatch_once())
            dispatched_ids = [lease_id for result in dispatch_results for lease_id in result]
            assert dispatched_ids.count(str(scheduled[2].id)) == 1
            intent = (
                await db.execute(
                    select(ChainTransaction).where(
                        ChainTransaction.tx_type == "assignProvider", ChainTransaction.job_id == job_uuid
                    )
                )
            ).scalar_one()
            assert intent.status == "submitted"
            confirmed_assignment = await dispatcher.confirm_assignment(
                db, lease_id=intent.lease_id, tx_hash=intent.tx_hash, block_number=0, block_hash=""
            )
            await db.commit()
            lease = (await db.execute(select(Lease).where(Lease.id == intent.lease_id))).scalar_one()
            assert nebula.functions.verifier().call().lower() == signer.get_address().lower()
            assert confirmed_assignment is True
            attempt = (await db.execute(select(JobAttempt).where(JobAttempt.lease_id == lease.id))).scalar_one()
            wh = {"X-API-Key": api_key}
            assert (await client.post(f"/v1/worker/nodes/{node.id}/heartbeat", headers=wh)).status_code == 200
            if journey == "timeout":
                on_chain = read_contract_job(chain, nebula.address, bytes.fromhex(created["chain_job_id"][2:]))
                nebula.functions.pause().transact({"from": w3.eth.accounts[0]})
                latest_timestamp = w3.eth.get_block("latest")["timestamp"]
                w3.provider.make_request(
                    "evm_increaseTime",
                    [int(on_chain["job_deadline"]) - int(latest_timestamp) + 1],
                )
                w3.provider.make_request("evm_mine", [])
                refund_tx = nebula.functions.requestTimeoutRefund(bytes.fromhex(created["chain_job_id"][2:])).transact(
                    {"from": w3.eth.accounts[1]}
                )
                w3.eth.wait_for_transaction_receipt(refund_tx)
            else:
                lease_payload = (await client.post("/v1/worker/leases/next", headers=wh)).json()["lease"]
                assert lease_payload["lease_id"] == str(lease.id)
                assert lease_payload["attempt_id"] == str(attempt.id)

                sys.path.insert(0, str(ROOT / "worker"))
                from core.executor import JobExecutor

                worker_settings = SimpleNamespace(
                    BACKEND_URL="http://test",
                    API_KEY=api_key,
                    CHAIN_ID=chain_id,
                    VERIFYING_CONTRACT=nebula.address,
                    PRIVATE_KEY=worker.key.hex(),
                )
                protocol_worker = JobExecutor(worker_settings)
                adapter = SessionAdapter(client)
                protocol_worker.session = adapter
                await protocol_worker.execute(lease_payload)
                await db.refresh(node)
                assert node.active_leases == 1
                complete_call = next(call for call in reversed(adapter.requests) if call[1].endswith("/complete"))
                duplicate = await client.request(
                    complete_call[0], complete_call[1], headers=wh, json=complete_call[2]["json"]
                )
                assert duplicate.status_code == 202
                output = await storage.get_object(complete_call[2]["json"]["result_file_key"])
                if journey == "invalid":
                    await storage.put_object(complete_call[2]["json"]["result_file_key"], output + b"tampered")

                await db.commit()

                refund_task = None
                if journey == "refund_race":
                    target_job_id = bytes.fromhex(created["chain_job_id"][2:])
                    settlement_ready = threading.Event()
                    refund_done = threading.Event()
                    original_read_contract_job = settlement_coordinator_module.read_contract_job

                    def read_after_refund(
                        blockchain: BlockchainBackend,
                        contract_address: str,
                        job_id: bytes,
                    ) -> dict[str, Any]:
                        if job_id == target_job_id and not refund_done.is_set():
                            settlement_ready.set()
                            if not refund_done.wait(timeout=5):
                                raise RuntimeError("refund did not complete during settlement race")
                        return original_read_contract_job(blockchain, contract_address, job_id)

                    monkeypatch.setattr(settlement_coordinator_module, "read_contract_job", read_after_refund)

                    def refund_when_settlement_checks_chain() -> None:
                        if not settlement_ready.wait(timeout=5):
                            raise RuntimeError("settlement did not reach its pre-broadcast chain check")
                        try:
                            on_chain = read_contract_job(chain, nebula.address, target_job_id)
                            latest_timestamp = w3.eth.get_block("latest")["timestamp"]
                            w3.provider.make_request(
                                "evm_increaseTime",
                                [int(on_chain["job_deadline"]) - int(latest_timestamp) + 1],
                            )
                            w3.provider.make_request("evm_mine", [])
                            refund_tx = nebula.functions.requestTimeoutRefund(target_job_id).transact(
                                {"from": w3.eth.accounts[1]}
                            )
                            assert w3.eth.wait_for_transaction_receipt(refund_tx)["status"] == 1
                        finally:
                            refund_done.set()

                    refund_task = asyncio.create_task(asyncio.to_thread(refund_when_settlement_checks_chain))
                    await asyncio.sleep(0)

                async def settle_once():
                    async with factory() as runner_db:
                        coordinator = SettlementCoordinator(
                            blockchain=chain,
                            signer=signer,
                            storage=storage,
                            contract_address=nebula.address,
                            chain_id=chain_id,
                        )
                        return await coordinator.run_once(runner_db)

                settlement_results = await asyncio.gather(settle_once(), settle_once())
                if refund_task is not None:
                    await refund_task
                assert sum(result["verified"] for result in settlement_results) == 1
                restarted_coordinator = SettlementCoordinator(
                    blockchain=chain,
                    signer=signer,
                    storage=storage,
                    contract_address=nebula.address,
                    chain_id=chain_id,
                )
                coordinator_results = list(settlement_results)
                for _ in range(3):
                    result = await restarted_coordinator.run_once(db)
                    coordinator_results.append(result)
                    if result == {"verified": 0, "broadcast": 0, "confirmed": 0}:
                        break
                assert coordinator_results[-1] == {
                    "verified": 0,
                    "broadcast": 0,
                    "confirmed": 0,
                }
                if journey == "refund_race":
                    assert sum(result["confirmed"] for result in coordinator_results) == 0
            poller = EventPoller(
                blockchain=chain,
                chain_id=chain_id,
                contract_address=nebula.address,
                deployment_block=deployment,
                confirmations=1,
                finality=1,
            )
            await poller.run_once(db)
            await db.commit()
            await db.refresh(node)
            assert node.active_leases == 0
            event_count = (
                await db.execute(select(func.count(BlockchainEvent.id)).where(BlockchainEvent.job_id == job_uuid))
            ).scalar_one()
            restarted_poller = EventPoller(
                blockchain=chain,
                chain_id=chain_id,
                contract_address=nebula.address,
                deployment_block=deployment,
                confirmations=1,
                finality=1,
            )
            await restarted_poller.run_once(db)
            await db.commit()
            assert (
                await db.execute(select(func.count(BlockchainEvent.id)).where(BlockchainEvent.job_id == job_uuid))
            ).scalar_one() == event_count
            final = (await client.get(f"/v1/jobs/{job_uuid}", headers=headers)).json()
            expected_status = "completed" if journey == "valid" else "refunded"
            expected_chain_state = "Settled" if journey == "valid" else "Refunded"
            assert final["status"] == expected_status and final["on_chain_state"] == expected_chain_state
            assert final["reconciliation_health"] == "match"
            assert final["attempt_count"] == 1
            assert final["current_lease_status"] == ("completed" if journey == "valid" else "failed")
            expected_proof_status = (
                None if journey == "timeout" else "valid" if journey in ("valid", "refund_race") else "invalid"
            )
            assert final["proof_verification_status"] == expected_proof_status
            assert final["escrow_transaction"]["status"] in ("confirmed", "finalized")
            assert final["assignment_transaction"]["status"] in ("confirmed", "finalized")
            downloaded = await client.get(f"/v1/jobs/{job_uuid}/result", headers=headers)
            if journey in ("valid", "refund_race"):
                assert downloaded.status_code == 200
                assert downloaded.content == output
            elif journey == "invalid":
                assert downloaded.status_code == 503
            else:
                assert downloaded.status_code == 404
            if journey == "timeout":
                assert final["proof_transaction"] is None
                assert final["settlement_transaction"] is None
            elif journey == "refund_race":
                # The refund wins before proof broadcast: the abandoned intent
                # is durable, but there is no transaction hash to expose as
                # on-chain evidence in the API response.
                proof_intent = (
                    await db.execute(
                        select(ChainTransaction).where(
                            ChainTransaction.job_id == job_uuid,
                            ChainTransaction.tx_type == "submitProof",
                        )
                    )
                ).scalar_one()
                assert proof_intent.status == "replaced"
                assert proof_intent.tx_hash is None
                assert final["proof_transaction"] is None
                assert final["settlement_transaction"] is None
            else:
                assert final["proof_transaction"]["status"] in ("confirmed", "finalized")
                assert final["settlement_transaction"]["status"] in ("confirmed", "finalized")
                proof = (await db.execute(select(Proof).where(Proof.job_attempt_id == attempt.id))).scalar_one()
                assert proof.valid is (journey in ("valid", "refund_race"))
            contract_job = read_contract_job(chain, nebula.address, bytes.fromhex(created["chain_job_id"][2:]))
            assert contract_job["state"] == (4 if journey == "valid" else 5)
            beneficiary = w3.eth.accounts[2] if journey == "valid" else w3.eth.accounts[1]
            assert nebula.functions.getPendingWithdrawal(beneficiary).call() == price
            before = usdc.functions.balanceOf(beneficiary).call()
            withdrawal = nebula.functions.withdraw().transact({"from": beneficiary})
            w3.eth.wait_for_transaction_receipt(withdrawal)
            assert nebula.functions.getPendingWithdrawal(beneficiary).call() == 0
            assert usdc.functions.balanceOf(beneficiary).call() == before + price
            assert (await reconcile_job_state(db, job_uuid))["status"] == "match"
            persisted_job = (await db.execute(select(Job).where(Job.id == job_uuid))).scalar_one()
            assert persisted_job.status == expected_status
            assert persisted_job.completed_at is not None
            assert persisted_job.completed_at > datetime(2020, 1, 1, tzinfo=timezone.utc)
            await db.refresh(attempt)
            await db.refresh(node)
            assert attempt.status == ("completed" if journey == "valid" else "failed")
            assert node.active_leases == 0
            await client.aclose()
        await engine.dispose()
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
