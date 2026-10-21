"""Tests for Merkle tree, EIP-712 signing, and proof verification (PRD §9, §22)."""

import hashlib
import secrets

from app.services.eip712 import build_eip712_struct_hash, recover_signer, verify_signature
from app.services.merkle import build_merkle_tree, compute_leaf_hash, compute_node_hash
from app.services.proof_verifier import verify_proof_envelope


class TestMerkleTree:
    def test_compute_leaf_hash(self):
        leaf_data = b"test-leaf-data"
        h = compute_leaf_hash(leaf_data)
        assert isinstance(h, bytes)
        assert len(h) == 32
        expected = hashlib.sha256(b"\x00" + leaf_data).digest()
        assert h == expected

    def test_compute_node_hash(self):
        left = hashlib.sha256(b"left").digest()
        right = hashlib.sha256(b"right").digest()
        h = compute_node_hash(left, right)
        assert isinstance(h, bytes)
        assert len(h) == 32
        expected = hashlib.sha256(b"\x01" + left + right).digest()
        assert h == expected

    def test_build_tree_single_leaf(self):
        leaves = [b"leaf1"]
        root, proof = build_merkle_tree(leaves)
        assert isinstance(root, bytes)
        assert len(root) == 32
        assert proof == [[]]  # One leaf, one empty proof path

    def test_build_tree_two_leaves(self):
        leaves = [b"leaf1", b"leaf2"]
        root, proofs = build_merkle_tree(leaves)
        assert len(proofs) == 2
        for proof in proofs:
            assert isinstance(proof, list)

    def test_build_tree_three_leaves(self):
        leaves = [b"leaf1", b"leaf2", b"leaf3"]
        root, proofs = build_merkle_tree(leaves)
        assert len(proofs) == 3
        # Verify each proof can reconstruct root
        for i, leaf in enumerate(leaves):
            leaf_hash = compute_leaf_hash(leaf)
            current = leaf_hash
            for sibling, is_right in proofs[i]:
                if is_right:
                    current = compute_node_hash(current, sibling)
                else:
                    current = compute_node_hash(sibling, current)
            assert current == root

    def test_build_tree_empty(self):
        root, proofs = build_merkle_tree([])
        assert root == b"\x00" * 32
        assert proofs == []

    def test_build_tree_odd_leaves_duplicates_final(self):
        leaves = [b"leaf1", b"leaf2", b"leaf3"]
        root, proofs = build_merkle_tree(leaves)
        assert root is not None
        assert len(proofs) == 3


class TestEIP712:
    def test_build_struct_hash(self):
        struct_hash = build_eip712_struct_hash(
            job_id=bytes(32),
            fingerprint=bytes(32),
            merkle_root=bytes(32),
            output_hash=bytes(32),
            timestamp=1000,
        )
        assert isinstance(struct_hash, bytes)
        assert len(struct_hash) == 32

    def test_sign_and_verify(self):
        private_key = secrets.token_bytes(32)
        struct_hash = build_eip712_struct_hash(
            job_id=bytes(32),
            fingerprint=bytes(32),
            merkle_root=bytes(32),
            output_hash=bytes(32),
            timestamp=1000,
        )
        signer_address, signature = recover_signer(struct_hash, private_key)
        assert isinstance(signer_address, str)
        assert len(signer_address) == 42
        assert verify_signature(struct_hash, signature, signer_address)


class TestProofVerifier:
    def test_verify_proof_envelope(self):
        from app.services.eip712 import sign_struct_hash

        private_key = secrets.token_bytes(32)

        leaves = [b"step1", b"step2", b"step3"]
        root, proofs = build_merkle_tree(leaves)

        leaf_data = b"step1"
        leaf_hash = compute_leaf_hash(leaf_data)
        proof = proofs[0]

        job_id = bytes(32)
        fingerprint = hashlib.sha256(b"fingerprint").digest()
        output_hash = hashlib.sha256(b"output").digest()
        timestamp = 1000

        struct_hash = build_eip712_struct_hash(
            job_id=job_id,
            fingerprint=fingerprint,
            merkle_root=root,
            output_hash=output_hash,
            timestamp=timestamp,
        )
        signer_address, signature = sign_struct_hash(struct_hash, private_key)

        result = verify_proof_envelope(
            leaf_data=leaf_data,
            leaf_hash=leaf_hash,
            merkle_proof=proof,
            merkle_root=root,
            job_id=job_id,
            fingerprint=fingerprint,
            output_hash=output_hash,
            timestamp=timestamp,
            signature=signature,
            expected_signer=signer_address,
        )
        assert result is True

    def test_verify_proof_wrong_root(self):
        leaves = [b"step1"]
        _, proofs = build_merkle_tree(leaves)
        leaf_hash = compute_leaf_hash(b"step1")
        wrong_root = hashlib.sha256(b"wrong").digest()

        result = verify_proof_envelope(
            leaf_data=b"step1",
            leaf_hash=leaf_hash,
            merkle_proof=proofs[0],
            merkle_root=wrong_root,
            job_id=bytes(32),
            fingerprint=bytes(32),
            output_hash=bytes(32),
            timestamp=1000,
            signature=b"\x00" * 65,
            expected_signer="0x" + "00" * 40,
        )
        assert result is False

    def test_verify_proof_wrong_signer(self):
        from app.services.eip712 import sign_struct_hash

        private_key = secrets.token_bytes(32)
        leaves = [b"step1"]
        root, proofs = build_merkle_tree(leaves)

        struct_hash = build_eip712_struct_hash(
            job_id=bytes(32),
            fingerprint=bytes(32),
            merkle_root=root,
            output_hash=bytes(32),
            timestamp=1000,
        )
        _, signature = sign_struct_hash(struct_hash, private_key)

        result = verify_proof_envelope(
            leaf_data=b"step1",
            leaf_hash=compute_leaf_hash(b"step1"),
            merkle_proof=proofs[0],
            merkle_root=root,
            job_id=bytes(32),
            fingerprint=bytes(32),
            output_hash=bytes(32),
            timestamp=1000,
            signature=signature,
            expected_signer="0x" + "dead" * 10,
        )
        assert result is False
