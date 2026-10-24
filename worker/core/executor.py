"""Protocol-compliant HTTP worker with a replaceable deterministic executor."""

import asyncio
import base64
import hashlib
import logging
import uuid
from datetime import datetime, timezone

import aiohttp
from proof.envelope import ProofEnvelope, sign_envelope
from proof.merkle import build_merkle_root

from core.fixture_executor import CHECKPOINTS, DeterministicFixtureExecutor

logger = logging.getLogger(__name__)


class JobExecutor:
    def __init__(self, settings, executor=None):
        self.settings = settings
        self.model_loader = None
        if executor is not None:
            self.executor = executor
        elif getattr(settings, "EXECUTOR_ADAPTER", "fixture") == "fixture":
            self.executor = DeterministicFixtureExecutor()
        elif settings.EXECUTOR_ADAPTER == "resnet50":
            from core.model_loader import ModelLoader
            from core.resnet50_executor import ResNet50Executor

            self.executor = ResNet50Executor(device=settings.EXECUTOR_DEVICE)
            self.model_loader = ModelLoader(
                settings.MODEL_CACHE_DIR,
                download_factory=self._download_model_chunks,
            )
        else:
            raise ValueError("unknown worker executor adapter")
        self.session = None

    async def _download_model_chunks(self, spec):
        if spec.artifact_url.startswith(("https://", "http://")):
            response = await self.session.get(spec.artifact_url, allow_redirects=False)
            response.raise_for_status()
        else:
            response = await self.request("GET", spec.artifact_url)
        try:
            async for chunk in response.content.iter_chunked(64 * 1024):
                yield chunk
        finally:
            response.close()

    async def request(self, method, path, **kwargs):
        response = await self.session.request(
            method,
            self.settings.BACKEND_URL + path,
            headers={"X-API-Key": self.settings.API_KEY},
            **kwargs,
        )
        response.raise_for_status()
        return response

    async def run(self):
        async with aiohttp.ClientSession() as self.session:
            while True:
                lease = None
                try:
                    await self.request(
                        "POST", f"/v1/worker/nodes/{self.settings.NODE_ID}/heartbeat"
                    )
                    lease = (
                        await (
                            await self.request("POST", "/v1/worker/leases/next")
                        ).json()
                    )["lease"]
                    if lease:
                        await self.execute(lease)
                except Exception as exc:  # noqa: BLE001 - cycle isolation must survive any adapter failure
                    logger.warning(
                        "worker_cycle_failed error_type=%s", type(exc).__name__
                    )
                    if lease:
                        try:
                            await self.request(
                                "POST",
                                f"/v1/worker/leases/{lease['lease_id']}/fail",
                                json={"error": type(exc).__name__},
                            )
                        except Exception as report_exc:  # noqa: BLE001 - failure reporting must not stop polling
                            logger.warning(
                                "worker_failure_report_failed error_type=%s",
                                type(report_exc).__name__,
                            )
                await asyncio.sleep(self.settings.POLL_INTERVAL_SECONDS)

    async def execute(self, lease):
        lid = lease["lease_id"]
        await self.request("POST", f"/v1/worker/leases/{lid}/ack", json={})
        input_response = await self.request("GET", f"/v1/worker/leases/{lid}/input")
        input_data = await input_response.read()
        expected = (
            (lease.get("model_hash") or "").removeprefix("sha256:").removeprefix("0x")
        )
        if self.model_loader is not None:
            from core.model_loader import RESNET50_DEPENDENCIES, ModelSpec

            spec = ModelSpec(
                model_id=lease["model_id"],
                model_version=lease["model_version"],
                artifact_url=(
                    self.settings.MODEL_ARTIFACT_URL or f"/v1/worker/leases/{lid}/model"
                ),
                sha256=expected,
                max_artifact_bytes=self.settings.MAX_MODEL_ARTIFACT_BYTES,
                architecture="torchvision.models.resnet50",
                framework="pytorch-safetensors",
                preprocessing_version=lease["preprocessing_version"],
                input_type="image",
                max_input_bytes=16 * 1024 * 1024,
                vram_required_gb=4,
                checkpoints=tuple(CHECKPOINTS),
                serialization_version="safetensors-v1",
                dependency_versions=RESNET50_DEPENDENCIES,
            )
            model = (await self.model_loader.get_artifact(spec)).read_bytes()
        else:
            model_response = await self.request("GET", f"/v1/worker/leases/{lid}/model")
            model = await model_response.read()
        if expected and hashlib.sha256(model).hexdigest() != expected:
            raise ValueError("model hash mismatch")
        if hashlib.sha256(input_data).hexdigest() != lease["input_hash"]:
            raise ValueError("input hash mismatch")
        output, trace = self.executor.execute(model, input_data, lease["model_id"])
        output_hash = hashlib.sha256(output).digest()
        root = build_merkle_root([*trace, output_hash])
        key = f"results/{lease['job_id']}/{lease['attempt_id']}/output"
        await self.request(
            "POST",
            f"/v1/worker/leases/{lid}/result-upload",
            json={
                "result_file_key": key,
                "result_bytes_base64": base64.b64encode(output).decode(),
            },
        )
        ts = int(datetime.now(timezone.utc).timestamp())
        expires = int(datetime.fromisoformat(lease["lease_expires_at"]).timestamp())
        env = ProofEnvelope(
            1,
            self.settings.CHAIN_ID,
            self.settings.VERIFYING_CONTRACT,
            bytes.fromhex(lease["chain_job_id"][2:]),
            uuid.UUID(lease["attempt_id"]).bytes + b"\0" * 16,
            bytes.fromhex(lease["lease_id_chain"][2:]),
            lease["provider"],
            bytes.fromhex(lease["expected_fingerprint"]),
            root,
            output_hash,
            ts,
            expires,
        )
        payload = {
            "protocol_version": 1,
            "chain_id": env.chain_id,
            "verifying_contract": env.verifying_contract,
            "job_id": "0x" + env.job_id.hex(),
            "attempt_id": "0x" + env.attempt_id.hex(),
            "lease_id": "0x" + env.lease_id.hex(),
            "provider": env.provider,
            "fingerprint": "0x" + env.fingerprint.hex(),
            "merkle_root": "0x" + root.hex(),
            "output_hash": "0x" + output_hash.hex(),
            "proof_timestamp": ts,
            "lease_expires_at": expires,
            "checkpoint_names": CHECKPOINTS,
            "trace_hashes": ["0x" + v.hex() for v in trace],
            "signature": sign_envelope(env, self.settings.PRIVATE_KEY),
            "result_file_key": key,
        }
        await self.request("POST", f"/v1/worker/leases/{lid}/complete", json=payload)
