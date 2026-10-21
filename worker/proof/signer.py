"""ECDSA signing for PoAE proofs."""

from eth_account import Account
from eth_account.messages import encode_defunct


def sign_proof(message: str, private_key: str) -> bytes:
    """Sign message with worker's private key."""
    msg = encode_defunct(text=message)
    signed = Account.sign_message(msg, private_key)
    return signed.signature
