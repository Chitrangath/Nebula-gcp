"""Durable prepare-before-broadcast transaction outbox and nonce allocator."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChainTransaction, SignerNonce
from app.services.blockchain_service import BlockchainBackend
from app.services.tx_signer import TransactionSigner


def _json_transaction(tx: dict[str, Any]) -> dict[str, Any]:
    return {key: "0x" + value.hex() if isinstance(value, bytes) else value for key, value in tx.items()}


def _raw_transaction(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    if isinstance(result.get("data"), str):
        result["data"] = bytes.fromhex(result["data"].removeprefix("0x"))
    return result


def get_chain_instance_id(blockchain: BlockchainBackend) -> str:
    """Return the genesis block hash that identifies this concrete chain history."""
    genesis_hash = blockchain.get_block(0)["hash"]
    return ("0x" + genesis_hash.hex() if isinstance(genesis_hash, bytes) else str(genesis_hash)).lower()


async def _reserve_nonce(
    db: AsyncSession,
    *,
    chain_id: int,
    chain_instance_id: str,
    signer_address: str,
    chain_pending_nonce: int,
) -> int:
    """Reserve one nonce under a short DB row lock; performs no network I/O."""
    values = {
        "id": uuid.uuid4(),
        "chain_id": chain_id,
        "chain_instance_id": chain_instance_id,
        "signer_address": signer_address.lower(),
        "next_nonce": chain_pending_nonce,
    }
    dialect = db.bind.dialect.name if db.bind else "sqlite"
    statement = pg_insert(SignerNonce) if dialect == "postgresql" else sqlite_insert(SignerNonce)
    await db.execute(
        statement.values(**values).on_conflict_do_nothing(
            index_elements=["chain_id", "chain_instance_id", "signer_address"]
        )
    )
    row = await db.execute(
        select(SignerNonce)
        .where(
            SignerNonce.chain_id == chain_id,
            SignerNonce.chain_instance_id == chain_instance_id,
            SignerNonce.signer_address == signer_address.lower(),
        )
        .with_for_update()
    )
    state = row.scalar_one()
    nonce = max(int(state.next_nonce), chain_pending_nonce)
    state.next_nonce = nonce + 1
    return nonce


async def prepare_and_broadcast(
    db: AsyncSession,
    *,
    intent_id: uuid.UUID,
    blockchain: BlockchainBackend,
    signer: TransactionSigner,
    chain_id: int,
    build_transaction: Callable[[int, int], dict[str, Any]],
) -> bool:
    """Persist signed identity/payload before broadcasting it to the chain."""
    # These are RPC calls. End any implicit read transaction before making them.
    await db.commit()
    chain_nonce = blockchain.get_transaction_count(signer.get_address(), "pending")
    gas_price = blockchain.get_gas_price()
    chain_instance_id = get_chain_instance_id(blockchain)

    row = await db.execute(
        select(ChainTransaction)
        .where(ChainTransaction.id == intent_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    intent = row.scalar_one_or_none()
    if intent is None or intent.status != "pending":
        await db.commit()
        return False
    nonce = await _reserve_nonce(
        db,
        chain_id=chain_id,
        chain_instance_id=chain_instance_id,
        signer_address=signer.get_address(),
        chain_pending_nonce=chain_nonce,
    )
    tx = build_transaction(nonce, gas_price)
    tx_hash, raw_signed = signer.prepare_transaction(tx)
    intent.nonce = nonce
    intent.chain_instance_id = chain_instance_id
    intent.transaction_payload = _json_transaction(tx)
    intent.tx_hash = tx_hash.lower()
    intent.status = "submitted"
    intent.error = None
    await db.commit()

    try:
        observed_hash = signer.broadcast_raw_transaction(raw_signed)
        if observed_hash.lower() != tx_hash.lower():
            raise RuntimeError("broadcast hash differs from prepared transaction hash")
    except Exception as exc:
        # A transport error after send is success if the chain already knows the hash.
        known = (
            blockchain.get_transaction(tx_hash) is not None or blockchain.get_transaction_receipt(tx_hash) is not None
        )
        if not known:
            current = (await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id))).scalar_one()
            current.error = type(exc).__name__
            await db.commit()
            return False
    return True


async def rebroadcast_prepared(
    db: AsyncSession,
    *,
    intent_id: uuid.UUID,
    blockchain: BlockchainBackend,
    signer: TransactionSigner,
) -> bool:
    """Rebroadcast the exact prepared transaction only when the chain has never seen it."""
    row = await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id))
    intent = row.scalar_one_or_none()
    if (
        intent is None
        or intent.status not in ("submitted", "dropped")
        or not intent.tx_hash
        or not intent.transaction_payload
    ):
        await db.commit()
        return False
    if intent.status == "dropped":
        intent.status = "submitted"
        intent.error = None
        await db.commit()
    expected_hash = intent.tx_hash.lower()
    payload = dict(intent.transaction_payload)
    await db.commit()
    if (
        blockchain.get_transaction_receipt(expected_hash) is not None
        or blockchain.get_transaction(expected_hash) is not None
    ):
        return False
    if intent.nonce is not None and blockchain.get_transaction_count(intent.from_address, "pending") > intent.nonce:
        current = (
            await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id).with_for_update())
        ).scalar_one()
        if current.status == "submitted":
            current.status = "replaced"
            current.error = "signer nonce already consumed by another transaction"
        await db.commit()
        return False
    prepared_hash, raw_signed = signer.prepare_transaction(_raw_transaction(payload))
    if prepared_hash.lower() != expected_hash:
        raise RuntimeError("persisted transaction payload does not reproduce its hash")
    try:
        signer.broadcast_raw_transaction(raw_signed)
    except Exception as exc:
        # A legacy transaction can disappear from a public mempool when its
        # gas price falls below the provider's current acceptance floor. Keep
        # the same nonce and calldata, but durably prepare a fee-bumped
        # replacement before attempting the second broadcast.
        old_gas_price = payload.get("gasPrice")
        if old_gas_price is None:
            current = (await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id))).scalar_one()
            current.error = type(exc).__name__
            await db.commit()
            return False
        replacement = dict(payload)
        network_gas_price = blockchain.get_gas_price()
        replacement["gasPrice"] = max(int(old_gas_price) * 110 // 100 + 1, network_gas_price * 120 // 100)
        replacement_hash, replacement_raw = signer.prepare_transaction(_raw_transaction(replacement))
        current = (
            await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id).with_for_update())
        ).scalar_one()
        if current.status != "submitted" or current.tx_hash.lower() != expected_hash:
            await db.commit()
            return False
        current.tx_hash = replacement_hash.lower()
        current.transaction_payload = replacement
        current.error = None
        await db.commit()
        try:
            observed_hash = signer.broadcast_raw_transaction(replacement_raw)
            if observed_hash.lower() != replacement_hash.lower():
                raise RuntimeError("replacement broadcast hash differs from prepared transaction hash")
        except Exception as replacement_exc:
            current = (await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id))).scalar_one()
            current.error = type(replacement_exc).__name__
            await db.commit()
            return False
    return True
