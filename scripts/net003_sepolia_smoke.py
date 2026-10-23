#!/usr/bin/env python3
"""Run NET-003 against the deployed Arbitrum Sepolia contract.

This is an operator harness, not a normal test-suite member. It uses public HTTP
interfaces for both journeys and starts the API, five runners, and worker as
independent processes. Direct database access is limited to provisioning the
static model registry and to final read-only assertions.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values
from eth_account import Account
from eth_account.messages import encode_defunct
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from web3 import Web3

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
WORKER = ROOT / "worker"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(WORKER))

from app.models import (
    BlockchainEvent,
    ChainCursor,
    ChainTransaction,
    Job,
    JobAttempt,
    Lease,
    Proof,
    ReconciliationIncident,
    SupportedModel,
)
from app.services.storage import StorageRuntimeConfig, build_storage

API = "http://127.0.0.1:8013"
MODEL_ID = "resnet50"
MODEL_BYTES = b"nebula-net003-fixture-model-v1"
PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000000020001e221bc330000000049454e44ae426082"
)
LOG_DIR = Path("/tmp/nebula-net003-logs")
SETTLED_STATE = 4
PROCESS_ENV_ALLOWLIST = (
    "PATH",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
)


def process_base_environment() -> dict[str, str]:
    """Pass only non-secret process plumbing from the operator environment."""
    return {key: os.environ[key] for key in PROCESS_ENV_ALLOWLIST if key in os.environ}


def build_smoke_storage(env: dict[str, str]):
    """Build the configured smoke storage without changing local harness behavior."""
    if env.get("STORAGE_ADAPTER") == "s3":
        config = StorageRuntimeConfig(
            adapter="s3",
            bucket=env["R2_BUCKET_NAME"],
            endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            region=env.get("OBJECT_STORAGE_REGION", "auto"),
            access_key_id=env["R2_ACCESS_KEY_ID"],
            secret_access_key=env["R2_SECRET_ACCESS_KEY"],
            key_prefix=env.get("OBJECT_STORAGE_PREFIX", ""),
        )
    else:
        config = StorageRuntimeConfig(
            adapter="file", local_root=env["LOCAL_STORAGE_PATH"]
        )
    return build_storage(config)


def load_environment() -> dict[str, str]:
    """Load ignored NET003 environment files without logging secret values."""
    values: dict[str, str] = dict(os.environ)
    configured_from_environment = values.get("NET003_CONFIG_FROM_ENV") == "true"
    for path in (BACKEND / ".env.sepolia", ROOT / "contracts/.env.net003"):
        if not path.exists() and not configured_from_environment:
            raise RuntimeError(f"missing required ignored environment file: {path}")
        if not path.exists():
            continue
        values.update(
            {
                key: value
                for key, value in dotenv_values(path).items()
                if value is not None
            }
        )
    values.update(
        {
            "EVENT_BLOCK_RANGE": "500",
            "CONFIRMATION_DEPTH": "1",
            "FINALITY_DEPTH": "1",
            "RUNNER_POLL_INTERVAL_SECONDS": "2",
            "PYTHONUNBUFFERED": "1",
        }
    )
    return values


async def provision_static_model(env: dict[str, str]) -> None:
    """Provision only the isolated smoke model metadata and fixture artifact."""
    if env.get("STORAGE_ADAPTER") == "s3":
        storage = build_smoke_storage(env)
        await storage.put_object_once(
            f"models/{MODEL_ID}", MODEL_BYTES, "application/octet-stream"
        )
    else:
        local_storage = Path(env["LOCAL_STORAGE_PATH"])
        artifact = local_storage / "models" / MODEL_ID
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(MODEL_BYTES)
    engine = create_async_engine(env["DATABASE_URL"])
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        model = await db.get(SupportedModel, MODEL_ID)
        if model is None:
            model = SupportedModel(id=MODEL_ID, name="NET003 deterministic fixture")
            db.add(model)
        model.price_base_units = 50_000
        model.vram_required_gb = 1
        model.model_hash_sha256 = hashlib.sha256(MODEL_BYTES).hexdigest()
        model.model_version = "1.0"
        model.preprocessing_version = "resnet50-v1"
        model.model_source_url = f"models/{MODEL_ID}"
        model.max_input_size_mb = 1
        model.supported_formats = ["png"]
        model.input_type = "image"
        await db.commit()
    await engine.dispose()


def start_process(
    command: list[str], cwd: Path, env: dict[str, str], name: str
) -> subprocess.Popen[bytes]:
    """Start one independently stoppable runtime process with a local log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    LOG_DIR.chmod(0o700)
    log_path = LOG_DIR / f"{name}.log"
    log = log_path.open("ab")
    log_path.chmod(0o600)
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def stop_processes(processes: list[subprocess.Popen[bytes]]) -> None:
    """Terminate every runtime process started by this harness."""
    for process in reversed(processes):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and any(
        process.poll() is None for process in processes
    ):
        time.sleep(0.1)
    for process in reversed(processes):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)


