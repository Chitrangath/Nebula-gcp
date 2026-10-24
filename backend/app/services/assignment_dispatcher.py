"""Assignment dispatcher: transitions pending_chain leases to active after on-chain confirmation.

PRD v3.1 §13: The scheduler creates pending_chain leases in a committed DB transaction.
The dispatcher runs AFTER the scheduler commits, builds and broadcasts assignProvider(),
waits for the ProviderAssigned event, and activates the lease only after confirmation.

Architecture:
  1. Scheduler creates pending_chain lease + attempt + updates job status (DB commit)
  2. Dispatcher claims a pending assignment intent transactionally
  3. Dispatcher builds assignProvider() calldata
  4. Dispatcher signs via TransactionSigner
  5. Dispatcher broadcasts via BlockchainBackend
  6. Dispatcher persists tx_hash and nonce to ChainTransaction
  7. Dispatcher waits for receipt and ProviderAssigned event
  8. Dispatcher activates lease and transitions job to assigned
  9. Dispatcher handles submitted/confirmed/reverted/dropped/replaced states
"""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChainTransaction, Job, Lease, Node
from app.services.blockchain_service import (
    BlockchainBackend,
    build_assign_provider_tx,
    decode_receipt_logs,
)
from app.services.chain_outbox import get_chain_instance_id, prepare_and_broadcast, rebroadcast_prepared
from app.services.job_service import update_job_status
from app.services.lease_service import activate_lease
from app.services.retry_policy import apply_attempt_failure
from app.services.tx_signer import TransactionSigner

logger = logging.getLogger(__name__)


class AssignmentStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    REVERTED = "reverted"
    DROPPED = "dropped"
    REPLACED = "replaced"


