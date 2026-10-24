"""Deterministic, code-defined ResNet50 execution adapter."""

from __future__ import annotations

import hashlib
import io
import json
import os
import warnings
from collections.abc import Callable
from typing import Final

import numpy as np
import torch
from PIL import Image, ImageOps, UnidentifiedImageError
from safetensors.torch import load as load_safetensors
from torch import Tensor, nn
from torchvision.models import resnet50

from core.fixture_executor import CHECKPOINTS

MAX_INPUT_BYTES: Final = 16 * 1024 * 1024
MAX_IMAGE_DIMENSION: Final = 16_384
MAX_IMAGE_PIXELS: Final = 40_000_000
RESIZE_SHORT_SIDE: Final = 256
CROP_SIZE: Final = 224
TOP_K: Final = 5
MEAN: Final = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32).view(3, 1, 1)
STD: Final = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32).view(3, 1, 1)


class ModelExecutionError(RuntimeError):
    """An approved model input or execution failed safely."""


def configure_determinism() -> None:
    """Configure the documented deterministic PyTorch execution envelope."""
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


def preprocess_resnet50(input_bytes: bytes) -> Tensor:
    """Decode, orient, RGB-convert, resize, center-crop, and normalize an image."""
    if not input_bytes or len(input_bytes) > MAX_INPUT_BYTES:
        raise ModelExecutionError("input byte size is outside the approved range")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(input_bytes)) as source:
                if source.format not in {"PNG", "JPEG"}:
                    raise ModelExecutionError("input image format is not approved")
                width, height = source.size
                if (
                    width <= 0
                    or height <= 0
                    or width > MAX_IMAGE_DIMENSION
                    or height > MAX_IMAGE_DIMENSION
                    or width * height > MAX_IMAGE_PIXELS
                ):
                    raise ModelExecutionError(
                        "decoded image dimensions exceed the approved limit"
                    )
                # Policy: apply EXIF orientation before dropping metadata.
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.load()
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ModelExecutionError(
            "input image is corrupt, truncated, or unsafe"
        ) from exc

    width, height = image.size
    scale = RESIZE_SHORT_SIDE / min(width, height)
    resized = image.resize(
        (round(width * scale), round(height * scale)),
        resample=Image.Resampling.BILINEAR,
        reducing_gap=None,
    )
    left = (resized.width - CROP_SIZE) // 2
    top = (resized.height - CROP_SIZE) // 2
    cropped = resized.crop((left, top, left + CROP_SIZE, top + CROP_SIZE))
    array = np.asarray(cropped, dtype=np.float32) / np.float32(255.0)
    tensor = torch.from_numpy(array.transpose(2, 0, 1).copy())
    return ((tensor - MEAN) / STD).unsqueeze(0)


def canonical_tensor_bytes(tensor: Tensor) -> bytes:
    """Serialize a CPU float32 tensor with an unambiguous shape/type header."""
    value = tensor.detach().to(device="cpu", dtype=torch.float32).contiguous()
    shape = ",".join(str(part) for part in value.shape)
    header = f"NEBULA_TENSOR_V1\ndtype=float32-le\nshape={shape}\n\n".encode()
    return header + value.numpy().astype("<f4", copy=False).tobytes(order="C")


def canonical_topk(probabilities: Tensor) -> bytes:
    """Serialize top-k values with index-ascending deterministic tie breaking."""
    values = probabilities.detach().to(device="cpu", dtype=torch.float32)[0].tolist()
    ranked = sorted(enumerate(values), key=lambda item: (-item[1], item[0]))[:TOP_K]
    payload = {
        "model_id": "resnet50",
        "top_k": [
            {"index": index, "probability_hex": float(probability).hex()}
            for index, probability in ranked
        ],
    }
    return (
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"
    )


class ResNet50Executor:
    """Execute approved safetensors weights behind the worker executor seam."""

    def __init__(
        self,
        *,
        device: str = "cpu",
        model_factory: Callable[[], nn.Module] | None = None,
        state_loader: Callable[[bytes], dict[str, Tensor]] = load_safetensors,
    ) -> None:
        self.device = torch.device(device)
        self.model_factory = model_factory or (lambda: resnet50(weights=None))
        self.state_loader = state_loader
        self._models: dict[str, nn.Module] = {}

    def execute(
        self, model: bytes, input_data: bytes, model_id: str
    ) -> tuple[bytes, list[bytes]]:
        """Return canonical top-k bytes and exactly four ordered checkpoint hashes."""
        if model_id != "resnet50":
            raise ModelExecutionError(
                "ResNet50Executor received an unapproved model ID"
            )
        configure_determinism()
        artifact_hash = hashlib.sha256(model).hexdigest()
        network = self._models.get(artifact_hash)
        if network is None:
            try:
                state = self.state_loader(model)
                network = self.model_factory()
                network.load_state_dict(state, strict=True)
                network.eval().to(self.device)
            except Exception as exc:
                raise ModelExecutionError(
                    "invalid ResNet50 safetensors state dictionary"
                ) from exc
            self._models[artifact_hash] = network

        try:
            preprocessed = preprocess_resnet50(input_data)
            with torch.inference_mode():
                logits = network(preprocessed.to(self.device))
                if logits.shape != (1, 1000) or not torch.isfinite(logits).all():
                    raise ModelExecutionError("ResNet50 produced invalid logits")
                probabilities = torch.softmax(logits, dim=1)
                output = canonical_topk(probabilities)
            checkpoint_values = (
                canonical_tensor_bytes(preprocessed),
                canonical_tensor_bytes(logits),
                canonical_tensor_bytes(probabilities),
                output,
            )
            if len(checkpoint_values) != len(CHECKPOINTS):
                raise ModelExecutionError("checkpoint contract length mismatch")
            return output, [
                hashlib.sha256(value).digest() for value in checkpoint_values
            ]
        except torch.OutOfMemoryError as exc:
            if self.device.type == "cuda":
                torch.cuda.empty_cache()
            raise ModelExecutionError(
                "model execution exceeded available device memory"
            ) from exc
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                raise ModelExecutionError(
                    "model execution exceeded available device memory"
                ) from exc
            raise
