"""Transaction signer service with dependency injection.

Production: reads BACKEND_PRIVATE_KEY from config, signs via Web3.
Anvil tests: deterministic key from Foundry test mnemonic.
Unit tests: FakeSigner records calls without RPC.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from web3 import Web3

from app.config import settings


class TransactionSigner(Protocol):
    """Protocol for signing and sending blockchain transactions."""

    def get_address(self) -> str: ...
    def get_chain_id(self) -> int: ...
    def get_nonce(self, address: str | None = None) -> int: ...
    def prepare_transaction(self, tx: dict[str, Any]) -> tuple[str, str]: ...
    def broadcast_raw_transaction(self, raw_transaction: str) -> str: ...
    def sign_and_send(self, tx: dict[str, Any]) -> str: ...
    def wait_for_receipt(self, tx_hash: str, timeout: float = 120) -> dict[str, Any]: ...


class Web3Signer:
    """Production signer using Web3 + configured private key."""

    def __init__(self, rpc_url: str, private_key: str | None = None):
        self._w3 = Web3(Web3.HTTPProvider(rpc_url))
        pk = private_key or settings.BACKEND_PRIVATE_KEY
        if not pk:
            raise ValueError("BACKEND_PRIVATE_KEY is required for Web3Signer")
        self._account = self._w3.eth.account.from_key(pk)
        self._address = self._account.address

    def get_address(self) -> str:
        return self._address

    def get_chain_id(self) -> int:
        return self._w3.eth.chain_id

    def get_nonce(self, address: str | None = None) -> int:
        return self._w3.eth.get_transaction_count(address or self._address)

    def sign_and_send(self, tx: dict[str, Any]) -> str:
        if "nonce" not in tx:
            tx["nonce"] = self.get_nonce()
        if "chainId" not in tx:
            tx["chainId"] = self.get_chain_id()
        if "gas" not in tx:
            tx["gas"] = self._w3.eth.estimate_gas(tx)
        if "gasPrice" not in tx:
            tx["gasPrice"] = self._w3.eth.gas_price
        _, raw_transaction = self.prepare_transaction(tx)
        return self.broadcast_raw_transaction(raw_transaction)

    def prepare_transaction(self, tx: dict[str, Any]) -> tuple[str, str]:
        """Sign locally and return the deterministic hash/raw bytes without broadcasting."""
        signed = self._w3.eth.account.sign_transaction(tx, private_key=self._account.key)
        return "0x" + signed.hash.hex(), "0x" + signed.raw_transaction.hex()

    def broadcast_raw_transaction(self, raw_transaction: str) -> str:
        tx_hash = self._w3.eth.send_raw_transaction(bytes.fromhex(raw_transaction.removeprefix("0x")))
        return tx_hash.hex() if isinstance(tx_hash, bytes) else tx_hash

    def wait_for_receipt(self, tx_hash: str, timeout: float = 120) -> dict[str, Any]:
        return self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)


class FakeSigner:
    """Deterministic fake signer for unit tests. Tracks all calls."""

    def __init__(self, address: str = "0x" + "ab" * 20, chain_id: int = 421614):
        self._address = address
        self._chain_id = chain_id
        self._nonce = 0
        self.sent_txs: list[dict[str, Any]] = []
        self._tx_hashes: list[str] = []
        self._prepared: dict[str, str] = {}

    def get_address(self) -> str:
        return self._address

    def get_chain_id(self) -> int:
        return self._chain_id

    def get_nonce(self, address: str | None = None) -> int:
        n = self._nonce
        self._nonce += 1
        return n

    def sign_and_send(self, tx: dict[str, Any]) -> str:
        _, raw_transaction = self.prepare_transaction(tx)
        return self.broadcast_raw_transaction(raw_transaction)

    def prepare_transaction(self, tx: dict[str, Any]) -> tuple[str, str]:
        self.sent_txs.append(tx)
        serializable = {
            key: "0x" + value.hex() if isinstance(value, bytes) else value for key, value in sorted(tx.items())
        }
        raw_transaction = "0x" + json.dumps(serializable, sort_keys=True, separators=(",", ":")).encode().hex()
        tx_hash = "0x" + hashlib.sha256(bytes.fromhex(raw_transaction[2:])).hexdigest()
        self._prepared[raw_transaction] = tx_hash
        return tx_hash, raw_transaction

    def broadcast_raw_transaction(self, raw_transaction: str) -> str:
        tx_hash = self._prepared.get(raw_transaction)
        if tx_hash is None:
            tx_hash = "0x" + hashlib.sha256(bytes.fromhex(raw_transaction.removeprefix("0x"))).hexdigest()
        self._tx_hashes.append(tx_hash)
        return tx_hash

    def wait_for_receipt(self, tx_hash: str, timeout: float = 120) -> dict[str, Any]:
        return {
            "transactionHash": bytes.fromhex(tx_hash.removeprefix("0x")),
            "status": 1,
            "blockNumber": 1,
            "blockHash": b"\xab" * 32,
            "from": bytes.fromhex(self._address.removeprefix("0x")),
            "to": b"",
            "logs": [],
            "gasUsed": 21000,
            "cumulativeGasUsed": 21000,
            "contractAddress": b"",
            "transactionIndex": 0,
            "type": 0,
        }