def handle_termination(_signum: int, _frame: Any) -> None:
    """Unwind through ``main`` so its child-process cleanup always executes."""
    raise KeyboardInterrupt


async def wait_for_api(client: httpx.AsyncClient) -> None:
    """Wait for the API readiness interface with a bounded timeout."""
    for _ in range(60):
        try:
            response = await client.get("/ready")
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1)
    raise RuntimeError(
        "API did not become ready; inspect /tmp/nebula-net003-logs/api.log"
    )


async def authenticate(
    client: httpx.AsyncClient, private_key: str, frontend_origin: str
) -> tuple[str, str]:
    """Authenticate through the public wallet challenge interface."""
    account = Account.from_key(private_key)
    wallet = account.address.lower()
    challenge = await client.post("/v1/auth/challenge", json={"wallet_address": wallet})
    challenge.raise_for_status()
    body = challenge.json()
    signature = Account.sign_message(
        encode_defunct(text=body["challenge"]), private_key
    ).signature.hex()
    verified = await client.post(
        "/v1/auth/verify",
        json={"wallet_address": wallet, "signature": signature, "nonce": body["nonce"]},
        headers={"Origin": frontend_origin},
    )
    verified.raise_for_status()
    return wallet, verified.json()["access_token"]


def send_transaction(
    w3: Web3, private_key: str, tx: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Sign, broadcast, and require a successful real-chain receipt."""
    account = Account.from_key(private_key)
    tx.setdefault("from", account.address)
    tx.setdefault("nonce", w3.eth.get_transaction_count(account.address, "pending"))
    tx.setdefault("chainId", w3.eth.chain_id)
    if "gasPrice" not in tx and "maxFeePerGas" not in tx:
        tx["gasPrice"] = w3.eth.gas_price
    if "gas" not in tx:
        tx["gas"] = int(w3.eth.estimate_gas(tx) * 12 // 10)
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = dict(w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180))
    if receipt["status"] != 1:
        raise RuntimeError(f"transaction reverted: {tx_hash.hex()}")
    return tx_hash.hex(), receipt


async def create_and_wait(
    client: httpx.AsyncClient,
    w3: Web3,
    nebula,
    usdc,
    user_key: str,
    token: str,
    sequence: int,
) -> dict[str, Any]:
    """Execute one public API-to-chain journey and return public evidence."""
    started_at = time.monotonic()
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": f"net003-{uuid.uuid4()}",
    }
    created_response = await client.post(
        "/v1/jobs",
        headers=headers,
        data={
            "model_id": MODEL_ID,
            "deadline": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        files={"input_file": (f"net003-{sequence}.png", PNG_1X1, "image/png")},
    )
    if created_response.is_error:
        raise RuntimeError(
            f"job creation failed: {created_response.status_code} {created_response.text}"
        )
    created = created_response.json()
    price = int(created["price_base_units"])
    user = Account.from_key(user_key).address
    if usdc.functions.allowance(user, nebula.address).call() < price:
        approval_tx = usdc.functions.approve(
            nebula.address, price * 2
        ).build_transaction({"from": user})
        send_transaction(w3, user_key, approval_tx)
    chain_id = bytes.fromhex(created["chain_job_id"].removeprefix("0x"))
    fingerprint = bytes.fromhex(created["fingerprint"].removeprefix("0x"))
    escrow_hash, escrow_receipt = send_transaction(
        w3,
        user_key,
        nebula.functions.createJob(chain_id, fingerprint).build_transaction(
            {"from": user}
        ),
    )
    confirmation = await client.post(
        f"/v1/jobs/{created['id']}/confirm-escrow",
        headers=headers,
        json={"tx_hash": escrow_hash},
    )
    confirmation.raise_for_status()
    deadline = time.monotonic() + 600
    latest = None
    while time.monotonic() < deadline:
        response = await client.get(f"/v1/jobs/{created['id']}", headers=headers)
        response.raise_for_status()
        latest = response.json()
        if (
            latest["status"] == "completed"
            and latest["reconciliation_health"] == "match"
        ):
            break
        await asyncio.sleep(3)
    else:
        raise RuntimeError(f"journey {sequence} did not reconcile: {latest}")
    downloaded = await client.get(f"/v1/jobs/{created['id']}/result", headers=headers)
    downloaded.raise_for_status()
    on_chain = nebula.functions.getJob(chain_id).call()
    if on_chain[-1] != SETTLED_STATE or on_chain[0].lower() != user.lower():
        raise RuntimeError(f"journey {sequence} contract projection mismatch")
    return {
        "uuid": created["id"],
        "chain_job_id": created["chain_job_id"],
        "escrow_tx": escrow_hash,
        "escrow_block": escrow_receipt["blockNumber"],
        "duration_seconds": round(time.monotonic() - started_at, 3),
        "result_sha256": hashlib.sha256(downloaded.content).hexdigest(),
        "final": latest,
    }


async def assert_database(
    env: dict[str, str], journeys: list[dict[str, Any]]
) -> dict[str, Any]:
    """Assert each journey's PostgreSQL, receipt, event, and cursor evidence."""
    engine = create_async_engine(env["DATABASE_URL"])
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = [uuid.UUID(item["uuid"]) for item in journeys]
    async with factory() as db:
        jobs = (await db.execute(select(Job).where(Job.id.in_(ids)))).scalars().all()
        txs = (
            (
                await db.execute(
                    select(ChainTransaction).where(ChainTransaction.job_id.in_(ids))
                )
            )
            .scalars()
            .all()
        )
        leases = (
            (await db.execute(select(Lease).where(Lease.job_id.in_(ids))))
            .scalars()
            .all()
        )
        proofs = (
            (
                await db.execute(
                    select(Proof).join(JobAttempt).where(JobAttempt.job_id.in_(ids))
                )
            )
            .scalars()
            .all()
        )
        event_rows = (
            (
                await db.execute(
                    select(BlockchainEvent).where(BlockchainEvent.job_id.in_(ids))
                )
            )
            .scalars()
            .all()
        )
        incidents = (
            await db.execute(
                select(func.count(ReconciliationIncident.id)).where(
                    ReconciliationIncident.chain_id == int(env["CHAIN_ID"]),
                    ReconciliationIncident.contract_address
                    == env["NEBULA_PAYMENT_CONTRACT"],
                    ReconciliationIncident.status == "open",
                )
            )
        ).scalar_one()
        cursor = (await db.execute(select(ChainCursor))).scalars().first()
        if len(jobs) != 2 or any(job.status != "completed" for job in jobs):
            raise RuntimeError("database jobs did not both complete")
        if len(leases) != 2 or any(lease.status != "completed" for lease in leases):
            raise RuntimeError("database leases did not both complete")
        if len(proofs) != 2 or any(proof.valid is not True for proof in proofs):
            raise RuntimeError("database proofs did not both verify")
        if incidents != 0 or cursor is None:
            raise RuntimeError("reconciliation incident or missing chain cursor")
        required = {"createJob", "assignProvider", "submitProof", "verifyJob"}
        required_events = {
            "JobCreated",
            "ProviderAssigned",
            "ProofSubmitted",
            "PaymentCredited",
            "JobSettled",
        }
        evidence: dict[str, Any] = {}
        verifier_nonces: list[int] = []
        for job_id in ids:
            job_txs = [
                tx
                for tx in txs
                if tx.job_id == job_id and tx.status in {"confirmed", "finalized"}
            ]
            tx_types = {tx.tx_type for tx in job_txs}
            if not required.issubset(tx_types):
                raise RuntimeError(
                    f"job {job_id} missing confirmed transaction types: {required - tx_types}"
                )
            job_events = [event for event in event_rows if event.job_id == job_id]
            event_names = {event.event_name for event in job_events}
            if not required_events.issubset(event_names):
                raise RuntimeError(
                    f"job {job_id} missing events: {required_events - event_names}"
                )
            for tx in job_txs:
                if tx.tx_type != "createJob" and tx.nonce is not None:
                    verifier_nonces.append(tx.nonce)
            evidence[str(job_id)] = {
                "transactions": {
                    tx.tx_type: {
                        "hash": tx.tx_hash,
                        "block": tx.block_number,
                        "status": tx.status,
                        "nonce": tx.nonce,
                    }
                    for tx in job_txs
                },
                "events": sorted(event_names),
            }
        if len(verifier_nonces) != len(set(verifier_nonces)):
            raise RuntimeError("verifier nonce was reused across the two journeys")
        if cursor.last_scanned_block < max(tx.block_number or 0 for tx in txs):
            raise RuntimeError(
                "event cursor did not advance through the journey receipts"
            )
        storage = build_smoke_storage(env)
        input_hashes: dict[str, str] = {}
        for job in jobs:
            downloaded_input = await storage.get_object(job.input_file_key)
            downloaded_hash = hashlib.sha256(downloaded_input).hexdigest()
            if downloaded_hash != job.input_hash:
                raise RuntimeError(f"job {job.id} private input hash mismatch")
            input_hashes[str(job.id)] = downloaded_hash
        result = {
            "jobs": len(jobs),
            "leases": len(leases),
            "proofs": len(proofs),
            "events": len(event_rows),
            "cursor_block": cursor.last_scanned_block,
            "journey_evidence": evidence,
            "input_sha256": input_hashes,
        }
    await engine.dispose()
    return result


async def main() -> None:
    """Run the bounded NET003 topology and print a sanitized evidence record."""
    env = load_environment()
    await provision_static_model(env)
    w3 = Web3(
        Web3.HTTPProvider(env["ARBITRUM_SEPOLIA_RPC"], request_kwargs={"timeout": 20})
    )
    if not w3.is_connected() or w3.eth.chain_id != 421614:
        raise RuntimeError("Arbitrum Sepolia preflight failed")
    event_w3 = Web3(
        Web3.HTTPProvider(
            "https://sepolia-rollup.arbitrum.io/rpc", request_kwargs={"timeout": 20}
        )
    )
    if not event_w3.is_connected() or event_w3.eth.chain_id != w3.eth.chain_id:
        raise RuntimeError(
            "official event-backfill RPC does not match the configured chain"
        )
    abi = json.loads((BACKEND / "app/nebula_abi.json").read_text())
    nebula = w3.eth.contract(
        address=Web3.to_checksum_address(env["NEBULA_PAYMENT_CONTRACT"]), abi=abi
    )
    erc20_abi = json.loads(
        """[
        {"type":"function","name":"approve","stateMutability":"nonpayable",
         "inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],
         "outputs":[{"type":"bool"}]},
        {"type":"function","name":"allowance","stateMutability":"view",
         "inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],
         "outputs":[{"type":"uint256"}]},
        {"type":"function","name":"balanceOf","stateMutability":"view",
         "inputs":[{"name":"owner","type":"address"}],"outputs":[{"type":"uint256"}]}
        ]"""
    )
    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(env["USDC_SEPOLIA_ADDRESS"]), abi=erc20_abi
    )
    processes: list[subprocess.Popen[bytes]] = []
    python = str(BACKEND / ".venv/bin/python")
    api_origin = env.get("NET003_API_ORIGIN", API).rstrip("/")
    try:
        if env.get("NET003_START_LOCAL_API", "true") == "true":
            api_command = [
                python,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8013",
            ]
            processes.append(start_process(api_command, BACKEND, env, "api"))
        async with httpx.AsyncClient(base_url=api_origin, timeout=30) as client:
            await wait_for_api(client)
            _, provider_token = await authenticate(
                client, env["NET003_PROVIDER_PRIVATE_KEY"], env["FRONTEND_URL"]
            )
            _, user_token = await authenticate(
                client, env["NET003_AI_USER_PRIVATE_KEY"], env["FRONTEND_URL"]
            )
            node_response = await client.post(
                "/v1/nodes",
                headers={"Authorization": f"Bearer {provider_token}"},
                json={
                    "gpu_name": "NET003 fixture",
                    "vram_gb": 24,
                    "location": "testnet",
                    "worker_signer_address": env["NET003_WORKER_SIGNER_ADDRESS"],
                },
            )
            node_response.raise_for_status()
            node = node_response.json()
            for runner in (
                "receipts",
                "assignment",
                "settlement",
                "events",
                "reconciliation",
            ):
                runner_env = process_base_environment()
                runner_env.update(
                    {
                        key: env[key]
                        for key in (
                            "DATABASE_URL",
                            "JWT_SECRET",
                            "FRONTEND_URL",
                            "ARBITRUM_SEPOLIA_RPC",
                            "NEBULA_PAYMENT_CONTRACT",
                            "CONTRACT_DEPLOYMENT_BLOCK",
                            "CONTRACT_VERIFIER_ADDRESS",
                            "R2_ACCOUNT_ID",
                            "R2_BUCKET_NAME",
                            "R2_ACCESS_KEY_ID",
                            "R2_SECRET_ACCESS_KEY",
                            "OBJECT_STORAGE_PREFIX",
                            "BACKEND_PRIVATE_KEY",
                            "BACKEND_EXECUTOR_ADDRESS",
                            "CHAIN_ID",
                            "USDC_SEPOLIA_ADDRESS",
                            "STORAGE_ADAPTER",
                            "OBJECT_STORAGE_REGION",
                            "RUNNERS_ENABLED",
                            "CONFIRMATION_DEPTH",
                            "FINALITY_DEPTH",
                            "EVENT_BLOCK_RANGE",
                            "RUNNER_POLL_INTERVAL_SECONDS",
                            "PYTHONUNBUFFERED",
                        )
                    }
                )
                if runner == "events":
                    runner_env["ARBITRUM_SEPOLIA_RPC"] = (
                        "https://sepolia-rollup.arbitrum.io/rpc"
                    )
                    runner_env["EVENT_BLOCK_RANGE"] = "10000"
                    runner_env["RUNNER_POLL_INTERVAL_SECONDS"] = "0.05"
                processes.append(
                    start_process(
                        [python, "-m", "app.runners", runner],
                        BACKEND,
                        runner_env,
                        f"runner-{runner}",
                    )
                )
            worker_env = process_base_environment()
            worker_env.update(
                {
                    "NODE_ID": node["node_id"],
                    "API_KEY": node["api_key"],
                    "PRIVATE_KEY": env["NET003_WORKER_PRIVATE_KEY"],
                    "BACKEND_URL": api_origin,
                    "VERIFYING_CONTRACT": env["NEBULA_PAYMENT_CONTRACT"],
                    "EXECUTOR_ADAPTER": "fixture",
                    "EXECUTOR_DEVICE": "cpu",
                    "POLL_INTERVAL_SECONDS": "2",
                    "CHAIN_ID": env["CHAIN_ID"],
                }
            )
            processes.append(
                start_process([python, "worker.py"], WORKER, worker_env, "worker")
            )
            provider = Web3.to_checksum_address(env["NET003_PROVIDER_ADDRESS"])
            pending_before = nebula.functions.getPendingWithdrawal(provider).call()
            journeys = [
                await create_and_wait(
                    client,
                    w3,
                    nebula,
                    usdc,
                    env["NET003_AI_USER_PRIVATE_KEY"],
                    user_token,
                    i,
                )
                for i in (1, 2)
            ]
            if journeys[0]["uuid"] == journeys[1]["uuid"]:
                raise RuntimeError("journeys did not use distinct UUIDs")
            database = await assert_database(env, journeys)
            for journey in journeys:
                journey["input_sha256"] = database["input_sha256"][journey["uuid"]]
            pending = nebula.functions.getPendingWithdrawal(provider).call()
            expected = pending_before + nebula.functions.jobPrice().call() * 2
            if pending != expected:
                raise RuntimeError(
                    f"provider pending withdrawal mismatch: {pending} != {expected}"
                )
            before = usdc.functions.balanceOf(provider).call()
            withdrawal_hash, withdrawal_receipt = send_transaction(
                w3,
                env["NET003_PROVIDER_PRIVATE_KEY"],
                nebula.functions.withdraw().build_transaction({"from": provider}),
            )
            after = usdc.functions.balanceOf(provider).call()
            if (
                nebula.functions.getPendingWithdrawal(provider).call() != 0
                or after - before != expected
            ):
                raise RuntimeError(
                    "provider withdrawal did not conserve credited amount"
                )
            result = {
                "status": "passed",
                "chain_id": w3.eth.chain_id,
                "contract": nebula.address,
                "journeys": [
                    {
                        k: item[k]
                        for k in (
                            "uuid",
                            "chain_job_id",
                            "escrow_tx",
                            "escrow_block",
                            "input_sha256",
                            "result_sha256",
                        )
                    }
                    for item in journeys
                ],
                "database": database,
                "journey_provider_credit": nebula.functions.jobPrice().call() * 2,
                "provider_withdrawal_amount": expected,
                "withdrawal_tx": withdrawal_hash,
                "withdrawal_block": withdrawal_receipt["blockNumber"],
                "logs": str(LOG_DIR),
            }
            print(json.dumps(result, indent=2))
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_termination)
    asyncio.run(main())
