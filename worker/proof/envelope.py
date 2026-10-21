"""Worker serialization of the canonical EIP-712 envelope."""

from dataclasses import dataclass

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import to_checksum_address


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


def typed_data(v: ProofEnvelope) -> dict:
    pairs = [
        ("protocolVersion", "uint256"),
        ("chainId", "uint256"),
        ("verifyingContract", "address"),
        ("jobId", "bytes32"),
        ("attemptId", "bytes32"),
        ("leaseId", "bytes32"),
        ("provider", "address"),
        ("fingerprint", "bytes32"),
        ("merkleRoot", "bytes32"),
        ("outputHash", "bytes32"),
        ("proofTimestamp", "uint64"),
        ("leaseExpiresAt", "uint64"),
    ]
    contract = to_checksum_address(v.verifying_contract)
    return {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "ProofEnvelope": [{"name": n, "type": t} for n, t in pairs],
        },
        "primaryType": "ProofEnvelope",
        "domain": {
            "name": "NebulaVerifiableAI",
            "version": "1",
            "chainId": v.chain_id,
            "verifyingContract": contract,
        },
        "message": {
            "protocolVersion": v.protocol_version,
            "chainId": v.chain_id,
            "verifyingContract": contract,
            "jobId": v.job_id,
            "attemptId": v.attempt_id,
            "leaseId": v.lease_id,
            "provider": to_checksum_address(v.provider),
            "fingerprint": v.fingerprint,
            "merkleRoot": v.merkle_root,
            "outputHash": v.output_hash,
            "proofTimestamp": v.proof_timestamp,
            "leaseExpiresAt": v.lease_expires_at,
        },
    }


def sign_envelope(v: ProofEnvelope, private_key: str) -> str:
    return (
        "0x"
        + bytes(
            Account.sign_message(
                encode_typed_data(full_message=typed_data(v)), private_key=private_key
            ).signature
        ).hex()
    )
