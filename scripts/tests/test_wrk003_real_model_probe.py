import hashlib
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from eth_account import Account

from scripts.net003_sepolia_smoke import (
    MODEL_BYTES,
    PNG_1X1,
    ROOT,
    SETTLED_STATE,
    create_and_wait,
    preflight_worker,
    require_matching_existing_model,
    resolve_model_artifact,
)


def test_live_probe_input_decodes_through_real_worker() -> None:
    """Exercise the exact uploaded bytes through the actual worker decoder."""
    result = subprocess.run(
        [
            str(ROOT / "worker/.venv/bin/python"),
            "-c",
            (
                "import sys; from core.resnet50_executor import preprocess_resnet50; "
                "assert tuple(preprocess_resnet50(sys.stdin.buffer.read()).shape) == (1, 3, 224, 224)"
            ),
        ],
        cwd=ROOT / "worker",
        input=PNG_1X1,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()


def test_fixture_mode_remains_the_default() -> None:
    payload, name, vram = resolve_model_artifact({})
    assert payload == MODEL_BYTES
    assert name == "NET003 deterministic fixture"
    assert vram == 1


def test_existing_approved_model_keeps_its_deployed_upload_limit() -> None:
    digest = "ab" * 32
    key = f"models/resnet50/{digest}.safetensors"
    existing = SimpleNamespace(
        model_hash_sha256=digest,
        model_source_url=key,
        model_version="1.0",
        preprocessing_version="resnet50-v1",
        price_base_units=50_000,
        input_type="image",
        max_input_size_mb=25,
    )
    require_matching_existing_model(existing, digest, key)
    assert existing.max_input_size_mb == 25


def test_live_probe_rejects_different_model_artifact_before_writes() -> None:
    existing = SimpleNamespace(
        model_hash_sha256="ab" * 32,
        model_source_url="models/resnet50/approved.safetensors",
        model_version="1.0",
        preprocessing_version="resnet50-v1",
        price_base_units=50_000,
        input_type="image",
    )
    with pytest.raises(RuntimeError, match="existing ResNet50 registry"):
        require_matching_existing_model(existing, "cd" * 32, "models/resnet50/new.safetensors")


def test_real_model_requires_verified_safetensors(tmp_path: Path) -> None:
    artifact = tmp_path / "resnet50.safetensors"
    artifact.write_bytes(b"approved-safetensors")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    payload, name, vram = resolve_model_artifact(
        {
            "NET003_EXECUTOR_ADAPTER": "resnet50",
            "NET003_MODEL_ARTIFACT_PATH": str(artifact),
            "NET003_MODEL_SHA256": digest,
        }
    )
    assert payload == b"approved-safetensors"
    assert name == "Approved torchvision ResNet50"
    assert vram == 4


def test_real_model_rejects_hash_mismatch(tmp_path: Path) -> None:
    artifact = tmp_path / "resnet50.safetensors"
    artifact.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        resolve_model_artifact(
            {
                "NET003_EXECUTOR_ADAPTER": "resnet50",
                "NET003_MODEL_ARTIFACT_PATH": str(artifact),
                "NET003_MODEL_SHA256": "0" * 64,
            }
        )


def test_fixture_preflight_requires_no_gpu_or_model_artifact() -> None:
    assert preflight_worker({}) is None


def test_corrupt_model_fails_offline_before_live_writes(tmp_path: Path) -> None:
    artifact = tmp_path / "resnet50.safetensors"
    artifact.write_bytes(b"hash-correct-but-not-a-state-dictionary")
    with pytest.raises(
        RuntimeError, match="offline worker preflight failed before any live writes"
    ):
        preflight_worker(
            {
                "NET003_EXECUTOR_ADAPTER": "resnet50",
                "NET003_EXECUTOR_DEVICE": "cpu",
                "NET003_MODEL_ARTIFACT_PATH": str(artifact),
                "NET003_MODEL_SHA256": hashlib.sha256(
                    artifact.read_bytes()
                ).hexdigest(),
                "NET003_WORKER_PYTHON": str(ROOT / "worker/.venv/bin/python"),
            }
        )


@pytest.mark.asyncio
async def test_resume_downloads_confirmed_job_without_creating_another_escrow() -> None:
    key = "0x" + "11" * 32
    owner = Account.from_key(key).address
    job_id = "12345678-1234-5678-1234-567812345678"
    escrow_hash = "0x" + "ab" * 32
    job = {
        "id": job_id,
        "model_id": "resnet50",
        "chain_job_id": "0x" + "12" * 32,
        "status": "completed",
        "reconciliation_health": "match",
        "escrow_transaction": {"hash": escrow_hash, "status": "confirmed"},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET", (
            "a resumed job must never create or fund another job"
        )
        if request.url.path.endswith("/result"):
            return httpx.Response(200, content=b"authorized-result")
        return httpx.Response(200, json=job)

    w3 = SimpleNamespace(
        eth=SimpleNamespace(
            get_transaction_receipt=lambda _hash: {"status": 1, "blockNumber": 42}
        )
    )
    block_queries = []

    def read_job(**kwargs):
        block_queries.append(kwargs.get("block_identifier"))
        return [owner, SETTLED_STATE]

    nebula = SimpleNamespace(
        functions=SimpleNamespace(getJob=lambda _id: SimpleNamespace(call=read_job))
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.example"
    ) as client:
        result = await create_and_wait(
            client, w3, nebula, None, key, "test-token", 1, job_id, baseline_block=42
        )
    assert result["uuid"] == job_id
    assert result["escrow_tx"] == escrow_hash
    assert result["resumed"] is True
    assert block_queries == [42, None]


@pytest.mark.asyncio
async def test_resume_rejects_job_bound_to_different_artifact_or_input() -> None:
    job_id = "12345678-1234-5678-1234-567812345678"
    job = {"id": job_id, "model_id": "resnet50", "fingerprint": "0x" + "00" * 32}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=job)),
        base_url="https://api.example",
    ) as client:
        with pytest.raises(RuntimeError, match="preflight artifact and input"):
            await create_and_wait(
                client,
                None,
                None,
                None,
                "0x" + "11" * 32,
                "test-token",
                1,
                job_id,
                execution={"model_sha256": "ab" * 32, "input_sha256": "cd" * 32},
            )
