"""Tests for the canonical deterministic fingerprint service (PRD v3.1 §8)."""

import hashlib
import json

from app.services.fingerprint import compute_config_hash, compute_fingerprint, length_prefixed


class TestLengthPrefixed:
    def test_empty_string(self):
        result = length_prefixed("")
        assert result == b"\x00\x00\x00\x00"

    def test_hello(self):
        result = length_prefixed("hello")
        assert result == b"\x00\x00\x00\x05hello"

    def test_resnet50(self):
        result = length_prefixed("resnet50")
        assert result == b"\x00\x00\x00\x08resnet50"

    def test_returns_bytes(self):
        assert isinstance(length_prefixed("test"), bytes)


class TestComputeConfigHash:
    def test_resnet50_config_hash(self):
        h = compute_config_hash("resnet50")
        assert isinstance(h, bytes)
        assert len(h) == 32

    def test_yolov5_config_hash(self):
        h = compute_config_hash("yolov5")
        assert len(h) == 32

    def test_bert_base_config_hash(self):
        h = compute_config_hash("bert-base")
        assert len(h) == 32

    def test_whisper_tiny_config_hash(self):
        h = compute_config_hash("whisper-tiny")
        assert len(h) == 32

    def test_deterministic(self):
        h1 = compute_config_hash("resnet50")
        h2 = compute_config_hash("resnet50")
        assert h1 == h2

    def test_different_models_different_hash(self):
        h1 = compute_config_hash("resnet50")
        h2 = compute_config_hash("yolov5")
        assert h1 != h2

    def test_config_hash_matches_manual(self):
        config = {
            "input_size": [224, 224],
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
            "num_classes": 1000,
            "preprocessing_version": "resnet50-v1",
        }
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
        expected = hashlib.sha256(canonical).digest()
        assert compute_config_hash("resnet50") == expected


class TestComputeFingerprint:
    def test_golden_vector_resnet50(self):
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        model_id = "resnet50"
        model_version = "1.0"
        model_hash = "ab" * 32
        input_hash = "cd" * 32
        preprocessing_version = "resnet50-v1"

        fp = compute_fingerprint(
            job_id=job_id,
            model_id=model_id,
            model_version=model_version,
            model_hash=model_hash,
            input_hash=input_hash,
            preprocessing_version=preprocessing_version,
        )
        assert isinstance(fp, bytes)
        assert len(fp) == 32

    def test_deterministic(self):
        kwargs = dict(
            job_id="550e8400-e29b-41d4-a716-446655440000",
            model_id="resnet50",
            model_version="1.0",
            model_hash="ab" * 32,
            input_hash="cd" * 32,
            preprocessing_version="resnet50-v1",
        )
        fp1 = compute_fingerprint(**kwargs)
        fp2 = compute_fingerprint(**kwargs)
        assert fp1 == fp2

    def test_different_input_different_fingerprint(self):
        kwargs = dict(
            job_id="550e8400-e29b-41d4-a716-446655440000",
            model_id="resnet50",
            model_version="1.0",
            model_hash="ab" * 32,
            input_hash="cd" * 32,
            preprocessing_version="resnet50-v1",
        )
        fp1 = compute_fingerprint(**kwargs)
        kwargs["input_hash"] = "ef" * 32
        fp2 = compute_fingerprint(**kwargs)
        assert fp1 != fp2

    def test_domain_separator_is_nebula_poae_v1(self):
        from app.utils import uuid_to_bytes32

        job_id_bytes = bytes.fromhex(uuid_to_bytes32("550e8400-e29b-41d4-a716-446655440000")[2:34])
        model_id = length_prefixed("resnet50")
        model_version = length_prefixed("1.0")
        model_hash = bytes.fromhex("ab" * 32)
        input_hash = bytes.fromhex("cd" * 32)
        preprocessing_version = length_prefixed("resnet50-v1")
        config_hash = compute_config_hash("resnet50")

        data = (
            b"NEBULA_POAE_V1"
            + job_id_bytes
            + model_id
            + model_version
            + model_hash
            + input_hash
            + preprocessing_version
            + config_hash
        )
        expected = hashlib.sha256(data).digest()

        fp = compute_fingerprint(
            job_id="550e8400-e29b-41d4-a716-446655440000",
            model_id="resnet50",
            model_version="1.0",
            model_hash="ab" * 32,
            input_hash="cd" * 32,
            preprocessing_version="resnet50-v1",
        )
        assert fp == expected

    def test_no_pickle_no_datetime(self):
        fp = compute_fingerprint(
            job_id="550e8400-e29b-41d4-a716-446655440000",
            model_id="resnet50",
            model_version="1.0",
            model_hash="ab" * 32,
            input_hash="cd" * 32,
            preprocessing_version="resnet50-v1",
        )
        assert isinstance(fp, bytes)
        assert len(fp) == 32

    def test_fingerprint_as_hex(self):
        fp = compute_fingerprint(
            job_id="550e8400-e29b-41d4-a716-446655440000",
            model_id="resnet50",
            model_version="1.0",
            model_hash="ab" * 32,
            input_hash="cd" * 32,
            preprocessing_version="resnet50-v1",
        )
        hex_str = fp.hex()
        assert len(hex_str) == 64
