"""Blockchain transaction service: real Web3 + fake for unit tests.

Production shape for:
- Receipt retrieval, contract reads
- assignProvider, submitProof, verifyJob
- Gas estimation, nonce coordination
- Transaction state tracking, timeouts, replacement, revert handling
"""

import json
from pathlib import Path
from typing import Any, Protocol

from eth_abi import decode, encode
from web3 import Web3
from web3._utils.events import get_event_data
from web3.types import TxReceipt

ABI_PATH = Path(__file__).parent.parent / "nebula_abi.json"

# Solidity function selectors (first 4 bytes of keccak256)
SELECTOR_ASSIGN_PROVIDER = bytes.fromhex("4e583fbf")  # assignProvider(bytes32,address,bytes32,uint64)
SELECTOR_SUBMIT_PROOF = bytes.fromhex("3521e00d")  # submitProof(bytes32,bytes32,bytes32,bytes32)
SELECTOR_VERIFY_JOB = bytes.fromhex("d3164c32")  # verifyJob(bytes32,bool)
SELECTOR_GET_JOB = bytes.fromhex("f729cf0d")  # getJob(bytes32)
GET_JOB_OUTPUT_TYPES = [
    "address",
    "address",
    "bytes32",
    "bytes32",
    "bytes32",
    "bytes32",
    "uint256",
    "uint64",
    "uint64",
    "uint64",
    "uint64",
    "uint8",
]


def load_abi() -> list[dict]:
    """Load the contract ABI from the JSON file."""
    with open(ABI_PATH) as f:
        return json.load(f)


def read_contract_job(blockchain: "BlockchainBackend", contract_address: str, job_id: bytes) -> dict[str, Any]:
    """Read the canonical on-chain Job tuple through the backend abstraction."""
    calldata = SELECTOR_GET_JOB + encode(["bytes32"], [job_id])
    values = decode(GET_JOB_OUTPUT_TYPES, blockchain.call_contract(contract_address, calldata))
    names = [
        "user",
        "provider",
        "fingerprint",
        "merkle_root",
        "output_hash",
        "lease_id",
        "amount",
        "lease_expires_at",
        "job_deadline",
        "created_at",
        "completed_at",
        "state",
    ]
    return dict(zip(names, values, strict=True))


class BlockchainBackend(Protocol):
    """Protocol for blockchain interaction backends."""

    def is_connected(self) -> bool: ...

    def get_chain_id(self) -> int: ...

    def get_block_number(self) -> int: ...

    def get_transaction_receipt(self, tx_hash: str) -> TxReceipt | None: ...

    def get_transaction(self, tx_hash: str) -> dict[str, Any] | None: ...

    def get_logs(self, filter_params: dict[str, Any]) -> list[dict[str, Any]]: ...

    def get_block(self, block_identifier: int | str) -> dict[str, Any]: ...

    def get_gas_price(self) -> int: ...

    def send_transaction(self, tx: dict[str, Any]) -> str: ...

    def estimate_gas(self, tx: dict[str, Any]) -> int: ...

    def get_transaction_count(self, address: str, block_identifier: str = "pending") -> int: ...

    def call_contract(self, to: str, data: bytes) -> bytes: ...

    def get_balance(self, address: str) -> int: ...

    def wait_for_receipt(self, tx_hash: str, timeout: float = 120) -> TxReceipt: ...

    def get_abi(self) -> list[dict]: ...


