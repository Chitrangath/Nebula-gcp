"""UUID ↔ bytes32 conversion utilities (PRD v3.1 §7.5).

Canonical encoding:
  UUID string → remove hyphens → 16 raw bytes → left-aligned in bytes32
  (first 16 bytes = UUID, last 16 bytes = 0x00)

Example:
  550e8400-e29b-41d4-a716-446655440000
  → 0x550e8400e29b41d4a71644665544000000000000000000000000000000000000
"""

import uuid


def uuid_to_bytes32(value: uuid.UUID | str) -> str:
    """Convert a UUID to its left-aligned bytes32 hex representation.

    Args:
        value: UUID object or UUID string (with hyphens).

    Returns:
        66-char hex string (0x + 64 hex chars).

    Raises:
        ValueError: If the input is not a valid UUID.
    """
    if isinstance(value, str):
        value = uuid.UUID(value)
    raw = value.bytes  # 16 bytes
    return "0x" + raw.hex() + "0" * 32


def bytes32_to_uuid(value: str) -> uuid.UUID:
    """Convert a bytes32 hex string back to a UUID.

    Args:
        value: 66-char hex string (0x + 64 hex chars) or 64 hex chars.

    Returns:
        UUID object.

    Raises:
        ValueError: If the input is not valid or the right 16 bytes are non-zero.
    """
    hex_str = value.removeprefix("0x")
    if len(hex_str) != 64:
        raise ValueError(f"Invalid bytes32 length: {len(hex_str)} hex chars (expected 64)")
    # Verify right 16 bytes are all zeros (left-aligned UUID)
    right_half = hex_str[32:]
    if right_half != "0" * 32:
        raise ValueError("Right 16 bytes must be zero for a valid left-aligned UUID")
    raw = bytes.fromhex(hex_str[:32])
    return uuid.UUID(bytes=raw)
