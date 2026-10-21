"""Merkle tree builder for PoAE proof envelopes (PRD v3.1 §9).

leafHash = SHA256(0x00 || canonicalLeafBytes)
nodeHash = SHA256(0x01 || leftChild || rightChild)
No sorting. Duplicate final node at odd level.
"""

import hashlib


def compute_leaf_hash(data: bytes) -> bytes:
    """PRD §9: leafHash = SHA256(0x00 || canonicalLeafBytes)."""
    return hashlib.sha256(b"\x00" + data).digest()


def compute_node_hash(left: bytes, right: bytes) -> bytes:
    """PRD §9: nodeHash = SHA256(0x01 || leftChild || rightChild)."""
    return hashlib.sha256(b"\x01" + left + right).digest()


def build_merkle_tree(leaves: list[bytes]) -> tuple[bytes, list[list[tuple[bytes, bool]]]]:
    """Build a Merkle tree from leaf data.

    Returns (root, proofs) where proofs[i] is a list of (sibling_hash, is_right)
    tuples representing the path from leaf i to root.
    Odd levels duplicate the final node (no sorting).
    """
    if not leaves:
        return b"\x00" * 32, []

    leaf_hashes = [compute_leaf_hash(leaf) for leaf in leaves]

    # Build tree levels
    levels = [leaf_hashes]
    current = leaf_hashes
    while len(current) > 1:
        next_level = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i + 1] if i + 1 < len(current) else current[i]
            next_level.append(compute_node_hash(left, right))
        levels.append(next_level)
        current = next_level

    root = current[0]

    # Build proofs: for each leaf, collect (sibling, is_right) along the path
    proofs: list[list[tuple[bytes, bool]]] = []
    for i in range(len(leaf_hashes)):
        proof: list[tuple[bytes, bool]] = []
        idx = i
        for level in levels[:-1]:
            if idx % 2 == 0:
                # Current is left child; sibling is on the right
                sibling_idx = idx + 1 if idx + 1 < len(level) else idx
                proof.append((level[sibling_idx], True))
            else:
                # Current is right child; sibling is on the left
                sibling_idx = idx - 1
                proof.append((level[sibling_idx], False))
            idx //= 2
        proofs.append(proof)

    return root, proofs