class Web3Backend:
    """Real Web3 backend for Anvil/mainnet interaction."""

    def __init__(self, rpc_url: str, *, timeout: float = 10.0):
        self._w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
        self._abi = load_abi()

    def is_connected(self) -> bool:
        return self._w3.is_connected()

    def get_chain_id(self) -> int:
        return self._w3.eth.chain_id

    def get_block_number(self) -> int:
        return self._w3.eth.block_number

    def get_transaction_receipt(self, tx_hash: str) -> TxReceipt | None:
        try:
            return self._w3.eth.get_transaction_receipt(tx_hash)
        except Exception:
            return None

    def get_transaction(self, tx_hash: str) -> dict[str, Any] | None:
        try:
            return dict(self._w3.eth.get_transaction(tx_hash))
        except Exception:
            return None

    def get_logs(self, filter_params: dict[str, Any]) -> list[dict[str, Any]]:
        return [dict(log) for log in self._w3.eth.get_logs(filter_params)]

    def get_block(self, block_identifier: int | str) -> dict[str, Any]:
        return dict(self._w3.eth.get_block(block_identifier))

    def get_gas_price(self) -> int:
        return self._w3.eth.gas_price

    def send_transaction(self, tx: dict[str, Any]) -> str:
        signed = self._w3.eth.account.sign_transaction(tx, private_key=tx.get("_private_key", ""))
        return self._w3.eth.send_raw_transaction(signed.raw_transaction)

    def estimate_gas(self, tx: dict[str, Any]) -> int:
        return self._w3.eth.estimate_gas(tx)

    def get_transaction_count(self, address: str, block_identifier: str = "pending") -> int:
        return self._w3.eth.get_transaction_count(address, block_identifier)

    def call_contract(self, to: str, data: bytes) -> bytes:
        result = self._w3.eth.call({"to": to, "data": data})
        return bytes(result)

    def get_balance(self, address: str) -> int:
        return self._w3.eth.get_balance(address)

    def wait_for_receipt(self, tx_hash: str, timeout: float = 120) -> TxReceipt:
        return self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)

    def get_w3(self) -> Web3:
        return self._w3

    def get_abi(self) -> list[dict]:
        return self._abi


class FakeBlockchainBackend:
    """Fake blockchain backend for unit tests. Stores state in-memory."""

    def __init__(self, chain_id: int = 421614):
        self._chain_id = chain_id
        self._block_number = 0
        self._transactions: dict[str, dict] = {}
        self._receipts: dict[str, TxReceipt] = {}
        self._nonces: dict[str, int] = {}
        self._balances: dict[str, int] = {}
        self._contracts: dict[str, dict] = {}  # address -> {storage, abi}
        self._tx_counter = 0

    def is_connected(self) -> bool:
        return True

    def get_chain_id(self) -> int:
        return self._chain_id

    def get_block_number(self) -> int:
        return self._block_number

    def get_transaction_receipt(self, tx_hash: str) -> TxReceipt | None:
        return self._receipts.get(tx_hash)

    def get_transaction(self, tx_hash: str) -> dict[str, Any] | None:
        return self._transactions.get(tx_hash)

    def get_logs(self, filter_params: dict[str, Any]) -> list[dict[str, Any]]:
        return [log for receipt in self._receipts.values() for log in receipt.get("logs", [])]

    def get_block(self, block_identifier: int | str) -> dict[str, Any]:
        return {"number": self._block_number, "hash": b"\xab" * 32, "timestamp": 0}

    def get_gas_price(self) -> int:
        return 1_000_000_000

    def send_transaction(self, tx: dict[str, Any]) -> str:
        self._tx_counter += 1
        tx_hash = f"0x{self._tx_counter:064x}"
        self._transactions[tx_hash] = tx
        self._block_number += 1

        # Create a receipt
        self._receipts[tx_hash] = {
            "transactionHash": bytes.fromhex(tx_hash[2:]),
            "transactionIndex": 0,
            "blockHash": bytes.fromhex("ab" * 32),
            "blockNumber": self._block_number,
            "from": bytes.fromhex(tx.get("from", "0" * 40)),
            "to": bytes.fromhex(tx.get("to", "0" * 40)) if tx.get("to") else b"",
            "gasUsed": 21000,
            "cumulativeGasUsed": 21000,
            "contractAddress": b"",
            "logs": [],
            "status": 1,
            "type": 0,
        }

        # Update nonce
        sender = tx.get("from", "").lower()
        if sender:
            self._nonces[sender] = self._nonces.get(sender, 0) + 1

        return tx_hash

    def estimate_gas(self, tx: dict[str, Any]) -> int:
        return 100000

    def get_transaction_count(self, address: str, block_identifier: str = "pending") -> int:
        return self._nonces.get(address.lower(), 0)

    def call_contract(self, to: str, data: bytes) -> bytes:
        contract = self._contracts.get(to.lower(), {})
        return contract.get("result", b"\x00" * 32)

    def get_balance(self, address: str) -> int:
        return self._balances.get(address.lower(), 0)

    def wait_for_receipt(self, tx_hash: str, timeout: float = 120) -> TxReceipt:
        receipt = self._receipts.get(tx_hash)
        if receipt is None:
            raise ValueError(f"Transaction {tx_hash} not found")
        return receipt

    def set_balance(self, address: str, balance: int) -> None:
        self._balances[address.lower()] = balance

    def set_contract_result(self, address: str, result: bytes) -> None:
        self._contracts[address.lower()] = {"result": result}

    def mine_block(self) -> None:
        self._block_number += 1

    def get_abi(self) -> list[dict]:
        return []


