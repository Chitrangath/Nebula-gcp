"""Tests for UUID ↔ bytes32 conversion utilities (PRD v3.1 §7.5 golden vectors)."""

import uuid

from app.utils import bytes32_to_uuid, uuid_to_bytes32

# Golden vectors: (uuid_string, expected_bytes32_hex)
# PRD v3.1 §7.5 — 10 canonical test vectors shared across contract, backend, and worker
GOLDEN_VECTORS = [
    ("550e8400-e29b-41d4-a716-446655440000", "0x550e8400e29b41d4a71644665544000000000000000000000000000000000000"),
    ("6ba7b810-9dad-11d1-80b4-00c04fd430c8", "0x6ba7b8109dad11d180b400c04fd430c800000000000000000000000000000000"),
    ("00000000-0000-0000-0000-000000000001", "0x0000000000000000000000000000000100000000000000000000000000000000"),
    ("bbbbbbbb-cccc-dddd-eeee-ffffffffffff", "0xbbbbbbbbccccddddeeeeffffffffffff00000000000000000000000000000000"),
    ("cccccccc-dddd-eeee-ffff-000000000000", "0xccccccccddddeeeeffff00000000000000000000000000000000000000000000"),
    ("a0b1c2d3-e4f5-6789-abcd-ef0123456789", "0xa0b1c2d3e4f56789abcdef012345678900000000000000000000000000000000"),
    ("9f8e7d6c-5b4a-3210-fedc-ba9876543210", "0x9f8e7d6c5b4a3210fedcba987654321000000000000000000000000000000000"),
    ("deadbeef-dead-beef-dead-beefdeadbeef", "0xdeadbeefdeadbeefdeadbeefdeadbeef00000000000000000000000000000000"),
    ("cafebabe-cafe-babe-cafe-babecafebabe", "0xcafebabecafebabecafebabecafebabe00000000000000000000000000000000"),
    ("01234567-89ab-cdef-0123-456789abcdef", "0x0123456789abcdef0123456789abcdef00000000000000000000000000000000"),
]


