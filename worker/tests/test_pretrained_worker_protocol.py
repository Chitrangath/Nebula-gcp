"""Opt-in real-weight acceptance through the worker's HTTP protocol seam.

Only HTTP transport is simulated. Acquisition, inference, result hashing,
Merkle commitment, and EIP-712 signing use the production worker code.
"""

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses
from eth_account import Account
from eth_account.messages import encode_typed_data

from core.executor import JobExecutor
from proof.envelope import ProofEnvelope, typed_data
from proof.merkle import build_merkle_root


@pytest.mark.asyncio
@pytest.mark.parametrize("model_id", ["resnet50", "bert-base"])
async def test_real_weights_complete_the_signed_worker_protocol(model_id, tmp_path):
    bert_dir = os.environ.get("NEBULA_BERT_ARTIFACT_DIR")
    resnet_path = os.environ.get("NEBULA_RESNET_ARTIFACT")
    if not bert_dir or not resnet_path:
        pytest.skip(
            "set NEBULA_BERT_ARTIFACT_DIR and NEBULA_RESNET_ARTIFACT for real-weight acceptance"
        )
    from core.bert_executor import BERT_REVISION

    artifact = (
        Path(bert_dir) / "model.safetensors"
        if model_id == "bert-base"
        else Path(resnet_path)
    )
    weights = artifact.read_bytes()
    if model_id == "bert-base":
        input_bytes = b"This product is excellent, I love it! Highly recommended."
    else:
        import io
        from PIL import Image

        image = io.BytesIO()
        Image.new("RGB", (256, 256), (120, 30, 90)).save(image, format="PNG")
        input_bytes = image.getvalue()
    job_id, attempt_id, lease_id = [str(uuid.uuid4()) for _ in range(3)]
    signer = Account.create()
    settings = SimpleNamespace(
        EXECUTOR_ADAPTER="multimodel",
        EXECUTOR_DEVICE=os.environ.get("NEBULA_REAL_MODEL_DEVICE", "cpu"),
        BERT_VOCAB_PATH=str(Path(bert_dir) / "vocab.txt"),
        MODEL_CACHE_DIR=str(tmp_path / "models"),
        MODEL_ARTIFACT_URL="https://private.invalid/resnet.safetensors",
        MAX_MODEL_ARTIFACT_BYTES=768 * 1024 * 1024,
        BACKEND_URL="https://api.invalid",
        API_KEY="test-only-worker-key",
        CHAIN_ID=421614,
        VERIFYING_CONTRACT="0x" + "11" * 20,
        PRIVATE_KEY=signer.key.hex(),
    )
    lease = dict(
        lease_id=lease_id,
        job_id=job_id,
        attempt_id=attempt_id,
        model_id=model_id,
        model_version=BERT_REVISION if model_id == "bert-base" else "1.0",
        preprocessing_version="bert-sentiment-v1"
        if model_id == "bert-base"
        else "resnet50-v1",
        input_hash=hashlib.sha256(input_bytes).hexdigest(),
        model_hash=hashlib.sha256(weights).hexdigest(),
        chain_job_id="0x" + uuid.UUID(job_id).hex + "00" * 16,
        lease_id_chain="0x" + "22" * 32,
        provider="0x" + "33" * 20,
        expected_fingerprint="44" * 32,
        lease_expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    requests = {}

    def capture(url, **kwargs):
        requests[str(url).rsplit("/", 1)[-1]] = kwargs["json"]
        return CallbackResult(status=202, payload={})

    worker = JobExecutor(settings)
    root = f"https://api.invalid/v1/worker/leases/{lease_id}"
    with aioresponses() as http:
        http.post(root + "/ack", payload={})
        http.get(root + "/input", body=input_bytes)
        http.get(
            root + "/model-url",
            payload={"url": "https://private.invalid/bert.safetensors"},
        )
        http.get(settings.MODEL_ARTIFACT_URL, body=weights)
        http.get("https://private.invalid/bert.safetensors", body=weights)
        http.post(root + "/result-upload", callback=capture)
        http.post(root + "/complete", callback=capture)
        async with aiohttp.ClientSession() as session:
            worker.session = session
            await worker.execute(lease)
    output = base64.b64decode(requests["result-upload"]["result_bytes_base64"])
    proof = requests["complete"]
    assert proof["output_hash"] == "0x" + hashlib.sha256(output).hexdigest()
    trace = [bytes.fromhex(value[2:]) for value in proof["trace_hashes"]]
    assert (
        proof["merkle_root"]
        == "0x" + build_merkle_root(trace + [hashlib.sha256(output).digest()]).hex()
    )
    assert proof["checkpoint_names"] == (
        ["tokenize", "forward", "pool", "project"]
        if model_id == "bert-base"
        else ["preprocess", "forward", "softmax", "topk"]
    )
    envelope = ProofEnvelope(
        1,
        421614,
        settings.VERIFYING_CONTRACT,
        bytes.fromhex(proof["job_id"][2:]),
        bytes.fromhex(proof["attempt_id"][2:]),
        bytes.fromhex(proof["lease_id"][2:]),
        proof["provider"],
        bytes.fromhex(proof["fingerprint"][2:]),
        bytes.fromhex(proof["merkle_root"][2:]),
        bytes.fromhex(proof["output_hash"][2:]),
        proof["proof_timestamp"],
        proof["lease_expires_at"],
    )
    assert (
        Account.recover_message(
            encode_typed_data(full_message=typed_data(envelope)),
            signature=proof["signature"],
        )
        == signer.address
    )
    result = json.loads(output)
    assert result["model_id"] == model_id
    if model_id == "bert-base":
        assert result["stars"] == 5
    else:
        assert len(result["top_k"]) == 5
