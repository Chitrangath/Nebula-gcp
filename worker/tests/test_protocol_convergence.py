"""Golden convergence at backend/worker protocol seams."""

from app.services.eip712 import ProofEnvelope as BackendEnvelope
from app.services.eip712 import envelope_typed_data
from app.services.fingerprint import compute_fingerprint as backend_fingerprint
from app.services.merkle import build_merkle_tree
from eth_account import Account
from eth_account.messages import encode_typed_data
from proof.envelope import ProofEnvelope as WorkerEnvelope
from proof.envelope import typed_data
from proof.fingerprint import compute_fingerprint as worker_fingerprint
from proof.merkle import build_merkle_root


def test_fingerprint_convergence() -> None:
    values = {
        "job_id": "12345678-1234-5678-1234-567812345678",
        "model_id": "resnet50",
        "model_version": "1.0.0",
        "model_hash": "ab" * 32,
        "input_hash": "cd" * 32,
        "preprocessing_version": "resnet50-v1",
    }
    assert worker_fingerprint(**values) == backend_fingerprint(**values)


def test_merkle_convergence_for_frozen_resnet_checkpoint_and_output_leaves() -> None:
    leaves = [
        bytes.fromhex(value)
        for value in (
            "e43ddfc036a28b55884e8a420bf50df5cb95f3eec7e8e70ac07d0e5b60734d18",
            "2c074e7f7d944a95d10d4525077b46e88e7820e40237ef57f086cb5dc32122a7",
            "33b2d5816d9b4420fbf3b921ece831e4a6c97085bae1585b077a719e55f6a042",
            "e0392935ed95f98d180f7a265f7cdcdaecb461a23f91e78b8c59797c4dcd333e",
            "e0392935ed95f98d180f7a265f7cdcdaecb461a23f91e78b8c59797c4dcd333e",
        )
    ]
    assert build_merkle_root(leaves) == build_merkle_tree(leaves)[0]


def test_eip712_convergence() -> None:
    values = (
        1,
        421614,
        "0x" + "11" * 20,
        b"\x01" * 32,
        b"\x02" * 32,
        b"\x03" * 32,
        "0x" + "22" * 20,
        b"\x04" * 32,
        b"\x05" * 32,
        b"\x06" * 32,
        1_700_000_000,
        1_700_000_100,
    )
    backend = BackendEnvelope(*values)
    worker = WorkerEnvelope(*values)
    assert envelope_typed_data(backend) == typed_data(worker)
    key = "0x" + "33" * 32
    backend_signature = Account.sign_message(
        encode_typed_data(full_message=envelope_typed_data(backend)), private_key=key
    ).signature
    worker_signature = Account.sign_message(
        encode_typed_data(full_message=typed_data(worker)), private_key=key
    ).signature
    assert backend_signature == worker_signature