class TestUuidToBytes32:
    def test_golden_vector_0(self):
        assert uuid_to_bytes32(GOLDEN_VECTORS[0][0]) == GOLDEN_VECTORS[0][1]

    def test_golden_vector_1(self):
        assert uuid_to_bytes32(GOLDEN_VECTORS[1][0]) == GOLDEN_VECTORS[1][1]

    def test_golden_vector_2(self):
        assert uuid_to_bytes32(GOLDEN_VECTORS[2][0]) == GOLDEN_VECTORS[2][1]

    def test_golden_vector_3(self):
        assert uuid_to_bytes32(GOLDEN_VECTORS[3][0]) == GOLDEN_VECTORS[3][1]

    def test_golden_vector_4(self):
        assert uuid_to_bytes32(GOLDEN_VECTORS[4][0]) == GOLDEN_VECTORS[4][1]

    def test_golden_vector_5(self):
        assert uuid_to_bytes32(GOLDEN_VECTORS[5][0]) == GOLDEN_VECTORS[5][1]

    def test_golden_vector_6(self):
        assert uuid_to_bytes32(GOLDEN_VECTORS[6][0]) == GOLDEN_VECTORS[6][1]

    def test_golden_vector_7(self):
        assert uuid_to_bytes32(GOLDEN_VECTORS[7][0]) == GOLDEN_VECTORS[7][1]

    def test_golden_vector_8(self):
        assert uuid_to_bytes32(GOLDEN_VECTORS[8][0]) == GOLDEN_VECTORS[8][1]

    def test_golden_vector_9(self):
        assert uuid_to_bytes32(GOLDEN_VECTORS[9][0]) == GOLDEN_VECTORS[9][1]

    def test_all_golden_vectors(self):
        for uuid_str, expected_hex in GOLDEN_VECTORS:
            assert uuid_to_bytes32(uuid_str) == expected_hex, f"Failed for UUID {uuid_str}"

    def test_uuid_object_input(self):
        u = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        assert uuid_to_bytes32(u) == "0x550e8400e29b41d4a71644665544000000000000000000000000000000000000"

    def test_output_is_66_chars(self):
        result = uuid_to_bytes32("550e8400-e29b-41d4-a716-446655440000")
        assert len(result) == 66
        assert result.startswith("0x")

    def test_right_16_bytes_are_zero(self):
        result = uuid_to_bytes32("550e8400-e29b-41d4-a716-446655440000")
        right_half = result[34:]  # after "0x" + first 32 hex chars
        assert right_half == "0" * 32

    def test_invalid_uuid_raises(self):
        import pytest

        with pytest.raises(ValueError):
            uuid_to_bytes32("not-a-uuid")

    def test_different_uuids_different_results(self):
        a = uuid_to_bytes32("550e8400-e29b-41d4-a716-446655440000")
        b = uuid_to_bytes32("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
        assert a != b


class TestBytes32ToUuid:
    def test_golden_vector_0(self):
        assert str(bytes32_to_uuid(GOLDEN_VECTORS[0][1])) == GOLDEN_VECTORS[0][0]

    def test_golden_vector_1(self):
        assert str(bytes32_to_uuid(GOLDEN_VECTORS[1][1])) == GOLDEN_VECTORS[1][0]

    def test_golden_vector_2(self):
        assert str(bytes32_to_uuid(GOLDEN_VECTORS[2][1])) == GOLDEN_VECTORS[2][0]

    def test_golden_vector_3(self):
        assert str(bytes32_to_uuid(GOLDEN_VECTORS[3][1])) == GOLDEN_VECTORS[3][0]

    def test_golden_vector_4(self):
        assert str(bytes32_to_uuid(GOLDEN_VECTORS[4][1])) == GOLDEN_VECTORS[4][0]

    def test_golden_vector_5(self):
        assert str(bytes32_to_uuid(GOLDEN_VECTORS[5][1])) == GOLDEN_VECTORS[5][0]

    def test_golden_vector_6(self):
        assert str(bytes32_to_uuid(GOLDEN_VECTORS[6][1])) == GOLDEN_VECTORS[6][0]

    def test_golden_vector_7(self):
        assert str(bytes32_to_uuid(GOLDEN_VECTORS[7][1])) == GOLDEN_VECTORS[7][0]

    def test_golden_vector_8(self):
        assert str(bytes32_to_uuid(GOLDEN_VECTORS[8][1])) == GOLDEN_VECTORS[8][0]

    def test_golden_vector_9(self):
        assert str(bytes32_to_uuid(GOLDEN_VECTORS[9][1])) == GOLDEN_VECTORS[9][0]

    def test_all_golden_vectors(self):
        for uuid_str, expected_hex in GOLDEN_VECTORS:
            assert str(bytes32_to_uuid(expected_hex)) == uuid_str, f"Failed for hex {expected_hex}"

    def test_roundtrip(self):
        for uuid_str, _ in GOLDEN_VECTORS:
            result = bytes32_to_uuid(uuid_to_bytes32(uuid_str))
            assert str(result) == uuid_str

    def test_roundtrip_uuid_object(self):
        original = uuid.UUID("deadbeef-dead-beef-dead-beefdeadbeef")
        result = bytes32_to_uuid(uuid_to_bytes32(original))
        assert result == original

    def test_non_zero_right_half_raises(self):
        import pytest

        # Right 16 bytes are non-zero — invalid for left-aligned UUID
        with pytest.raises(ValueError, match="Right 16 bytes must be zero"):
            bytes32_to_uuid("550e8400e29b41d4a716446655440000ffffffffffffffffffffffffffffffff")

    def test_wrong_length_raises(self):
        import pytest

        with pytest.raises(ValueError, match="Invalid bytes32 length"):
            bytes32_to_uuid("0x550e8400e29b41d4a716446655440000")

    def test_without_0x_prefix(self):
        result = bytes32_to_uuid("550e8400e29b41d4a71644665544000000000000000000000000000000000000")
        assert str(result) == "550e8400-e29b-41d4-a716-446655440000"
