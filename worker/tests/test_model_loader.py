"""Behavior tests for the approved model artifact cache interface."""

import asyncio
import hashlib
import os
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np
import pytest
from core.model_loader import (
    CACHE_FRESHNESS_SECONDS,
    RESNET50_DEPENDENCIES,
    ModelArtifactError,
    ModelLoader,
    ModelSpec,
)
from safetensors.numpy import save

ARTIFACT = save({"weight": np.array([1.0, 2.0], dtype=np.float32)})


def spec(**changes: object) -> ModelSpec:
    values = {
        "model_id": "resnet50",
        "model_version": "1.0.0",
        "artifact_url": "https://storage.invalid/resnet50.safetensors",
        "sha256": hashlib.sha256(ARTIFACT).hexdigest(),
        "max_artifact_bytes": 1024,
        "architecture": "torchvision.models.resnet50",
        "framework": "pytorch-safetensors",
        "preprocessing_version": "resnet50-v1",
        "input_type": "image",
        "max_input_bytes": 1024,
        "vram_required_gb": 4,
        "checkpoints": ("preprocess", "forward", "softmax", "topk"),
        "serialization_version": "safetensors-v1",
        "dependency_versions": RESNET50_DEPENDENCIES,
    }
    values.update(changes)
    return ModelSpec(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_streams_verifies_and_atomically_publishes_hash_keyed_artifact(
    tmp_path: Path,
) -> None:
    async def chunks(_spec: ModelSpec) -> AsyncIterator[bytes]:
        yield ARTIFACT[:5]
        yield ARTIFACT[5:]

    path = await ModelLoader(tmp_path, download_factory=chunks).get_artifact(spec())
    assert path.name == f"{hashlib.sha256(ARTIFACT).hexdigest()}.safetensors"
    assert path.read_bytes() == ARTIFACT
    assert list(tmp_path.glob("*.partial")) == []


@pytest.mark.asyncio
async def test_concurrent_requests_download_once(tmp_path: Path) -> None:
    calls = 0

    async def chunks(_spec: ModelSpec) -> AsyncIterator[bytes]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        yield ARTIFACT

    loader = ModelLoader(tmp_path, download_factory=chunks)
    paths = await asyncio.gather(*(loader.get_artifact(spec()) for _ in range(10)))
    assert len(set(paths)) == 1
    assert calls == 1


@pytest.mark.asyncio
async def test_independent_loaders_share_the_file_lock(tmp_path: Path) -> None:
    calls = 0

    async def chunks(_spec: ModelSpec) -> AsyncIterator[bytes]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        yield ARTIFACT

    first = ModelLoader(tmp_path, download_factory=chunks)
    second = ModelLoader(tmp_path, download_factory=chunks)
    paths = await asyncio.gather(
        first.get_artifact(spec()), second.get_artifact(spec())
    )
    assert paths[0] == paths[1]
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [b"wrong", b""])
async def test_hash_mismatch_or_partial_download_leaves_no_artifact(
    tmp_path: Path, payload: bytes
) -> None:
    async def chunks(_spec: ModelSpec) -> AsyncIterator[bytes]:
        yield payload

    with pytest.raises(ModelArtifactError):
        await ModelLoader(tmp_path, download_factory=chunks).get_artifact(spec())
    assert list(tmp_path.glob("*.safetensors")) == []
    assert list(tmp_path.glob("*.partial")) == []


@pytest.mark.asyncio
async def test_timeout_cleans_partial_download(tmp_path: Path) -> None:
    async def chunks(_spec: ModelSpec) -> AsyncIterator[bytes]:
        yield ARTIFACT[:2]
        await asyncio.sleep(1)

    with pytest.raises(ModelArtifactError, match="timed out"):
        await ModelLoader(
            tmp_path, timeout_seconds=0.01, download_factory=chunks
        ).get_artifact(spec())
    assert list(tmp_path.glob("*.partial")) == []


@pytest.mark.asyncio
async def test_over_limit_download_is_rejected(tmp_path: Path) -> None:
    async def chunks(_spec: ModelSpec) -> AsyncIterator[bytes]:
        yield ARTIFACT

    with pytest.raises(ModelArtifactError, match="byte limit"):
        await ModelLoader(tmp_path, download_factory=chunks).get_artifact(
            spec(max_artifact_bytes=1)
        )


@pytest.mark.asyncio
async def test_byte_limit_closes_download_immediately(tmp_path: Path) -> None:
    closed = False

    async def chunks(_spec: ModelSpec) -> AsyncIterator[bytes]:
        nonlocal closed
        try:
            yield ARTIFACT
        finally:
            closed = True

    with pytest.raises(ModelArtifactError, match="byte limit"):
        await ModelLoader(tmp_path, download_factory=chunks).get_artifact(
            spec(max_artifact_bytes=1)
        )
    assert closed, (
        "a failed bounded download must release its network connection immediately"
    )


@pytest.mark.asyncio
async def test_corrupt_cache_is_atomically_replaced(tmp_path: Path) -> None:
    target = tmp_path / f"{spec().sha256}.safetensors"
    target.write_bytes(b"corrupt")

    async def chunks(_spec: ModelSpec) -> AsyncIterator[bytes]:
        assert target.read_bytes() == b"corrupt"
        yield ARTIFACT

    resolved = await ModelLoader(tmp_path, download_factory=chunks).get_artifact(spec())
    assert resolved.read_bytes() == ARTIFACT


@pytest.mark.asyncio
async def test_stale_valid_cache_is_atomically_refreshed_without_disrupting_reader(
    tmp_path: Path,
) -> None:
    target = tmp_path / f"{spec().sha256}.safetensors"
    target.write_bytes(ARTIFACT)
    old = 1_000.0
    os.utime(target, (old, old))

    calls = 0

    async def refresh(_spec: ModelSpec) -> AsyncIterator[bytes]:
        nonlocal calls
        calls += 1
        yield ARTIFACT

    with target.open("rb") as in_use:
        resolved = await ModelLoader(
            tmp_path,
            now=lambda: old + CACHE_FRESHNESS_SECONDS + 1,
            download_factory=refresh,
        ).get_artifact(spec())
        assert resolved == target
        assert in_use.read() == ARTIFACT
    assert calls == 1


def test_registry_rejects_pickle_or_unapproved_architecture() -> None:
    with pytest.raises(ValueError, match="safetensors"):
        spec(framework="pytorch-pickle")
    with pytest.raises(ValueError, match="registry"):
        spec(architecture="dynamic.remote.Model")
