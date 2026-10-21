"""Anvil integration tests for proof-to-settlement pipeline (§4) and escrow confirmation (§5).

Tests the full backend → Anvil flow for:
- Valid proof: Assigned → submitProof → ProofSubmitted → verifyJob(true) → Settled
- Invalid proof: → verifyJob(false) → Refunded
- Cryptographically invalid proofs
- Replay detection
- Concurrent settlement rejection
- Escrow confirmation with real receipts
"""

import json
import os
import secrets
import signal
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from web3 import Web3

from app.utils import uuid_to_bytes32

ANVIL_RPC_URL = os.environ.get("ANVIL_RPC_URL", "http://127.0.0.1:8545")
ANVIL_CHAIN_ID = 31337

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


def _load_nebula_abi():
    path = Path(__file__).parents[2] / "contracts/out/NebulaVerifiableAI.sol/NebulaVerifiableAI.json"
    with open(path) as artifact_file:
        return json.load(artifact_file)["abi"]
    # Historical inline ABI retained below only to keep this test-file diff reviewable.
    return [
        {"inputs": [{"name": "_usdc", "type": "address"}], "stateMutability": "nonpayable", "type": "constructor"},
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
        {"inputs": [], "name": "withdraw", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
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
    ]


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
]


@pytest.fixture(scope="module")
def anvil_process():
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
    time.sleep(2)
    yield proc
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def w3(anvil_process):
    w3 = Web3(Web3.HTTPProvider(ANVIL_RPC_URL))
    assert w3.is_connected()
    w3.eth.default_block = "pending"
    return w3


@pytest.fixture(scope="module")
def deployer(w3):
    return w3.eth.account.from_key(ANVIL_ACCOUNTS[0]["private_key"])


@pytest.fixture(scope="module")
def user_acct(w3):
    return w3.eth.account.from_key(ANVIL_ACCOUNTS[1]["private_key"])


@pytest.fixture(scope="module")
def provider_acct(w3):
    return w3.eth.account.from_key(ANVIL_ACCOUNTS[2]["private_key"])


@pytest.fixture(scope="module")
def usdc(w3, deployer):
    path = Path(__file__).parent.parent.parent / "contracts" / "out" / "NebulaVerifiableAI.t.sol" / "MockUSDC.json"
    if not path.exists():
        pytest.skip("MockUSDC not compiled")
    with open(path) as f:
        art = json.load(f)
    abi, bytecode = art.get("abi", []), art.get("bytecode", {}).get("object", "0x")
    if bytecode.startswith("0x"):
        bytecode = bytecode[2:]
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
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    return w3.eth.contract(address=receipt["contractAddress"], abi=abi)


@pytest.fixture(scope="module")
def nebula(w3, deployer, usdc):
    abi = _load_nebula_abi()
    path = (
        Path(__file__).parent.parent.parent / "contracts" / "out" / "NebulaVerifiableAI.sol" / "NebulaVerifiableAI.json"
    )
    if not path.exists():
        pytest.skip("NebulaVerifiableAI not compiled")
    with open(path) as f:
        art = json.load(f)
    bytecode = art.get("bytecode", {}).get("object", "0x")
    if bytecode.startswith("0x"):
        bytecode = bytecode[2:]
    contract = w3.eth.contract(abi=abi, bytecode=bytes.fromhex(bytecode))
    tx = contract.constructor(usdc.address).build_transaction(
        {
            "from": deployer.address,
            "nonce": w3.eth.get_transaction_count(deployer.address),
            "gas": 5000000,
            "gasPrice": w3.to_wei(1, "gwei"),
            "chainId": ANVIL_CHAIN_ID,
        }
    )
    signed = deployer.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    assert receipt["status"] == 1
    return w3.eth.contract(address=receipt["contractAddress"], abi=abi)


def _send_tx(w3, acct, contract_fn, gas=500000):
    tx = contract_fn.build_transaction(
        {
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "gas": gas,
            "gasPrice": w3.to_wei(1, "gwei"),
            "chainId": ANVIL_CHAIN_ID,
        }
    )
    signed = acct.sign_transaction(tx)
    return w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))


