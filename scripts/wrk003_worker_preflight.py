#!/usr/bin/env python3
"""Verify artifact delivery and repeat inference before any storage or chain writes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))


async def verify_download(url: str, expected_hash: str) -> None:
    """Exercise bounded private artifact delivery with the real worker loader."""
    from core.model_loader import RESNET50_DEPENDENCIES, ModelLoader, ModelSpec

    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError(
            "private artifact URL must be HTTPS without embedded credentials"
        )
    spec = ModelSpec(
        model_id="resnet50",
        model_version="1.0",
        artifact_url=url,
        sha256=expected_hash,
        max_artifact_bytes=256 * 1024 * 1024,
        architecture="torchvision.models.resnet50",
        framework="pytorch-safetensors",
        preprocessing_version="resnet50-v1",
        input_type="image",
        max_input_bytes=16 * 1024 * 1024,
        vram_required_gb=4,
        checkpoints=("preprocess", "forward", "softmax", "topk"),
        serialization_version="safetensors-v1",
        dependency_versions=RESNET50_DEPENDENCIES,
    )
    try:
        with tempfile.TemporaryDirectory(prefix="nebula-wrk003-download-") as cache:
            await ModelLoader(cache).get_artifact(spec)
    except Exception as exc:  # noqa: BLE001 - sanitize URL-bearing HTTP exceptions at the CLI boundary
        raise RuntimeError(
            f"private artifact download verification failed ({type(exc).__name__}); "
            "check or refresh the protected artifact URL"
        ) from None


def verify_execution(
    path: Path, expected_hash: str, input_bytes: bytes, device: str
) -> dict[str, Any]:
    """Verify artifact bytes and repeat actual inference on the selected device."""
    # CUDA determinism requires this to be set before the first CUDA operation.
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    from core.resnet50_executor import ResNet50Executor

    if not path.is_file() or not 0 < path.stat().st_size <= 256 * 1024 * 1024:
        raise ValueError("artifact is missing or exceeds the approved byte bound")
    artifact = path.read_bytes()
    if hashlib.sha256(artifact).hexdigest() != expected_hash:
        raise ValueError("artifact SHA-256 mismatch")
    artifact_url = os.environ.get("WRK003_PREFLIGHT_ARTIFACT_URL")
    if artifact_url:
        asyncio.run(verify_download(artifact_url, expected_hash))
    adapter = ResNet50Executor(device=device)
    first = adapter.execute(artifact, input_bytes, "resnet50")
    second = adapter.execute(artifact, input_bytes, "resnet50")
    if first != second:
        raise RuntimeError("same-process inference is not repeatable")

    import torch

    return {
        "adapter": "resnet50",
        "device": device,
        "gpu_name": torch.cuda.get_device_name(0) if device == "cuda" else None,
        "gpu_memory_bytes": torch.cuda.get_device_properties(0).total_memory
        if device == "cuda"
        else None,
        "model_sha256": expected_hash,
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "result_sha256": hashlib.sha256(first[0]).hexdigest(),
        "checkpoint_sha256": [value.hex() for value in first[1]],
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
    }


def main() -> int:
    """Read only public execution inputs and emit sanitized inference evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--input-hex", required=True)
    args = parser.parse_args()
    try:
        result = verify_execution(
            args.artifact, args.sha256, bytes.fromhex(args.input_hex), args.device
        )
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        # HTTP exceptions are sanitized by verify_download; never emit a signed URL.
        print(
            f"WRK-003 offline preflight failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
