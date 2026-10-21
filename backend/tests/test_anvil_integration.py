"""Anvil integration tests for the full escrow and contract lifecycle (§2).

Starts a deterministic Anvil instance, deploys MockUSDC + NebulaVerifiableAI,
and tests real-RPC flows: createJob → confirm → assignProvider → submitProof → verifyJob.
"""

import json
import os
import signal
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from web3 import Web3
from web3.constants import ADDRESS_ZERO

from app.utils import uuid_to_bytes32

# Deterministic Anvil accounts (DO NOT use in production)
ANVIL_ACCOUNTS = [
    {
        "address": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "private_key": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    },
    {
        "address": "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "private_key": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    },
    {
        "address": "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
        "private_key": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    },
]

# Contract ABIs
NEBULA_ABI_PATH = (
    Path(__file__).parent.parent.parent / "contracts" / "out" / "NebulaVerifiableAI.sol" / "NebulaVerifiableAI.json"
)
ERC20_ABI_PATH = (
    Path(__file__).parent.parent.parent
    / "contracts"
    / "lib"
    / "openzeppelin-contracts"
    / "contracts"
    / "token"
    / "ERC20"
    / "ERC20.json"
)


def _load_contract_abi(name: str) -> list[dict]:
    """Load compiled contract ABI from forge output."""
    # Try forge out directory
    forge_out = Path(__file__).parent.parent.parent / "contracts" / "out"
    abi_file = forge_out / f"{name}.sol" / f"{name}.json"
    if abi_file.exists():
        with open(abi_file) as f:
            data = json.load(f)
            return data.get("abi", [])

    # Try OpenZeppelin lib
    oz_file = Path(__file__).parent.parent.parent / "contracts" / "lib" / "openzeppelin-contracts"
    for p in oz_file.rglob(f"{name}.json"):
        with open(p) as f:
            data = json.load(f)
            if "abi" in data:
                return data["abi"]
    return []


# Minimal ERC20 ABI for mint/approve/balanceOf
ERC20_MINIMAL_ABI = [
    {
        "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def _load_nebula_abi() -> list[dict]:
    """Load NebulaVerifiableAI ABI."""
    with open(NEBULA_ABI_PATH) as artifact_file:
        return json.load(artifact_file)["abi"]
    # Historical inline ABI retained below only to keep this test-file diff reviewable.
    return [
        {
            "inputs": [{"name": "_usdc", "type": "address"}],
            "stateMutability": "nonpayable",
            "type": "constructor",
        },
        {
            "inputs": [{"name": "chainJobId", "type": "bytes32"}, {"name": "fingerprint", "type": "bytes32"}],
            "name": "createJob",
            "outputs": [{"name": "jobId", "type": "bytes32"}],
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "inputs": [
                {"name": "jobId", "type": "bytes32"},
                {"name": "provider", "type": "address"},
                {"name": "leaseId", "type": "bytes32"},
                {"name": "leaseExpiresAt", "type": "uint64"},
            ],
            "name": "assignProvider",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "inputs": [
                {"name": "jobId", "type": "bytes32"},
                {"name": "leaseId", "type": "bytes32"},
                {"name": "merkleRoot", "type": "bytes32"},
                {"name": "outputHash", "type": "bytes32"},
            ],
            "name": "submitProof",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "inputs": [{"name": "jobId", "type": "bytes32"}, {"name": "isValid", "type": "bool"}],
            "name": "verifyJob",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "inputs": [{"name": "jobId", "type": "bytes32"}],
            "name": "getJob",
            "outputs": [
                {"name": "user", "type": "address"},
                {"name": "provider", "type": "address"},
                {"name": "fingerprint", "type": "bytes32"},
                {"name": "merkleRoot", "type": "bytes32"},
                {"name": "outputHash", "type": "bytes32"},
                {"name": "leaseId", "type": "bytes32"},
                {"name": "amount", "type": "uint256"},
                {"name": "leaseExpiresAt", "type": "uint64"},
                {"name": "jobDeadline", "type": "uint64"},
                {"name": "createdAt", "type": "uint64"},
                {"name": "completedAt", "type": "uint64"},
                {"name": "state", "type": "uint8"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [{"name": "account", "type": "address"}],
            "name": "getPendingWithdrawal",
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [],
            "name": "jobPrice",
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [],
            "name": "token",
            "outputs": [{"name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [],
            "name": "withdraw",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "jobId", "type": "bytes32"},
                {"indexed": True, "name": "user", "type": "address"},
                {"indexed": False, "name": "fingerprint", "type": "bytes32"},
                {"indexed": False, "name": "amount", "type": "uint256"},
                {"indexed": False, "name": "timestamp", "type": "uint256"},
            ],
            "name": "JobCreated",
            "type": "event",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "jobId", "type": "bytes32"},
                {"indexed": True, "name": "provider", "type": "address"},
                {"indexed": False, "name": "leaseId", "type": "bytes32"},
                {"indexed": False, "name": "leaseExpiresAt", "type": "uint64"},
            ],
            "name": "ProviderAssigned",
            "type": "event",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "jobId", "type": "bytes32"},
                {"indexed": False, "name": "leaseId", "type": "bytes32"},
                {"indexed": False, "name": "merkleRoot", "type": "bytes32"},
                {"indexed": False, "name": "outputHash", "type": "bytes32"},
                {"indexed": False, "name": "provider", "type": "address"},
            ],
            "name": "ProofSubmitted",
            "type": "event",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "jobId", "type": "bytes32"},
                {"indexed": False, "name": "valid", "type": "bool"},
                {"indexed": False, "name": "timestamp", "type": "uint256"},
            ],
            "name": "JobSettled",
            "type": "event",
        },
        {
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "jobId", "type": "bytes32"},
                {"indexed": True, "name": "provider", "type": "address"},
                {"indexed": False, "name": "amount", "type": "uint256"},
            ],
            "name": "PaymentCredited",
            "type": "event",
        },
    ]