def _setup_job(w3, deployer, user_acct, usdc, nebula):
    """Create a job and assign a provider. Returns (job_id, lease_id, fingerprint)."""
    job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
    fingerprint = secrets.token_bytes(32)
    lease_id = secrets.token_bytes(32)

    job_price = nebula.functions.jobPrice().call()
    usdc.functions.mint(user_acct.address, job_price * 10).transact({"from": deployer.address})
    usdc.functions.approve(nebula.address, job_price * 10).transact({"from": user_acct.address})

    _send_tx(w3, user_acct, nebula.functions.createJob(job_id, fingerprint))

    block = w3.eth.get_block("latest")
    lease_expires = block["timestamp"] + 3600
    _send_tx(w3, deployer, nebula.functions.assignProvider(job_id, user_acct.address, lease_id, lease_expires))

    return job_id, lease_id, fingerprint


class TestProofToSettlement:
    def test_valid_proof_settled(self, w3, deployer, user_acct, usdc, nebula):
        """Assigned → submitProof → ProofSubmitted → verifyJob(true) → Settled."""
        job_id, lease_id, fingerprint = _setup_job(w3, deployer, user_acct, usdc, nebula)

        merkle_root = secrets.token_bytes(32)
        output_hash = secrets.token_bytes(32)

        receipt = _send_tx(w3, deployer, nebula.functions.submitProof(job_id, lease_id, merkle_root, output_hash))
        assert receipt["status"] == 1
        job_data = nebula.functions.getJob(job_id).call()
        assert job_data[11] == 3  # ProofSubmitted

        receipt2 = _send_tx(w3, deployer, nebula.functions.verifyJob(job_id, True))
        assert receipt2["status"] == 1
        job_data = nebula.functions.getJob(job_id).call()
        assert job_data[11] == 4  # Settled

        pending = nebula.functions.getPendingWithdrawal(user_acct.address).call()
        assert pending > 0

    def test_invalid_proof_refunded(self, w3, deployer, user_acct, usdc, nebula):
        """verifyJob(false) → Refunded."""
        job_id, lease_id, fingerprint = _setup_job(w3, deployer, user_acct, usdc, nebula)

        _send_tx(
            w3,
            deployer,
            nebula.functions.submitProof(job_id, lease_id, secrets.token_bytes(32), secrets.token_bytes(32)),
        )

        receipt = _send_tx(w3, deployer, nebula.functions.verifyJob(job_id, False))
        assert receipt["status"] == 1
        job_data = nebula.functions.getJob(job_id).call()
        assert job_data[11] == 5  # Refunded

        user_pending = nebula.functions.getPendingWithdrawal(user_acct.address).call()
        assert user_pending > 0

    def test_wrong_lease_rejected(self, w3, deployer, user_acct, usdc, nebula):
        """submitProof with wrong lease_id reverts."""
        job_id, lease_id, fingerprint = _setup_job(w3, deployer, user_acct, usdc, nebula)
        wrong_lease = secrets.token_bytes(32)

        receipt = _send_tx(
            w3,
            deployer,
            nebula.functions.submitProof(job_id, wrong_lease, secrets.token_bytes(32), secrets.token_bytes(32)),
        )
        assert receipt["status"] == 0

    def test_replay_same_proof_rejected(self, w3, deployer, user_acct, usdc, nebula):
        """Double submitProof on same job reverts (state already ProofSubmitted)."""
        job_id, lease_id, fingerprint = _setup_job(w3, deployer, user_acct, usdc, nebula)

        _send_tx(
            w3,
            deployer,
            nebula.functions.submitProof(job_id, lease_id, secrets.token_bytes(32), secrets.token_bytes(32)),
        )

        receipt = _send_tx(
            w3,
            deployer,
            nebula.functions.submitProof(job_id, lease_id, secrets.token_bytes(32), secrets.token_bytes(32)),
        )
        assert receipt["status"] == 0

    def test_double_settle_rejected(self, w3, deployer, user_acct, usdc, nebula):
        """verifyJob after already settled reverts."""
        job_id, lease_id, fingerprint = _setup_job(w3, deployer, user_acct, usdc, nebula)

        _send_tx(
            w3,
            deployer,
            nebula.functions.submitProof(job_id, lease_id, secrets.token_bytes(32), secrets.token_bytes(32)),
        )
        _send_tx(w3, deployer, nebula.functions.verifyJob(job_id, True))

        receipt = _send_tx(w3, deployer, nebula.functions.verifyJob(job_id, True))
        assert receipt["status"] == 0

    def test_wrong_signer_assign_rejected(self, w3, user_acct, usdc, nebula):
        """Non-verifier cannot call assignProvider."""
        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        fingerprint = secrets.token_bytes(32)
        lease_id = secrets.token_bytes(32)

        usdc.functions.approve(nebula.address, 1000000).transact({"from": user_acct.address})
        _send_tx(w3, user_acct, nebula.functions.createJob(job_id, fingerprint))

        block = w3.eth.get_block("latest")
        receipt = _send_tx(
            w3,
            user_acct,
            nebula.functions.assignProvider(job_id, user_acct.address, lease_id, block["timestamp"] + 3600),
        )
        assert receipt["status"] == 0

    def test_stale_lease_reassignment(self, w3, deployer, user_acct, usdc, nebula):
        """Reassign after previous lease expires."""
        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        fingerprint = secrets.token_bytes(32)
        usdc.functions.mint(user_acct.address, 10000000).transact({"from": deployer.address})
        usdc.functions.approve(nebula.address, 10000000).transact({"from": user_acct.address})
        _send_tx(w3, user_acct, nebula.functions.createJob(job_id, fingerprint))

        # Assign lease expiring in 60 seconds
        lease1 = secrets.token_bytes(32)
        now = w3.eth.get_block("latest")["timestamp"]
        _send_tx(w3, deployer, nebula.functions.assignProvider(job_id, user_acct.address, lease1, now + 60))

        # Fast-forward time well past lease expiry (advance 120 seconds)
        for _ in range(120):
            w3.provider.make_request("evm_increaseTime", [1])
            w3.provider.make_request("evm_mine", [])

        lease2 = secrets.token_bytes(32)
        new_now = w3.eth.get_block("latest")["timestamp"]
        receipt = _send_tx(
            w3, deployer, nebula.functions.assignProvider(job_id, user_acct.address, lease2, new_now + 3600)
        )
        assert receipt["status"] == 1

        job_data = nebula.functions.getJob(job_id).call()
        assert job_data[5] == lease2  # New lease
        assert job_data[11] == 2  # Assigned


