"""Canonical deterministic fingerprint computation (PRD v3.1 §8).

The fingerprint binds: domain separator, job ID, model identity, model artifact
hash, input hash, preprocessing version, and canonical inference config hash.

All strings use 4-byte big-endian length-prefix encoding.
No pickle, no datetime, no ambiguous concatenation.
"""

import hashlib
import json

from app.utils import uuid_to_bytes32

# PRD v3.1 §8.1: domain separator is exactly 16 bytes
DOMAIN_SEPARATOR = b"NEBULA_POAE_V1"

# PRD v3.1 §8.5: canonical inference configurations for each approved model
MODEL_CONFIGS: dict[str, dict] = {
    "resnet50": {
        "input_size": [224, 224],
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "num_classes": 1000,
        "preprocessing_version": "resnet50-v1",
    },
    "yolov5": {
        "input_size": [640, 640],
        "confidence_threshold": 0.25,
        "preprocessing_version": "yolov5-v1",
    },
    "bert-base": {
        "max_length": 512,
        "tokenizer": "bert-base-uncased",
        "preprocessing_version": "bert-v1",
    },
    "whisper-tiny": {
        "sample_rate": 16000,
        "max_duration_seconds": 30,
        "preprocessing_version": "whisper-v1",
    },
}


def length_prefixed(s: str) -> bytes:
    """PRD v3.1 §8.2: 4-byte big-endian length prefix + UTF-8 bytes."""
    encoded = s.encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded


def compute_config_hash(model_id: str) -> bytes:
    """PRD v3.1 §8.5: SHA-256 of canonical UTF-8 JSON config."""
    config = MODEL_CONFIGS.get(model_id)
    if config is None:
        raise ValueError(f"Unknown model_id: {model_id}")
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).digest()


def compute_fingerprint(
    *,
    job_id: str,
    model_id: str,
    model_version: str,
    model_hash: str,
    input_hash: str,
    preprocessing_version: str,
) -> bytes:
    """PRD v3.1 §8.1: Compute deterministic fingerprint.

    fingerprint = SHA256(
        domainSeparator    ||   // 16 bytes
        jobId              ||   // 16 bytes (UUID left-aligned)
        modelId            ||   // length-prefixed UTF-8
        modelVersion       ||   // length-prefixed UTF-8
        modelHash          ||   // 32 bytes
        inputHash          ||   // 32 bytes
        preprocessingVersion || // length-prefixed UTF-8
        configHash               // 32 bytes
    )
    """
    # Job ID: left-aligned in bytes32, take first 16 bytes
    job_id_bytes = bytes.fromhex(uuid_to_bytes32(job_id)[2:34])

    # Model hash and input hash: 32 bytes each
    model_hash_bytes = bytes.fromhex(model_hash)
    input_hash_bytes = bytes.fromhex(input_hash)

    data = (
        DOMAIN_SEPARATOR
        + job_id_bytes
        + length_prefixed(model_id)
        + length_prefixed(model_version)
        + model_hash_bytes
        + input_hash_bytes
        + length_prefixed(preprocessing_version)
        + compute_config_hash(model_id)
    )

    return hashlib.sha256(data).digest()