ANVIL_RPC_URL = os.environ.get("ANVIL_RPC_URL", "http://127.0.0.1:8545")
ANVIL_CHAIN_ID = 31337


@pytest.fixture(scope="module")
def anvil_process():
    """Start a deterministic Anvil instance for the test module."""
    proc = subprocess.Popen(
        [
            "anvil",
            "--host",
            "127.0.0.1",
            "--port",
            "8545",
            "--chain-id",
            str(ANVIL_CHAIN_ID),
            "--accounts",
            "10",
            "--balance",
            "10000",
            "--mnemonic",
            "test test test test test test test test test test test junk",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)  # Wait for Anvil to start
    yield proc
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def w3(anvil_process):
    """Connect Web3 to the running Anvil instance."""
    w3 = Web3(Web3.HTTPProvider(ANVIL_RPC_URL))
    assert w3.is_connected(), "Failed to connect to Anvil"
    assert w3.eth.chain_id == ANVIL_CHAIN_ID
    # Include pending convenience ``Contract.transact`` calls when locally
    # signing the next transaction; this removes an automining nonce race.
    w3.eth.default_block = "pending"
    return w3


@pytest.fixture(scope="module")
def deployer(w3):
    """The deployer account (Anvil account 0)."""
    acct = ANVIL_ACCOUNTS[0]
    return w3.eth.account.from_key(acct["private_key"])


@pytest.fixture(scope="module")
def user_account(w3):
    """A test user account (Anvil account 1)."""
    acct = ANVIL_ACCOUNTS[1]
    return w3.eth.account.from_key(acct["private_key"])


@pytest.fixture(scope="module")
def provider_account(w3):
    """A test provider account (Anvil account 2)."""
    acct = ANVIL_ACCOUNTS[2]
    return w3.eth.account.from_key(acct["private_key"])


@pytest.fixture(scope="module")
def usdc_contract(w3, deployer):
    """Deploy MockUSDC using inline Solidity compilation."""
    # We'll deploy a minimal ERC20 via a factory approach
    # For simplicity, use the forge-compiled MockUSDC
    # Since we may not have compiled it for Python, deploy a minimal mock

    # Deploy using forge's compiled MockUSDC
    mock_artifact_path = (
        Path(__file__).parent.parent.parent / "contracts" / "out" / "NebulaVerifiableAI.t.sol" / "MockUSDC.json"
    )
    if mock_artifact_path.exists():
        with open(mock_artifact_path) as f:
            artifact = json.load(f)
        abi = artifact.get("abi", [])
        bytecode = artifact.get("bytecode", {}).get("object", "0x")
        if bytecode.startswith("0x"):
            bytecode = bytecode[2:]
    else:
        pytest.skip("MockUSDC not compiled. Run: cd contracts && forge build")
        return  # unreachable, keeps linter happy

    contract = w3.eth.contract(abi=abi, bytecode=bytes.fromhex(bytecode))
    tx = contract.constructor().build_transaction(
        {
            "from": deployer.address,
            "nonce": w3.eth.get_transaction_count(deployer.address),
            "gas": 3000000,
            "gasPrice": w3.to_wei(1, "gwei"),
            "chainId": ANVIL_CHAIN_ID,
        }
    )
    signed = deployer.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return w3.eth.contract(address=receipt["contractAddress"], abi=abi)


@pytest.fixture(scope="module")
def nebula_contract(w3, deployer, user_account, usdc_contract):
    """Deploy NebulaVerifiableAI."""
    abi = _load_nebula_abi()

    # Get bytecode from forge output
    artifact_path = (
        Path(__file__).parent.parent.parent / "contracts" / "out" / "NebulaVerifiableAI.sol" / "NebulaVerifiableAI.json"
    )
    if artifact_path.exists():
        with open(artifact_path) as f:
            artifact = json.load(f)
        bytecode = artifact.get("bytecode", {}).get("object", "0x")
        if bytecode.startswith("0x"):
            bytecode = bytecode[2:]
    else:
        pytest.skip("NebulaVerifiableAI not compiled. Run: cd contracts && forge build")

    contract = w3.eth.contract(abi=abi, bytecode=bytes.fromhex(bytecode))
    tx = contract.constructor(usdc_contract.address).build_transaction(
        {
            "from": deployer.address,
            "nonce": w3.eth.get_transaction_count(deployer.address),
            "gas": 5000000,
            "gasPrice": w3.to_wei(1, "gwei"),
            "chainId": ANVIL_CHAIN_ID,
        }
    )
    signed = deployer.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    assert receipt["status"] == 1, "NebulaVerifiableAI deployment failed"
    funding_hash = usdc_contract.functions.mint(user_account.address, 10_000_000).transact({"from": deployer.address})
    w3.eth.wait_for_transaction_receipt(funding_hash)
    return w3.eth.contract(address=receipt["contractAddress"], abi=abi)


# ═══════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════


class TestAnvilEscrow:
    """Full escrow lifecycle against a real Anvil node."""

    def test_deploy_contracts(self, usdc_contract, nebula_contract):
        """Both contracts deploy successfully."""
        assert usdc_contract.address != ADDRESS_ZERO
        assert nebula_contract.address != ADDRESS_ZERO

    def test_chain_id(self, w3):
        """Connected to correct chain."""
        assert w3.eth.chain_id == ANVIL_CHAIN_ID

    def test_create_job_escrow_flow(self, w3, deployer, user_account, usdc_contract, nebula_contract):
        """Full flow: mint USDC → approve → createJob → verify receipt → confirm backend."""
        # Step 1: Backend generates UUID and canonical bytes32
        job_uuid = uuid.uuid4()
        from app.utils import uuid_to_bytes32

        chain_job_id_hex = uuid_to_bytes32(job_uuid)  # 0x + 64 hex
        chain_job_id_bytes = bytes.fromhex(chain_job_id_hex[2:])  # 32 bytes left-aligned

        # Step 2: Backend computes fingerprint
        from app.services.fingerprint import compute_fingerprint

        fingerprint = compute_fingerprint(
            job_id=str(job_uuid),
            model_id="resnet50",
            model_version="1.0",
            model_hash="ab" * 32,
            input_hash="cd" * 32,
            preprocessing_version="resnet50-v1",
        )

        # Step 3: User approves USDC spending
        job_price = nebula_contract.functions.jobPrice().call()
        usdc_contract.functions.mint(user_account.address, job_price * 10).transact({"from": deployer.address})
        usdc_contract.functions.approve(nebula_contract.address, job_price * 10).transact(
            {"from": user_account.address}
        )

        # Step 4: User calls createJob
        tx = nebula_contract.functions.createJob(chain_job_id_bytes, fingerprint).build_transaction(
            {
                "from": user_account.address,
                "nonce": w3.eth.get_transaction_count(user_account.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed = user_account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        # Step 5: Verify receipt
        assert receipt["status"] == 1, "createJob transaction failed"
        assert receipt["to"].lower() == nebula_contract.address.lower()
        assert len(receipt["logs"]) > 0, "No events emitted"

        # Decode JobCreated event — filter logs to only nebula contract
        filtered_receipt = {
            **receipt,
            "logs": [
                log
                for log in receipt.get("logs", [])
                if log.get("address", b"").lower() == nebula_contract.address.lower()
            ],
        }
        job_created_event = nebula_contract.events.JobCreated().process_receipt(filtered_receipt)
        assert len(job_created_event) == 1, f"Expected 1 JobCreated event, got {len(job_created_event)}"
        event = job_created_event[0]
        assert event["args"]["jobId"] == chain_job_id_bytes
        assert event["args"]["user"] == user_account.address
        assert event["args"]["fingerprint"] == fingerprint
        assert event["args"]["amount"] == job_price

        # Step 6: Backend confirms on-chain state
        job_data = nebula_contract.functions.getJob(chain_job_id_bytes).call()
        assert job_data[0] == user_account.address  # user
        assert job_data[2] == fingerprint  # fingerprint
        assert job_data[6] == job_price  # amount
        assert job_data[11] == 1  # state == Created

        # Step 7: Backend transitions job to queued

        # The receipt confirms the job was created on-chain
        # Backend marks as queued
        # (This would normally happen via event ingestion, tested separately)

    def test_duplicate_create_job_rejected(self, w3, user_account, usdc_contract, nebula_contract):
        """Same chain_job_id cannot create two jobs."""
        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        fingerprint = bytes(range(32))

        usdc_contract.functions.approve(nebula_contract.address, 1000000).transact({"from": user_account.address})

        # First createJob succeeds
        tx1 = nebula_contract.functions.createJob(job_id, fingerprint).build_transaction(
            {
                "from": user_account.address,
                "nonce": w3.eth.get_transaction_count(user_account.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed1 = user_account.sign_transaction(tx1)
        tx_hash1 = w3.eth.send_raw_transaction(signed1.raw_transaction)
        receipt1 = w3.eth.wait_for_transaction_receipt(tx_hash1)
        assert receipt1["status"] == 1

        # Second createJob with same ID reverts
        tx2 = nebula_contract.functions.createJob(job_id, fingerprint).build_transaction(
            {
                "from": user_account.address,
                "nonce": w3.eth.get_transaction_count(user_account.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed2 = user_account.sign_transaction(tx2)
        tx_hash2 = w3.eth.send_raw_transaction(signed2.raw_transaction)
        receipt2 = w3.eth.wait_for_transaction_receipt(tx_hash2)
        assert receipt2["status"] == 0, "Duplicate createJob should revert"

    def test_assign_provider(self, w3, deployer, user_account, provider_account, usdc_contract, nebula_contract):
        """assignProvider by owner succeeds, creates ProviderAssigned event."""
        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        fingerprint = bytes(range(32))

        usdc_contract.functions.approve(nebula_contract.address, 1000000).transact({"from": user_account.address})
        tx = nebula_contract.functions.createJob(job_id, fingerprint).build_transaction(
            {
                "from": user_account.address,
                "nonce": w3.eth.get_transaction_count(user_account.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed = user_account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        w3.eth.wait_for_transaction_receipt(tx_hash)

        # assignProvider by owner
        lease_id = bytes(range(32))
        block = w3.eth.get_block("latest")
        lease_expires = block["timestamp"] + 3600  # 1 hour from now

        tx2 = nebula_contract.functions.assignProvider(
            job_id, provider_account.address, lease_id, lease_expires
        ).build_transaction(
            {
                "from": deployer.address,
                "nonce": w3.eth.get_transaction_count(deployer.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed2 = deployer.sign_transaction(tx2)
        tx_hash2 = w3.eth.send_raw_transaction(signed2.raw_transaction)
        receipt2 = w3.eth.wait_for_transaction_receipt(tx_hash2)
        assert receipt2["status"] == 1

        # Verify ProviderAssigned event
        events = nebula_contract.events.ProviderAssigned().process_receipt(receipt2)
        assert len(events) == 1
        assert events[0]["args"]["jobId"] == job_id
        assert events[0]["args"]["provider"] == provider_account.address
        assert events[0]["args"]["leaseId"] == lease_id

        # Verify on-chain state
        job_data = nebula_contract.functions.getJob(job_id).call()
        assert job_data[1] == provider_account.address  # provider
        assert job_data[5] == lease_id  # leaseId
        assert job_data[11] == 2  # state == Assigned

    def test_submit_proof_and_verify(
        self, w3, deployer, user_account, provider_account, usdc_contract, nebula_contract
    ):
        """Full lifecycle: createJob → assignProvider → submitProof → verifyJob(valid)."""
        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        fingerprint = bytes(range(32))

        # Create job
        usdc_contract.functions.approve(nebula_contract.address, 1000000).transact({"from": user_account.address})
        tx = nebula_contract.functions.createJob(job_id, fingerprint).build_transaction(
            {
                "from": user_account.address,
                "nonce": w3.eth.get_transaction_count(user_account.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed = user_account.sign_transaction(tx)
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

        # Assign provider
        lease_id = bytes(range(32))
        block = w3.eth.get_block("latest")
        lease_expires = block["timestamp"] + 3600
        tx2 = nebula_contract.functions.assignProvider(
            job_id, provider_account.address, lease_id, lease_expires
        ).build_transaction(
            {
                "from": deployer.address,
                "nonce": w3.eth.get_transaction_count(deployer.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed2 = deployer.sign_transaction(tx2)
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed2.raw_transaction))

        # Submit proof (as verifier = deployer)
        merkle_root = bytes(range(32))
        output_hash = bytes(range(32))
        tx3 = nebula_contract.functions.submitProof(job_id, lease_id, merkle_root, output_hash).build_transaction(
            {
                "from": deployer.address,
                "nonce": w3.eth.get_transaction_count(deployer.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed3 = deployer.sign_transaction(tx3)
        receipt3 = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed3.raw_transaction))
        assert receipt3["status"] == 1

        # Verify state is ProofSubmitted
        job_data = nebula_contract.functions.getJob(job_id).call()
        assert job_data[11] == 3  # state == ProofSubmitted

        # Verify job (valid)
        tx4 = nebula_contract.functions.verifyJob(job_id, True).build_transaction(
            {
                "from": deployer.address,
                "nonce": w3.eth.get_transaction_count(deployer.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed4 = deployer.sign_transaction(tx4)
        receipt4 = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed4.raw_transaction))
        assert receipt4["status"] == 1

        # Verify state is Settled
        job_data = nebula_contract.functions.getJob(job_id).call()
        assert job_data[11] == 4  # state == Settled

        # Verify provider has pending withdrawal
        pending = nebula_contract.functions.getPendingWithdrawal(provider_account.address).call()
        assert pending > 0

    def test_wrong_sender_assign_rejected(self, w3, user_account, provider_account, usdc_contract, nebula_contract):
        """Non-owner cannot call assignProvider."""
        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        fingerprint = bytes(range(32))

        usdc_contract.functions.approve(nebula_contract.address, 1000000).transact({"from": user_account.address})
        tx = nebula_contract.functions.createJob(job_id, fingerprint).build_transaction(
            {
                "from": user_account.address,
                "nonce": w3.eth.get_transaction_count(user_account.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed = user_account.sign_transaction(tx)
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

        # User tries to assignProvider (should fail - not owner)
        lease_id = bytes(range(32))
        block = w3.eth.get_block("latest")
        lease_expires = block["timestamp"] + 3600
        tx2 = nebula_contract.functions.assignProvider(
            job_id, provider_account.address, lease_id, lease_expires
        ).build_transaction(
            {
                "from": user_account.address,
                "nonce": w3.eth.get_transaction_count(user_account.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed2 = user_account.sign_transaction(tx2)
        receipt2 = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed2.raw_transaction))
        assert receipt2["status"] == 0, "Non-owner assignProvider should revert"

    def test_wrong_fingerprint_rejected(self, w3, user_account, usdc_contract, nebula_contract):
        """Zero fingerprint is rejected."""
        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        zero_fingerprint = bytes(32)

        usdc_contract.functions.approve(nebula_contract.address, 1000000).transact({"from": user_account.address})
        tx = nebula_contract.functions.createJob(job_id, zero_fingerprint).build_transaction(
            {
                "from": user_account.address,
                "nonce": w3.eth.get_transaction_count(user_account.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed = user_account.sign_transaction(tx)
        receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
        assert receipt["status"] == 0, "Zero fingerprint should be rejected"

    def test_non_canonical_job_id_rejected(self, w3, user_account, usdc_contract, nebula_contract):
        """Non-canonical bytes32 (non-zero right 16 bytes) is rejected."""
        # Create a job ID with non-zero right half
        non_canonical = bytes(range(32))  # All 32 bytes are non-zero

        usdc_contract.functions.approve(nebula_contract.address, 1000000).transact({"from": user_account.address})
        tx = nebula_contract.functions.createJob(non_canonical, bytes(range(32))).build_transaction(
            {
                "from": user_account.address,
                "nonce": w3.eth.get_transaction_count(user_account.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed = user_account.sign_transaction(tx)
        receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
        assert receipt["status"] == 0, "Non-canonical job ID should be rejected"

    def test_verify_invalid_job(self, w3, deployer, user_account, provider_account, usdc_contract, nebula_contract):
        """verifyJob(isValid=false) refunds user."""
        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        fingerprint = bytes(range(32))

        usdc_contract.functions.approve(nebula_contract.address, 1000000).transact({"from": user_account.address})
        tx = nebula_contract.functions.createJob(job_id, fingerprint).build_transaction(
            {
                "from": user_account.address,
                "nonce": w3.eth.get_transaction_count(user_account.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed = user_account.sign_transaction(tx)
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

        lease_id = bytes(range(32))
        block = w3.eth.get_block("latest")
        lease_expires = block["timestamp"] + 3600
        tx2 = nebula_contract.functions.assignProvider(
            job_id, provider_account.address, lease_id, lease_expires
        ).build_transaction(
            {
                "from": deployer.address,
                "nonce": w3.eth.get_transaction_count(deployer.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed2 = deployer.sign_transaction(tx2)
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed2.raw_transaction))

        tx3 = nebula_contract.functions.submitProof(
            job_id, lease_id, bytes(range(32)), bytes(range(32))
        ).build_transaction(
            {
                "from": deployer.address,
                "nonce": w3.eth.get_transaction_count(deployer.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed3 = deployer.sign_transaction(tx3)
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed3.raw_transaction))

        # Verify invalid
        tx4 = nebula_contract.functions.verifyJob(job_id, False).build_transaction(
            {
                "from": deployer.address,
                "nonce": w3.eth.get_transaction_count(deployer.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed4 = deployer.sign_transaction(tx4)
        receipt4 = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed4.raw_transaction))
        assert receipt4["status"] == 1

        job_data = nebula_contract.functions.getJob(job_id).call()
        assert job_data[11] == 5  # state == Refunded

        # User has pending withdrawal
        pending = nebula_contract.functions.getPendingWithdrawal(user_account.address).call()
        assert pending > 0