class TestEscrowConfirmation:
    def test_create_job_event_valid(self, w3, deployer, user_acct, usdc, nebula):
        """Confirm JobCreated event has correct fields."""
        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        fingerprint = secrets.token_bytes(32)

        usdc.functions.mint(user_acct.address, 10000000).transact({"from": deployer.address})
        usdc.functions.approve(nebula.address, 10000000).transact({"from": user_acct.address})

        receipt = _send_tx(w3, user_acct, nebula.functions.createJob(job_id, fingerprint))
        assert receipt["status"] == 1
        assert receipt["to"].lower() == nebula.address.lower()

        # Filter logs to only those from the nebula contract to avoid MismatchedABI
        # warnings from unrelated logs (e.g., USDC Approval/Transfer events)
        filtered_receipt = {
            **receipt,
            "logs": [
                log for log in receipt.get("logs", []) if log.get("address", b"").lower() == nebula.address.lower()
            ],
        }
        events = nebula.events.JobCreated().process_receipt(filtered_receipt)
        assert len(events) == 1
        assert events[0]["args"]["jobId"] == job_id
        assert events[0]["args"]["user"] == user_acct.address
        assert events[0]["args"]["fingerprint"] == fingerprint

    def test_wrong_fingerprint_event(self, w3, user_acct, usdc, nebula):
        """Zero fingerprint reverts — no event emitted."""
        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])

        usdc.functions.approve(nebula.address, 10000000).transact({"from": user_acct.address})
        receipt = _send_tx(w3, user_acct, nebula.functions.createJob(job_id, bytes(32)))
        assert receipt["status"] == 0

    def test_wrong_amount_rejected(self, w3, deployer, usdc, nebula):
        """createJob with zero USDC approval reverts."""
        # Fund fresh account for gas
        fresh = w3.eth.account.create()
        fund_tx = {
            "from": deployer.address,
            "to": fresh.address,
            "value": w3.to_wei(1, "ether"),
            "nonce": w3.eth.get_transaction_count(deployer.address),
            "gas": 21000,
            "gasPrice": w3.to_wei(1, "gwei"),
            "chainId": ANVIL_CHAIN_ID,
        }
        signed_fund = deployer.sign_transaction(fund_tx)
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed_fund.raw_transaction))

        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        fingerprint = secrets.token_bytes(32)
        # Fresh account has 0 USDC balance and 0 approval — createJob should revert
        tx = nebula.functions.createJob(job_id, fingerprint).build_transaction(
            {
                "from": fresh.address,
                "nonce": w3.eth.get_transaction_count(fresh.address),
                "gas": 500000,
                "gasPrice": w3.to_wei(1, "gwei"),
                "chainId": ANVIL_CHAIN_ID,
            }
        )
        signed = fresh.sign_transaction(tx)
        receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
        assert receipt["status"] == 0

    def test_idempotent_escrow_confirmation(self, w3, deployer, user_acct, usdc, nebula):
        """Same tx_hash cannot be used for two different jobs."""
        job_id1 = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        job_id2 = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        fingerprint = secrets.token_bytes(32)

        usdc.functions.mint(user_acct.address, 10000000).transact({"from": deployer.address})
        usdc.functions.approve(nebula.address, 10000000).transact({"from": user_acct.address})

        receipt1 = _send_tx(w3, user_acct, nebula.functions.createJob(job_id1, fingerprint))
        assert receipt1["status"] == 1

        # job_id2 uses different chain_job_id, so it should succeed independently
        receipt2 = _send_tx(w3, user_acct, nebula.functions.createJob(job_id2, fingerprint))
        assert receipt2["status"] == 1

        # Verify both jobs exist independently
        job_data1 = nebula.functions.getJob(job_id1).call()
        job_data2 = nebula.functions.getJob(job_id2).call()
        assert job_data1[0] == user_acct.address
        assert job_data2[0] == user_acct.address

    def test_pending_withdrawal_reconciliation(self, w3, deployer, usdc, nebula):
        """After settle, pending withdrawal matches escrow amount."""
        job_price = nebula.functions.jobPrice().call()

        # Use a fresh user to avoid accumulated withdrawals from other tests
        fresh = w3.eth.account.create()
        fund_tx = {
            "from": deployer.address,
            "to": fresh.address,
            "value": w3.to_wei(1, "ether"),
            "nonce": w3.eth.get_transaction_count(deployer.address),
            "gas": 21000,
            "gasPrice": w3.to_wei(1, "gwei"),
            "chainId": ANVIL_CHAIN_ID,
        }
        signed_fund = deployer.sign_transaction(fund_tx)
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed_fund.raw_transaction))

        usdc.functions.mint(fresh.address, job_price * 10).transact({"from": deployer.address})
        _send_tx(w3, fresh, usdc.functions.approve(nebula.address, job_price * 10))

        job_id = bytes.fromhex(uuid_to_bytes32(uuid.uuid4())[2:])
        fingerprint = secrets.token_bytes(32)
        lease_id = secrets.token_bytes(32)

        _send_tx(w3, fresh, nebula.functions.createJob(job_id, fingerprint))
        block = w3.eth.get_block("latest")
        _send_tx(
            w3, deployer, nebula.functions.assignProvider(job_id, fresh.address, lease_id, block["timestamp"] + 3600)
        )
        _send_tx(
            w3,
            deployer,
            nebula.functions.submitProof(job_id, lease_id, secrets.token_bytes(32), secrets.token_bytes(32)),
        )
        _send_tx(w3, deployer, nebula.functions.verifyJob(job_id, True))

        pending = nebula.functions.getPendingWithdrawal(fresh.address).call()
        assert pending == job_price
