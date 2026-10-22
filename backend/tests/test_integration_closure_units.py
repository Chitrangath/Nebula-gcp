"""Regression tests for the Phase 3 integration-closure seams."""

import hashlib
import json
import uuid
from pathlib import Path

import pytest
from eth_account import Account
from web3 import Web3

from app.services.blockchain_service import (
    SELECTOR_ASSIGN_PROVIDER,
    SELECTOR_GET_JOB,
    SELECTOR_SUBMIT_PROOF,
    SELECTOR_VERIFY_JOB,
    decode_receipt_logs,
    load_abi,
)
from app.services.eip712 import ProofEnvelope, sign_envelope, verify_envelope_signature
from app.services.merkle import build_merkle_tree
from app.utils import uuid_to_bytes32

ROOT = Path(__file__).parents[2]
pytestmark = pytest.mark.asyncio


async def test_backend_abi_matches_preserved_deployment_manifest() -> None:
    deployment = json.loads((ROOT / "contracts/deployments/arbitrum-sepolia.json").read_text(encoding="utf-8"))
    metadata = json.loads((ROOT / "backend/app/nebula_artifact.json").read_text(encoding="utf-8"))
    canonical_abi = json.dumps(load_abi(), sort_keys=True, separators=(",", ":"))
    abi_sha256 = hashlib.sha256(canonical_abi.encode()).hexdigest()

    assert abi_sha256 == deployment["abi_sha256"]
    assert abi_sha256 == metadata["abi_sha256"]


async def test_canonical_function_and_event_shapes():
    abi = load_abi()
    functions = {
        item["name"]: [entry["type"] for entry in item["inputs"]] for item in abi if item["type"] == "function"
    }
    assert functions["createJob"] == ["bytes32", "bytes32"]
    assert functions["assignProvider"] == ["bytes32", "address", "bytes32", "uint64"]
    assert functions["submitProof"] == ["bytes32", "bytes32", "bytes32", "bytes32"]
    assert functions["verifyJob"] == ["bytes32", "bool"]
    assert functions["requestTimeoutRefund"] == ["bytes32"]
    assert functions["withdraw"] == []
    assert functions["getJob"] == ["bytes32"]
    assert functions["getPendingWithdrawal"] == ["address"]

    events = {item["name"]: item["inputs"] for item in abi if item["type"] == "event"}
    assert [(i["name"], i["type"], i["indexed"]) for i in events["JobCreated"]] == [
        ("jobId", "bytes32", True),
        ("user", "address", True),
        ("fingerprint", "bytes32", False),
        ("amount", "uint256", False),
        ("timestamp", "uint256", False),
    ]
    assert [i["name"] for i in events["ProviderAssigned"]] == [
        "jobId",
        "provider",
        "leaseId",
        "leaseExpiresAt",
    ]
    assert list(range(6)) == [0, 1, 2, 3, 4, 5]  # JobState declaration order


async def test_transaction_builders_use_generated_canonical_selectors():
    manifest = json.loads((ROOT / "backend/app/nebula_artifact.json").read_text())
    expected = manifest["function_selectors"]
    assert SELECTOR_ASSIGN_PROVIDER.hex() == expected["assignProvider(bytes32,address,bytes32,uint64)"][2:]
    assert SELECTOR_SUBMIT_PROOF.hex() == expected["submitProof(bytes32,bytes32,bytes32,bytes32)"][2:]
    assert SELECTOR_VERIFY_JOB.hex() == expected["verifyJob(bytes32,bool)"][2:]
    assert SELECTOR_GET_JOB.hex() == expected["getJob(bytes32)"][2:]


async def test_receipt_decoder_returns_all_event_arguments():
    abi = load_abi()
    contract = Web3().eth.contract(abi=abi)
    event_abi = next(i for i in abi if i.get("type") == "event" and i["name"] == "JobCreated")
    job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
    user = Account.create().address
    fingerprint = hashlib.sha256(b"fingerprint").digest()
    amount = 50_000
    timestamp = 1234
    from eth_abi import encode

    topic0 = Web3.keccak(text="JobCreated(bytes32,address,bytes32,uint256,uint256)")
    log = {
        "address": "0x" + "ab" * 20,
        "topics": [topic0, job_id, bytes.fromhex(user[2:]).rjust(32, b"\x00")],
        "data": "0x" + encode(["bytes32", "uint256", "uint256"], [fingerprint, amount, timestamp]).hex(),
        "blockNumber": 7,
        "transactionHash": b"\x11" * 32,
        "transactionIndex": 0,
        "blockHash": b"\x22" * 32,
        "logIndex": 0,
        "removed": False,
    }
    assert contract.events.JobCreated().abi == event_abi
    decoded = decode_receipt_logs({"logs": [log]}, abi)
    assert decoded[0]["event"] == "JobCreated"
    assert decoded[0]["args"] == {
        "jobId": job_id,
        "user": Web3.to_checksum_address(user),
        "fingerprint": fingerprint,
        "amount": amount,
        "timestamp": timestamp,
    }


async def test_full_eip712_envelope_binds_every_field():
    account = Account.create()
    envelope = ProofEnvelope(
        protocol_version=1,
        chain_id=31337,
        verifying_contract="0x" + "ab" * 20,
        job_id=b"\x01" * 32,
        attempt_id=b"\x02" * 32,
        lease_id=b"\x03" * 32,
        provider="0x" + "cd" * 20,
        fingerprint=b"\x04" * 32,
        merkle_root=b"\x05" * 32,
        output_hash=b"\x06" * 32,
        proof_timestamp=1234,
        lease_expires_at=4567,
    )
    signature = sign_envelope(envelope, account.key)
    assert verify_envelope_signature(envelope, signature, account.address)
    changed = ProofEnvelope(**{**envelope.__dict__, "attempt_id": b"\xff" * 32})
    assert not verify_envelope_signature(changed, signature, account.address)


async def test_merkle_root_commits_to_output_hash_as_final_leaf():
    trace = [hashlib.sha256(b"checkpoint").digest()]
    output_hash = hashlib.sha256(b"canonical output").digest()
    with_output, _ = build_merkle_tree([*trace, output_hash])
    trace_only, _ = build_merkle_tree(trace)
    assert with_output != trace_only