# ────────────────────────────────────────────────────
# High-level transaction helpers
# ────────────────────────────────────────────────────


def build_assign_provider_tx(
    *,
    contract_address: str,
    chain_id: int,
    nonce: int,
    gas_price: int,
    gas_limit: int,
    job_id: bytes,
    provider: str,
    lease_id: bytes,
    lease_expires_at: int,
) -> dict[str, Any]:
    """Build a raw transaction dict for assignProvider()."""
    encoded = SELECTOR_ASSIGN_PROVIDER + encode(
        ["bytes32", "address", "bytes32", "uint64"],
        [job_id, provider, lease_id, lease_expires_at],
    )
    return {
        "to": contract_address,
        "data": encoded,
        "chainId": chain_id,
        "nonce": nonce,
        "gasPrice": gas_price,
        "gas": gas_limit,
    }


def build_submit_proof_tx(
    *,
    contract_address: str,
    chain_id: int,
    nonce: int,
    gas_price: int,
    gas_limit: int,
    job_id: bytes,
    lease_id: bytes,
    merkle_root: bytes,
    output_hash: bytes,
) -> dict[str, Any]:
    """Build a raw transaction dict for submitProof()."""
    encoded = SELECTOR_SUBMIT_PROOF + encode(
        ["bytes32", "bytes32", "bytes32", "bytes32"],
        [job_id, lease_id, merkle_root, output_hash],
    )
    return {
        "to": contract_address,
        "data": encoded,
        "chainId": chain_id,
        "nonce": nonce,
        "gasPrice": gas_price,
        "gas": gas_limit,
    }


def build_verify_job_tx(
    *,
    contract_address: str,
    chain_id: int,
    nonce: int,
    gas_price: int,
    gas_limit: int,
    job_id: bytes,
    is_valid: bool,
) -> dict[str, Any]:
    """Build a raw transaction dict for verifyJob()."""
    encoded = SELECTOR_VERIFY_JOB + encode(
        ["bytes32", "bool"],
        [job_id, is_valid],
    )
    return {
        "to": contract_address,
        "data": encoded,
        "chainId": chain_id,
        "nonce": nonce,
        "gasPrice": gas_price,
        "gas": gas_limit,
    }


def decode_receipt_logs(receipt: TxReceipt, abi: list[dict]) -> list[dict[str, Any]]:
    """Decode event logs from a transaction receipt."""
    decoded: list[dict[str, Any]] = []
    codec = Web3().codec
    for log in receipt.get("logs", []):
        for event in [item for item in abi if item.get("type") == "event"]:
            event_signature = Web3.keccak(text=f"{event['name']}({','.join(i['type'] for i in event['inputs'])})").hex()
            topic = log.get("topics", [b""])[0]
            if isinstance(topic, bytes):
                topic = topic.hex()
            if topic.lower() == event_signature.lower():
                event_data = get_event_data(codec, event, log)
                decoded.append(
                    {
                        "event": event_data["event"],
                        "args": dict(event_data["args"]),
                        "logIndex": event_data["logIndex"],
                        "transactionHash": event_data["transactionHash"],
                        "blockNumber": event_data["blockNumber"],
                        "blockHash": event_data["blockHash"],
                        "address": event_data["address"],
                    }
                )
                break
    return decoded
