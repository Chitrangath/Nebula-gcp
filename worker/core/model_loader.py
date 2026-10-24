"""Safe acquisition of approved, immutable model artifacts."""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import os
import re
import tempfile
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Final

import aiohttp
from safetensors import safe_open

CACHE_FRESHNESS_SECONDS: Final = 24 * 60 * 60
DOWNLOAD_CHUNK_BYTES: Final = 64 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
RESNET50_DEPENDENCIES: Final = (
    "torch==2.5.1",
    "torchvision==0.20.1",
    "safetensors==0.5.3",
    "Pillow==11.1.0",
    "numpy==2.1.3",
)
BERT_DEPENDENCIES: Final = (
    "torch==2.5.1",
    "transformers==4.48.3",
    "safetensors==0.5.3",
)


def approved_runtime_dependencies(model_id: str) -> tuple[str, ...]:
    """Validate the installed runtime against the two explicit GPU profiles."""
    torch_version = version("torch").split("+", 1)[0]
    vision_version = version("torchvision").split("+", 1)[0]
    if (torch_version, vision_version) not in {
        ("2.5.1", "0.20.1"),
        ("2.7.1", "0.22.1"),
    }:
        raise ValueError("install one of the pinned worker runtime profiles")
    baseline = BERT_DEPENDENCIES if model_id == "bert-base" else RESNET50_DEPENDENCIES
    return tuple(
        item.replace("torch==2.5.1", f"torch=={torch_version}").replace(
            "torchvision==0.20.1", f"torchvision=={vision_version}"
        )
        for item in baseline
    )


class ModelArtifactError(RuntimeError):
    """An approved model artifact could not be acquired safely."""


@dataclass(frozen=True)
class ModelSpec:
    """Complete immutable metadata required to acquire one approved model."""

    model_id: str
    model_version: str
    artifact_url: str
    sha256: str
    max_artifact_bytes: int
    architecture: str
    framework: str
    preprocessing_version: str
    input_type: str
    max_input_bytes: int
    vram_required_gb: int
    checkpoints: tuple[str, ...]
    serialization_version: str
    dependency_versions: tuple[str, ...]

    def __post_init__(self) -> None:
        registry = {
            "resnet50": (
                "torchvision.models.resnet50",
                ("preprocess", "forward", "softmax", "topk"),
                RESNET50_DEPENDENCIES,
            ),
            "bert-base": (
                "transformers.BertForSequenceClassification",
                ("tokenize", "forward", "pool", "project"),
                BERT_DEPENDENCIES,
            ),
        }
        approved = registry.get(self.model_id)
        if approved is None or self.architecture != approved[0]:
            raise ValueError("model is not in the code-defined ResNet50 registry")
        if not SHA256_PATTERN.fullmatch(self.sha256):
            raise ValueError(
                "model artifact SHA-256 must be 64 lowercase hexadecimal characters"
            )
        if (
            self.framework != "pytorch-safetensors"
            or self.serialization_version != "safetensors-v1"
        ):
            raise ValueError("only safetensors state dictionaries are accepted")
        if self.checkpoints != approved[1]:
            raise ValueError(
                "model checkpoint contract does not match the approved protocol"
            )
        modern_dependencies = tuple(
            item.replace("torch==2.5.1", "torch==2.7.1").replace(
                "torchvision==0.20.1", "torchvision==0.22.1"
            )
            for item in approved[2]
        )
        if self.dependency_versions not in (approved[2], modern_dependencies):
            raise ValueError(
                "model dependency versions do not match the approved registry"
            )
        if self.max_artifact_bytes <= 0 or self.max_input_bytes <= 0:
            raise ValueError("model byte limits must be positive")


DownloadFactory = Callable[[ModelSpec], AsyncIterator[bytes]]


class ModelLoader:
    """Resolve approved artifacts into a bounded, verified, hash-keyed cache."""

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        timeout_seconds: float = 120.0,
        download_factory: DownloadFactory | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.download_factory = download_factory or self._http_chunks
        self.now = now
        self._locks: dict[str, asyncio.Lock] = {}

    async def get_artifact(self, spec: ModelSpec) -> Path:
        """Return a verified safetensors path, acquiring it once when absent/corrupt."""
        target = self.cache_dir / f"{spec.sha256}.safetensors"
        async with self._locks.setdefault(spec.sha256, asyncio.Lock()):
            lock_file = self.cache_dir / f"{spec.sha256}.lock"
            async with self._exclusive_file_lock(lock_file):
                if (
                    self._is_valid(target, spec.sha256)
                    and self.now() - target.stat().st_mtime < CACHE_FRESHNESS_SECONDS
                ):
                    return target
                await self._download_atomic(spec, target)
                return target

    @asynccontextmanager
    async def _exclusive_file_lock(self, path: Path) -> AsyncIterator[None]:
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        acquired = False
        while not acquired:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                if asyncio.get_running_loop().time() >= deadline:
                    os.close(descriptor)
                    raise ModelArtifactError(
                        "timed out waiting for model cache lock"
                    ) from None
                await asyncio.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    async def _download_atomic(self, spec: ModelSpec, target: Path) -> None:
        fd, temporary_name = tempfile.mkstemp(
            dir=self.cache_dir, prefix=f".{spec.sha256}-", suffix=".partial"
        )
        digest = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(fd, "wb") as handle:
                async with asyncio.timeout(self.timeout_seconds):
                    source = self.download_factory(spec)
                    try:
                        async for chunk in source:
                            if not chunk:
                                continue
                            size += len(chunk)
                            if size > spec.max_artifact_bytes:
                                raise ModelArtifactError(
                                    "model artifact exceeds its approved byte limit"
                                )
                            digest.update(chunk)
                            handle.write(chunk)
                    finally:
                        close = getattr(source, "aclose", None)
                        if close is not None:
                            await close()
                handle.flush()
                os.fsync(handle.fileno())
            if size == 0:
                raise ModelArtifactError("model artifact download was empty")
            if digest.hexdigest() != spec.sha256:
                raise ModelArtifactError("model artifact SHA-256 mismatch")
            try:
                with safe_open(temporary_name, framework="numpy") as tensors:
                    if not list(tensors.keys()):
                        raise ModelArtifactError(
                            "safetensors state dictionary is empty"
                        )
            except ModelArtifactError:
                raise
            except Exception as exc:
                raise ModelArtifactError(
                    "model artifact is not a valid safetensors state dictionary"
                ) from exc
            os.replace(temporary_name, target)
        except TimeoutError as exc:
            raise ModelArtifactError("model artifact download timed out") from exc
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    @staticmethod
    def _is_valid(path: Path, expected_hash: str) -> bool:
        if not path.is_file():
            return False
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(DOWNLOAD_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest() == expected_hash

    @staticmethod
    async def _http_chunks(spec: ModelSpec) -> AsyncIterator[bytes]:
        timeout = aiohttp.ClientTimeout(total=None)
        async with (
            aiohttp.ClientSession(timeout=timeout) as session,
            session.get(spec.artifact_url, allow_redirects=False) as response,
        ):
            response.raise_for_status()
            async for chunk in response.content.iter_chunked(DOWNLOAD_CHUNK_BYTES):
                yield chunk