class AssignmentDispatcher:
    """Dispatches assignProvider() transactions after scheduler commits.

    The scheduler creates pending_chain leases in its own DB transaction.
    The dispatcher runs in a separate process/context, claims a pending
    assignment intent, and processes it through the blockchain lifecycle.
    """

    def __init__(
        self,
        *,
        blockchain: BlockchainBackend,
        signer: TransactionSigner,
        contract_address: str,
        chain_id: int,
        rpc_url: str,
        receipt_timeout: float = 10.0,
    ):
        self._blockchain = blockchain
        self._signer = signer
        self._contract_address = contract_address
        self._chain_id = chain_id
        self._rpc_url = rpc_url
        self._receipt_timeout = receipt_timeout

    async def dispatch_pending_assignments(self, db: AsyncSession) -> list[str]:
        """Find and dispatch all pending_chain leases that need on-chain assignment.

        Returns list of dispatched lease IDs.
        """
        await db.commit()
        chain_instance_id = get_chain_instance_id(self._blockchain)
        prepared = await db.execute(
            select(ChainTransaction.id).where(
                ChainTransaction.tx_type == "assignProvider",
                ChainTransaction.status.in_(["submitted", "dropped"]),
                ChainTransaction.transaction_payload.is_not(None),
                ChainTransaction.chain_id == self._chain_id,
                ChainTransaction.chain_instance_id == chain_instance_id,
                ChainTransaction.contract_address == self._contract_address,
            )
        )
        prepared_ids = list(prepared.scalars().all())
        await db.commit()
        for intent_id in prepared_ids:
            await rebroadcast_prepared(
                db,
                intent_id=intent_id,
                blockchain=self._blockchain,
                signer=self._signer,
            )

        pending_intents = await db.execute(
            select(ChainTransaction.id).where(
                ChainTransaction.tx_type == "assignProvider",
                ChainTransaction.status == "pending",
                ChainTransaction.tx_hash.is_(None),
                ChainTransaction.chain_id == self._chain_id,
                ChainTransaction.contract_address == self._contract_address,
                or_(
                    ChainTransaction.chain_instance_id.is_(None),
                    ChainTransaction.chain_instance_id == chain_instance_id,
                ),
            )
        )
        intent_ids = list(pending_intents.scalars().all())
        await db.commit()
        dispatched = []

        for intent_id in intent_ids:
            intent = (
                await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id))
            ).scalar_one_or_none()
            if intent is None:
                await db.commit()
                continue
            lease_result = await db.execute(select(Lease).where(Lease.id == intent.lease_id))
            lease = lease_result.scalar_one_or_none()
            if lease is None or lease.status != "pending_chain":
                await db.commit()
                continue
            lease_id = await self._dispatch_single_assignment(db, lease, intent)
            if lease_id:
                dispatched.append(str(lease_id))

        return dispatched

    async def _dispatch_single_assignment(
        self,
        db: AsyncSession,
        lease: Lease,
        chain_tx: ChainTransaction,
    ) -> uuid.UUID | None:
        """Claim and dispatch a single pending assignment.

        Operates in a separate DB session from the scheduler to avoid
        holding row locks during RPC calls.
        """
        # Load the associated job
        job_result = await db.execute(select(Job).where(Job.id == lease.job_id))
        job = job_result.scalar_one_or_none()
        if not job:
            logger.warning("Lease %s references missing job %s", lease.id, lease.job_id)
            return None

        # Load the node to get provider address
        node_result = await db.execute(select(Node).where(Node.id == lease.node_id))
        node = node_result.scalar_one_or_none()
        if not node:
            logger.warning("Lease %s references missing node %s", lease.id, lease.node_id)
            return None

        # Get the provider's wallet address
        from app.models import User

        provider_result = await db.execute(select(User).where(User.id == node.provider_id))
        provider = provider_result.scalar_one_or_none()
        if not provider:
            logger.warning("Node %s references missing provider %s", node.id, node.provider_id)
            return None

        # Build the assignProvider() calldata
        job_id_bytes = bytes.fromhex(job.chain_job_id.removeprefix("0x"))
        lease_id_bytes = bytes.fromhex(lease.lease_id.removeprefix("0x"))
        provider_address = provider.wallet_address
        lease_expires_at = int(lease.expires_at.timestamp())

        intent_id = chain_tx.id

        def build(nonce: int, gas_price: int) -> dict[str, Any]:
            return build_assign_provider_tx(
                contract_address=self._contract_address,
                chain_id=self._chain_id,
                nonce=nonce,
                gas_price=gas_price,
                gas_limit=300_000,
                job_id=job_id_bytes,
                provider=provider_address,
                lease_id=lease_id_bytes,
                lease_expires_at=lease_expires_at,
            )

        broadcast = await prepare_and_broadcast(
            db,
            intent_id=intent_id,
            blockchain=self._blockchain,
            signer=self._signer,
            chain_id=self._chain_id,
            build_transaction=build,
        )
        persisted = (await db.execute(select(ChainTransaction).where(ChainTransaction.id == intent_id))).scalar_one()
        persisted_lease = (await db.execute(select(Lease).where(Lease.id == lease.id))).scalar_one()
        persisted_lease.nonce = persisted.nonce
        persisted_lease.tx_hash = persisted.tx_hash
        await db.commit()
        logger.info(
            "Dispatched assignProvider for lease %s, tx_hash=%s, nonce=%d",
            lease.id,
            persisted.tx_hash,
            persisted.nonce,
        )

        return lease.id if broadcast else None

    async def confirm_assignment(
        self,
        db: AsyncSession,
        *,
        lease_id: uuid.UUID,
        tx_hash: str,
        block_number: int,
        block_hash: str,
    ) -> bool:
        """Process a confirmed assignProvider transaction.

        Validates the ProviderAssigned event, activates the lease,
        and transitions the job to assigned.

        Returns True if activation succeeded.
        """
        # Resolve the concrete chain before reading an intent. Fresh local
        # chains can legitimately reuse transaction hashes and addresses.
        await db.commit()
        chain_instance_id = get_chain_instance_id(self._blockchain)

        # Load the ChainTransaction
        tx_result = await db.execute(
            select(ChainTransaction).where(
                ChainTransaction.tx_hash == tx_hash,
                ChainTransaction.lease_id == lease_id,
                ChainTransaction.chain_id == self._chain_id,
                ChainTransaction.chain_instance_id == chain_instance_id,
                ChainTransaction.contract_address == self._contract_address,
            )
        )
        chain_tx = tx_result.scalar_one_or_none()
        if not chain_tx:
            logger.warning("ChainTransaction not found for tx_hash=%s", tx_hash)
            return False

        if chain_tx.status == "confirmed":
            logger.info("Transaction %s already confirmed, skipping", tx_hash)
            await db.commit()
            return True

        # Get receipt from blockchain
        await db.commit()
        try:
            receipt = self._blockchain.wait_for_receipt(tx_hash, timeout=self._receipt_timeout)
        except Exception as e:
            logger.error("Failed to get receipt for %s: %s", tx_hash, e)
            chain_tx = (
                await db.execute(
                    select(ChainTransaction).where(
                        ChainTransaction.tx_hash == tx_hash,
                        ChainTransaction.lease_id == lease_id,
                        ChainTransaction.chain_instance_id == chain_instance_id,
                    )
                )
            ).scalar_one()
            # A receipt timeout is not proof that a prepared transaction was
            # dropped. Keep it submitted so the durable outbox can rebroadcast
            # the exact payload or fee-bump the same nonce on the next cycle.
            chain_tx.status = "submitted"
            chain_tx.error = type(e).__name__
            await db.flush()
            return False

        chain_tx = (
            await db.execute(
                select(ChainTransaction)
                .where(
                    ChainTransaction.tx_hash == tx_hash,
                    ChainTransaction.lease_id == lease_id,
                    ChainTransaction.chain_instance_id == chain_instance_id,
                )
                .with_for_update()
            )
        ).scalar_one()
        if chain_tx.status in ("confirmed", "finalized"):
            return True

        if receipt.get("status") != 1:
            logger.warning("Transaction %s reverted on-chain", tx_hash)
            chain_tx.status = "reverted"
            chain_tx.error = "assignProvider transaction reverted"
            lease_obj = (await db.execute(select(Lease).where(Lease.id == lease_id))).scalar_one_or_none()
            if lease_obj is not None and lease_obj.status == "pending_chain":
                await apply_attempt_failure(db, lease_obj, reason="assignProvider transaction reverted")
            await db.flush()
            return False

        # Validate ProviderAssigned event exists in receipt
        decoded_events = decode_receipt_logs(receipt, self._blockchain.get_abi())
        lease_result = await db.execute(select(Lease).where(Lease.id == lease_id))
        lease_obj = lease_result.scalar_one_or_none()
        if not lease_obj:
            logger.error("Lease %s not found during confirmation", lease_id)
            return False
        job_result = await db.execute(select(Job).where(Job.id == chain_tx.job_id))
        job = job_result.scalar_one_or_none()
        node_result = await db.execute(select(Node).where(Node.id == lease_obj.node_id))
        node = node_result.scalar_one_or_none()
        from app.models import User

        provider = None
        if node:
            provider_result = await db.execute(select(User).where(User.id == node.provider_id))
            provider = provider_result.scalar_one_or_none()
        provider_assigned = [
            e
            for e in decoded_events
            if e.get("event") == "ProviderAssigned"
            and job is not None
            and provider is not None
            and bytes(e.get("args", {}).get("jobId", b"")) == bytes.fromhex(job.chain_job_id.removeprefix("0x"))
            and str(e.get("args", {}).get("provider", "")).lower() == provider.wallet_address.lower()
            and bytes(e.get("args", {}).get("leaseId", b"")) == bytes.fromhex(lease_obj.lease_id.removeprefix("0x"))
            and int(e.get("args", {}).get("leaseExpiresAt", 0)) == int(lease_obj.expires_at.timestamp())
        ]
        if not provider_assigned:
            logger.warning("No ProviderAssigned event in receipt for %s", tx_hash)
            return False

        chain_tx.status = "confirmed"
        chain_tx.block_number = int(receipt.get("blockNumber", block_number))
        receipt_hash = receipt.get("blockHash", block_hash)
        chain_tx.block_hash = "0x" + receipt_hash.hex() if isinstance(receipt_hash, bytes) else str(receipt_hash)

        if lease_obj.status == "pending_chain":
            await activate_lease(db, lease_id)

        # Transition job to assigned
        if job and job.status in ("queued", "retry_pending"):
            await update_job_status(db, job.id, "assigned")

        await db.flush()
        return True

    async def reconcile_existing_tx(
        self,
        db: AsyncSession,
        *,
        tx_hash: str,
    ) -> dict[str, Any]:
        """Reconcile an already-mined transaction without resubmission.

        If the transaction was submitted but not yet confirmed, this
        fetches the receipt and processes it.
        """
        await db.commit()
        chain_instance_id = get_chain_instance_id(self._blockchain)
        tx_result = await db.execute(
            select(ChainTransaction).where(
                ChainTransaction.tx_hash == tx_hash,
                ChainTransaction.chain_id == self._chain_id,
                ChainTransaction.contract_address == self._contract_address,
                ChainTransaction.chain_instance_id == chain_instance_id,
            )
        )
        chain_tx = tx_result.scalar_one_or_none()
        if not chain_tx:
            return {"status": "tx_not_found"}

        if chain_tx.status in ("confirmed", "finalized"):
            return {"status": "already_processed", "tx_status": chain_tx.status}

        try:
            await db.commit()
            receipt = self._blockchain.wait_for_receipt(tx_hash, timeout=10)
        except Exception as e:
            return {"status": "receipt_unavailable", "error": str(e)}

        chain_tx = (
            await db.execute(
                select(ChainTransaction)
                .where(
                    ChainTransaction.tx_hash == tx_hash,
                    ChainTransaction.chain_instance_id == chain_instance_id,
                )
                .with_for_update()
            )
        ).scalar_one()

        if receipt.get("status") != 1:
            chain_tx.status = "reverted"
            chain_tx.error = "assignProvider transaction reverted"
            lease_obj = (
                await db.execute(select(Lease).where(Lease.id == chain_tx.lease_id))
            ).scalar_one_or_none()
            if lease_obj is not None and lease_obj.status == "pending_chain":
                await apply_attempt_failure(db, lease_obj, reason="assignProvider transaction reverted")
            await db.flush()
            return {"status": "reverted"}

        chain_tx.status = "confirmed"
        chain_tx.block_number = receipt.get("blockNumber", 0)
        block_hash_raw = receipt.get("blockHash", b"")
        if isinstance(block_hash_raw, bytes):
            chain_tx.block_hash = "0x" + block_hash_raw.hex()
        else:
            chain_tx.block_hash = str(block_hash_raw)
        await db.flush()

        return {"status": "confirmed", "block_number": chain_tx.block_number}

    async def handle_dropped_tx(
        self,
        db: AsyncSession,
        *,
        lease_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Handle a dropped or replaced transaction by resetting lease state.

        The lease returns to pending_chain for re-dispatch.
        """
        lease_result = await db.execute(select(Lease).where(Lease.id == lease_id))
        lease = lease_result.scalar_one_or_none()
        if not lease:
            return {"status": "lease_not_found"}

        if lease.status == "active":
            return {"status": "already_active"}

        # Mark the old transaction as dropped
        if lease.tx_hash:
            tx_result = await db.execute(select(ChainTransaction).where(ChainTransaction.tx_hash == lease.tx_hash))
            chain_tx = tx_result.scalar_one_or_none()
            if chain_tx:
                chain_tx.status = "dropped"

        # Reset lease for re-dispatch
        lease.tx_hash = None
        lease.nonce = None
        await db.flush()

        return {"status": "reset_for_redispatch"}
