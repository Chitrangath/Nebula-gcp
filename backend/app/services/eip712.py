"""Canonical EIP-712 worker proof envelope."""

from __future__ import annotations

from dataclasses import dataclass

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from web3 import Web3


@dataclass(frozen=True)
class ProofEnvelope:
    protocol_version: int
    chain_id: int
    verifying_contract: str
    job_id: bytes
    attempt_id: bytes
    lease_id: bytes
    provider: str
    fingerprint: bytes
    merkle_root: bytes
    output_hash: bytes
    proof_timestamp: int
    lease_expires_at: int


PROOF_TYPES = {
    "ProofEnvelope": [
        {"name": "protocolVersion", "type": "uint256"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
        {"name": "jobId", "type": "bytes32"},
        {"name": "attemptId", "type": "bytes32"},
        {"name": "leaseId", "type": "bytes32"},
        {"name": "provider", "type": "address"},
        {"name": "fingerprint", "type": "bytes32"},
        {"name": "merkleRoot", "type": "bytes32"},
        {"name": "outputHash", "type": "bytes32"},
        {"name": "proofTimestamp", "type": "uint64"},
        {"name": "leaseExpiresAt", "type": "uint64"},
    ]
}


def envelope_typed_data(envelope: ProofEnvelope) -> dict:
    """Return the sole canonical typed-data representation used on the wire."""
    contract = Web3.to_checksum_address(envelope.verifying_contract)
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            **PROOF_TYPES,
        },
        "primaryType": "ProofEnvelope",
        "domain": {
            "name": "NebulaVerifiableAI",
            "version": "1",
            "chainId": envelope.chain_id,
            "verifyingContract": contract,
        },
        "message": {
            "protocolVersion": envelope.protocol_version,
            "chainId": envelope.chain_id,
            "verifyingContract": contract,
            "jobId": envelope.job_id,
            "attemptId": envelope.attempt_id,
            "leaseId": envelope.lease_id,
            "provider": Web3.to_checksum_address(envelope.provider),
            "fingerprint": envelope.fingerprint,
            "merkleRoot": envelope.merkle_root,
            "outputHash": envelope.output_hash,
            "proofTimestamp": envelope.proof_timestamp,
            "leaseExpiresAt": envelope.lease_expires_at,
        },
    }


def sign_envelope(envelope: ProofEnvelope, private_key: bytes | str) -> bytes:
    message = encode_typed_data(full_message=envelope_typed_data(envelope))
    return bytes(Account.sign_message(message, private_key=private_key).signature)


def verify_envelope_signature(envelope: ProofEnvelope, signature: bytes | str, expected_address: str) -> bool:
    try:
        message = encode_typed_data(full_message=envelope_typed_data(envelope))
        recovered = Account.recover_message(message, signature=signature)
        return recovered.lower() == expected_address.lower()
    except (TypeError, ValueError):
        return False


# Compatibility wrappers for existing Phase 3 unit callers. New protocol code
# uses ProofEnvelope above. These still use EVM Keccak rather than SHA-256.
def build_eip712_struct_hash(
    *, job_id: bytes, fingerprint: bytes, merkle_root: bytes, output_hash: bytes, timestamp: int
) -> bytes:
    type_hash = keccak(
        text="ProofEnvelope(bytes32 jobId,bytes32 fingerprint,bytes32 merkleRoot,bytes32 outputHash,uint256 timestamp)"
    )
    return keccak(type_hash + job_id + fingerprint + merkle_root + output_hash + timestamp.to_bytes(32, "big"))


def _legacy_typed_data(struct_hash: bytes) -> dict:
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "ProofHash": [{"name": "value", "type": "bytes32"}],
        },
        "primaryType": "ProofHash",
        "domain": {
            "name": "NebulaVerifiableAI",
            "version": "1",
            "chainId": 421614,
            "verifyingContract": "0x" + "00" * 20,
        },
        "message": {"value": struct_hash},
    }


def sign_struct_hash(struct_hash: bytes, private_key: bytes) -> tuple[str, bytes]:
    account = Account.from_key(private_key)
    signed = account.sign_message(encode_typed_data(full_message=_legacy_typed_data(struct_hash)))
    return account.address, bytes(signed.signature)


def recover_signer(struct_hash: bytes, private_key: bytes) -> tuple[str, bytes]:
    return sign_struct_hash(struct_hash, private_key)


def verify_signature(struct_hash: bytes, signature: bytes, expected_address: str) -> bool:
    try:
        message = encode_typed_data(full_message=_legacy_typed_data(struct_hash))
        return Account.recover_message(message, signature=signature).lower() == expected_address.lower()
    except (TypeError, ValueError):
        return False
