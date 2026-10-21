"""Canonical ordered SHA-256 Merkle tree."""

import hashlib


def build_merkle_root(values: list[bytes]) -> bytes:
    if not values:
        return b"\x00" * 32
    level = [hashlib.sha256(b"\x00" + value).digest() for value in values]
    while len(level) > 1:
        level = [
            hashlib.sha256(
                b"\x01" + level[i] + (level[i + 1] if i + 1 < len(level) else level[i])
            ).digest()
            for i in range(0, len(level), 2)
        ]
    return level[0]


def build_merkle_proof(trace_hashes: list[str], output_hash: str) -> str:
    values = [
        bytes.fromhex(value.removeprefix("0x"))
        for value in [*trace_hashes, output_hash]
    ]
    return build_merkle_root(values).hex()
