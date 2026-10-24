"""Canonical job fingerprint implementation shared by worker semantics."""

import hashlib
import json
import uuid

DOMAIN_SEPARATOR = b"NEBULA_POAE_V1"
MODEL_CONFIGS: dict[str, dict[str, object]] = {
    "resnet50": {
        "input_size": [224, 224],
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "num_classes": 1000,
        "preprocessing_version": "resnet50-v1",
    },
    "bert-base": {
        "max_length": 512,
        "tokenizer": "nlptown/bert-base-multilingual-uncased-sentiment",
        "tokenizer_sha256": "87b44292b452f6c05afa49b2e488e7eedf79ea4f4c39db6f2f4b37764228ef3f",
        "preprocessing_version": "bert-sentiment-v1",
    },
}


def _length_prefixed(value: str) -> bytes:
    encoded = value.encode()
    return len(encoded).to_bytes(4, "big") + encoded


def compute_fingerprint(
    *,
    job_id: str,
    model_id: str,
    model_version: str,
    model_hash: str,
    input_hash: str,
    preprocessing_version: str,
) -> bytes:
    """Compute the backend-compatible deterministic job fingerprint."""
    config = MODEL_CONFIGS.get(model_id)
    if config is None:
        raise ValueError("unapproved model ID")
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    ).digest()
    payload = (
        DOMAIN_SEPARATOR
        + uuid.UUID(job_id).bytes
        + _length_prefixed(model_id)
        + _length_prefixed(model_version)
        + bytes.fromhex(model_hash)
        + bytes.fromhex(input_hash)
        + _length_prefixed(preprocessing_version)
        + config_hash
    )
    return hashlib.sha256(payload).digest()
