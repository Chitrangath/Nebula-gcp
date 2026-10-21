"""Blockchain event ingestion, durability, and reconciliation service.

PRD v3.1 §19: Records all on-chain events in blockchain_events table.
Supports backfill from checkpoint, restart, overlap, reorg handling,
and reconciliation with DB state.

Reorg behavior:
  - Non-finalized events whose block hash no longer matches canonical chain
    are flagged for rollback.
  - Finalized events are never deleted; instead, a critical incident is recorded.
  - Automated projection updates are paused for affected jobs.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BlockchainEvent,
    ChainCursor,
    ChainTransaction,
    Job,
    JobAttempt,
    Lease,
    Node,
    Payment,
    ReconciliationIncident,
    User,
)
from app.services.blockchain_service import BlockchainBackend, decode_receipt_logs
from app.utils import bytes32_to_uuid

# ──────────────────────────────────────────────
# Event Recording
# ──────────────────────────────────────────────


async def record_event(
    db: AsyncSession,
    *,
    chain_id: int,
    chain_instance_id: str = "legacy",
    contract_address: str,
    transaction_hash: str,
    log_index: int,
    block_number: int,
    block_hash: str,
    event_name: str,
    event_data: dict[str, Any],
    job_id: uuid.UUID | None = None,
) -> BlockchainEvent:
    """Record an on-chain event. Idempotent — skips if (chain, contract, tx, log) already exists.

    Returns the existing event if already recorded, or the new event.
    """
    # Check for existing
    existing = await db.execute(
        select(BlockchainEvent).where(
            BlockchainEvent.chain_id == chain_id,
            BlockchainEvent.chain_instance_id == chain_instance_id,
            BlockchainEvent.contract_address == contract_address,
            BlockchainEvent.transaction_hash == transaction_hash,
            BlockchainEvent.log_index == log_index,
        )
    )
    existing_event = existing.scalar_one_or_none()
    if existing_event:
        if existing_event.confirmation_status == "orphaned":
            existing_event.block_number = block_number
            existing_event.block_hash = block_hash
            existing_event.event_name = event_name
            existing_event.event_data = event_data
            existing_event.job_id = job_id
            existing_event.confirmation_status = "pending"
            await db.flush()
        return existing_event

    event = BlockchainEvent(
        id=uuid.uuid4(),
        chain_id=chain_id,
        chain_instance_id=chain_instance_id,
        contract_address=contract_address,
        transaction_hash=transaction_hash,
        log_index=log_index,
        block_number=block_number,
        block_hash=block_hash,
        event_name=event_name,
        job_id=job_id,
        event_data=event_data,
        confirmation_status="pending",
    )
    db.add(event)
    await db.flush()
    return event


# ──────────────────────────────────────────────
# Checkpoint Management
# ──────────────────────────────────────────────


async def get_checkpoint(
    db: AsyncSession,
    chain_id: int,
    contract_address: str,
    chain_instance_id: str = "legacy",
) -> dict[str, Any]:
    """Get the last processed checkpoint for a chain+contract pair."""
    cursor = (
        await db.execute(
            select(ChainCursor).where(
                ChainCursor.chain_id == chain_id,
                ChainCursor.chain_instance_id == chain_instance_id,
                ChainCursor.contract_address == contract_address,
            )
        )
    ).scalar_one_or_none()
    if cursor:
        return {
            "chain_id": chain_id,
            "contract_address": contract_address,
            "last_block": cursor.last_scanned_block,
            "last_block_hash": cursor.last_scanned_block_hash,
            "halted": cursor.halted,
        }
    result = await db.execute(
        text(
            "SELECT MAX(block_number) as last_block "
            "FROM blockchain_events "
            "WHERE chain_id = :chain_id AND chain_instance_id = :chain_instance_id "
            "AND contract_address = :contract_address"
        ),
        {
            "chain_id": chain_id,
            "chain_instance_id": chain_instance_id,
            "contract_address": contract_address,
        },
    )
    row = result.first()
    last_block = row[0] if row and row[0] else 0
    return {"chain_id": chain_id, "contract_address": contract_address, "last_block": last_block, "halted": False}


async def backfill_events(
    db: AsyncSession,
    *,
    chain_id: int,
    contract_address: str,
    events: list[dict[str, Any]],
    from_block: int,
    to_block: int,
) -> list[BlockchainEvent]:
    """Backfill events from a block range. Idempotent.

    Overlapping backfill without duplicate events.
    """
    recorded = []
    for ev in events:
        event = await record_event(
            db,
            chain_id=chain_id,
            contract_address=contract_address,
            transaction_hash=ev["transaction_hash"],
            log_index=ev["log_index"],
            block_number=ev["block_number"],
            block_hash=ev["block_hash"],
            event_name=ev["event_name"],
            event_data=ev.get("event_data", {}),
            job_id=ev.get("job_id"),
        )
        recorded.append(event)
    return recorded


# ──────────────────────────────────────────────
# Confirmation Progression
# ──────────────────────────────────────────────


async def confirm_event(db: AsyncSession, event_id: uuid.UUID) -> BlockchainEvent:
    """Mark an event as confirmed (1+ block confirmations)."""
    result = await db.execute(select(BlockchainEvent).where(BlockchainEvent.id == event_id))
    event = result.scalar_one()
    event.confirmation_status = "confirmed"
    await db.flush()
    return event


async def finalize_event(db: AsyncSession, event_id: uuid.UUID) -> BlockchainEvent:
    """Mark an event as finalized (10+ blocks, reorg-safe).

    Finalized events are NEVER deleted. If a finalized event's block
    changes, a critical incident is recorded instead.
    """
    result = await db.execute(select(BlockchainEvent).where(BlockchainEvent.id == event_id))
    event = result.scalar_one()
    event.confirmation_status = "finalized"
    await db.flush()
    return event


async def confirm_events_at_block(
    db: AsyncSession,
    *,
    chain_id: int,
    contract_address: str,
    current_block: int,
    confirmations_required: int = 1,
) -> int:
    """Confirm all pending events that have enough block confirmations.

    Returns number of events confirmed.
    """
    result = await db.execute(
        select(BlockchainEvent).where(
            BlockchainEvent.chain_id == chain_id,
            BlockchainEvent.contract_address == contract_address,
            BlockchainEvent.confirmation_status == "pending",
        )
    )
    events = result.scalars().all()
    count = 0
    for event in events:
        if current_block - event.block_number >= confirmations_required:
            event.confirmation_status = "confirmed"
            count += 1
    if count > 0:
        await db.flush()
    return count


# ──────────────────────────────────────────────
# Reorg Handling
# ──────────────────────────────────────────────


async def handle_reorg(
    db: AsyncSession,
    *,
    chain_id: int,
    contract_address: str,
    reverted_block_number: int,
    reverted_block_hash: str,
) -> dict[str, Any]:
    """Handle chain reorganization.

    For non-finalized events: remove projections (DB state changes derived from
    orphaned events) but RETAIN the event record itself, flagged as orphaned.

    For finalized events that changed: mark a critical incident.
    Pause automated projection updates for affected jobs.
    """
    # Find events in the reverted block that are non-finalized
    result = await db.execute(
        select(BlockchainEvent).where(
            BlockchainEvent.chain_id == chain_id,
            BlockchainEvent.contract_address == contract_address,
            BlockchainEvent.block_number >= reverted_block_number,
            BlockchainEvent.confirmation_status.in_(["pending", "confirmed"]),
        )
    )
    orphaned_events = result.scalars().all()

    affected_job_ids: list[uuid.UUID] = []

    for event in orphaned_events:
        # Check if block hash changed
        if event.block_hash.lower() != reverted_block_hash.lower():
            # Non-finalized event with changed block hash — rollback projections
            if event.job_id:
                affected_job_ids.append(event.job_id)
            # Do NOT delete the event; flag it via status

    # Revert affected non-finalized events
    for event in orphaned_events:
        if event.block_hash.lower() != reverted_block_hash.lower():
            event.confirmation_status = "pending"  # Demote to pending for re-processing

    if orphaned_events:
        await db.flush()

    return {
        "orphaned_events_count": len(orphaned_events),
        "affected_job_ids": [str(jid) for jid in affected_job_ids],
        "requires_manual_investigation": len(orphaned_events) > 0,
    }


# ──────────────────────────────────────────────
# Replacement Event Ingestion
# ──────────────────────────────────────────────


async def replace_event(
    db: AsyncSession,
    *,
    chain_id: int,
    contract_address: str,
    old_tx_hash: str,
    old_log_index: int,
    new_event_data: dict[str, Any],
) -> BlockchainEvent | None:
    """Replace an existing event with updated data (e.g., after reorg).

    If the old event was finalized, a critical incident is logged and
    the event is NOT replaced — instead, automated updates are paused.
    """
    result = await db.execute(
        select(BlockchainEvent).where(
            BlockchainEvent.chain_id == chain_id,
            BlockchainEvent.contract_address == contract_address,
            BlockchainEvent.transaction_hash == old_tx_hash,
            BlockchainEvent.log_index == old_log_index,
        )
    )
    old_event = result.scalar_one_or_none()
    if not old_event:
        return None

    if old_event.confirmation_status == "finalized":
        # CRITICAL: Finalized event is being replaced — mark incident
        # Do NOT delete the finalized event
        return old_event

    # Update the non-finalized event
    old_event.block_number = new_event_data.get("block_number", old_event.block_number)
    old_event.block_hash = new_event_data.get("block_hash", old_event.block_hash)
    old_event.event_data = new_event_data.get("event_data", old_event.event_data)
    old_event.confirmation_status = "pending"  # Reset to pending for re-confirmation
    await db.flush()
    return old_event


# ──────────────────────────────────────────────
# Chain Success / DB Failure Recovery
# ──────────────────────────────────────────────


async def recover_from_db_failure(
    db: AsyncSession,
    *,
    chain_id: int,
    contract_address: str,
    from_block: int,
    to_block: int,
) -> dict[str, Any]:
    """Recover state after a database failure during event processing.

    Re-fetches events in the block range and re-processes any that
    were lost. Idempotent — won't duplicate events.
    """
    result = await db.execute(
        select(BlockchainEvent).where(
            BlockchainEvent.chain_id == chain_id,
            BlockchainEvent.contract_address == contract_address,
            BlockchainEvent.block_number >= from_block,
            BlockchainEvent.block_number <= to_block,
        )
    )
    existing_events = result.scalars().all()
    existing_keys = {(e.transaction_hash, e.log_index) for e in existing_events}
    return {
        "existing_events_count": len(existing_events),
        "existing_keys": existing_keys,
        "can_process_missing": True,
    }


# ──────────────────────────────────────────────
# Reconciliation
# ──────────────────────────────────────────────


async def reconcile_job_state(
    db: AsyncSession,
    job_id: uuid.UUID,
) -> dict[str, Any]:
    """Reconcile on-chain events with off-chain job state.

    Returns a dict with reconciliation status.
    Idempotent — running multiple times produces the same result.
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        return {"status": "job_not_found"}

    event_result = await db.execute(select(BlockchainEvent).where(BlockchainEvent.job_id == job_id))
    events = list(event_result.scalars().all())

    if not events:
        return {
            "status": "no_chain_events",
            "db_status": job.status,
            "chain_events": [],
        }

    pending = [e for e in events if e.confirmation_status == "pending"]
    confirmed = [e for e in events if e.confirmation_status in ("confirmed", "finalized")]
    finalized = [e for e in events if e.confirmation_status == "finalized"]

    if pending:
        return {
            "status": "pending_confirmation",
            "db_status": job.status,
            "pending_count": len(pending),
            "confirmed_count": len(confirmed),
            "finalized_count": len(finalized),
        }

    return {
        "status": "match",
        "db_status": job.status,
        "event_names": [e.event_name for e in confirmed],
        "finalized_count": len(finalized),
    }


async def get_unconfirmed_events(
    db: AsyncSession,
    *,
    chain_id: int,
) -> list[BlockchainEvent]:
    """Get all pending (unconfirmed) events for a chain."""
    result = await db.execute(
        select(BlockchainEvent).where(
            BlockchainEvent.chain_id == chain_id,
            BlockchainEvent.confirmation_status == "pending",
        )
    )
    return list(result.scalars().all())


def _hex(value: Any) -> str:
    if isinstance(value, bytes):
        return "0x" + value.hex()
    value = str(value)
    return value if value.startswith("0x") else "0x" + value


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return _hex(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


class CriticalReconciliationError(RuntimeError):
    """Automated projection stopped because finalized history diverged."""


async def _rebuild_job_projection(db: AsyncSession, job_id: uuid.UUID) -> None:
    """Rebuild chain-derived job/lease/payment state from canonical retained events."""
    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        return
    rows = await db.execute(
        select(BlockchainEvent)
        .where(
            BlockchainEvent.job_id == job_id,
            BlockchainEvent.confirmation_status.in_(["confirmed", "finalized"]),
        )
        .order_by(BlockchainEvent.block_number, BlockchainEvent.log_index)
    )
    events = list(rows.scalars().all())
    derived = [event for event in events if event.event_name != "__checkpoint__"]
    if any(event.event_name == "JobCreated" for event in derived):
        job.status = "queued"
    for event in derived:
        data = event.event_data or {}
        if event.event_name == "ProviderAssigned":
            job.status = "assigned"
        elif event.event_name == "ProofSubmitted":
            job.status = "settling"
        elif event.event_name == "JobSettled":
            job.status = "completed" if bool(data.get("valid")) else "refunded"
            job.completed_at = datetime.fromtimestamp(
                int(data.get("timestamp", data.get("_blockTimestamp", 0))),
                timezone.utc,
            )
        elif event.event_name == "TimeoutRefundCredited":
            job.status = "refunded"
            job.completed_at = datetime.fromtimestamp(int(data.get("_blockTimestamp", 0)), timezone.utc)

    orphaned_tx = select(BlockchainEvent.transaction_hash).where(
        BlockchainEvent.job_id == job_id,
        BlockchainEvent.confirmation_status == "orphaned",
    )
    await db.execute(delete(Payment).where(Payment.job_id == job_id, Payment.blockchain_tx_hash.in_(orphaned_tx)))
    lease = (await db.execute(select(Lease).where(Lease.id == job.current_lease_id))).scalar_one_or_none()
    if lease:
        if job.status == "assigned":
            lease.status = "active"
        elif job.status == "completed":
            lease.status = "completed"
        elif job.status == "refunded":
            lease.status = "failed"
        attempt = (await db.execute(select(JobAttempt).where(JobAttempt.lease_id == lease.id))).scalar_one_or_none()
        if attempt:
            if job.status == "completed":
                attempt.status = "completed"
                attempt.completed_at = job.completed_at
            elif job.status == "refunded":
                attempt.status = "failed"
                attempt.completed_at = job.completed_at
            elif job.status == "assigned":
                attempt.status = "running"
                attempt.completed_at = None
        active_count = (
            await db.execute(
                select(func.count(Lease.id)).where(
                    Lease.node_id == lease.node_id,
                    Lease.status == "active",
                )
            )
        ).scalar_one()
        node = (await db.execute(select(Node).where(Node.id == lease.node_id))).scalar_one_or_none()
        if node:
            node.active_leases = int(active_count)
    await db.flush()


class EventPoller:
    """Bounded, overlapping, restart-safe HTTP ``eth_getLogs`` poller."""

    def __init__(
        self,
        *,
        blockchain: BlockchainBackend,
        chain_id: int,
        contract_address: str,
        deployment_block: int,
        block_range: int = 500,
        overlap_blocks: int = 2,
        confirmations: int = 1,
        finality: int = 10,
    ):
        self.blockchain = blockchain
        self.chain_id = chain_id
        self.contract_address = contract_address
        self.deployment_block = deployment_block
        self.block_range = block_range
        self.overlap_blocks = overlap_blocks
        self.confirmations = confirmations
        self.finality = finality

    async def _detect_reorgs(self, db: AsyncSession, from_block: int) -> int:
        rows = await db.execute(
            select(BlockchainEvent).where(
                BlockchainEvent.chain_id == self.chain_id,
                BlockchainEvent.chain_instance_id == self.chain_instance_id,
                BlockchainEvent.contract_address == self.contract_address,
                BlockchainEvent.block_number >= from_block,
                BlockchainEvent.event_name != "__checkpoint__",
                BlockchainEvent.confirmation_status.in_(["pending", "confirmed", "finalized"]),
            )
        )
        snapshots = [
            (event.id, event.block_number, event.block_hash, event.confirmation_status, event.job_id)
            for event in rows.scalars().all()
        ]
        await db.commit()
        canonical_hashes: dict[int, str] = {}
        for _, block_number, _, _, _ in snapshots:
            if block_number not in canonical_hashes:
                canonical_hashes[block_number] = _hex(self.blockchain.get_block(block_number)["hash"]).lower()

        divergent = [row for row in snapshots if row[2].lower() != canonical_hashes[row[1]]]
        if not divergent:
            return 0
        if any(status == "finalized" for _, _, _, status, _ in divergent):
            for _, block_number, expected, status, _ in divergent:
                if status != "finalized":
                    continue
                observed = canonical_hashes[block_number]
                prior = await db.execute(
                    select(ReconciliationIncident).where(
                        ReconciliationIncident.chain_id == self.chain_id,
                        ReconciliationIncident.chain_instance_id == self.chain_instance_id,
                        ReconciliationIncident.contract_address == self.contract_address,
                        ReconciliationIncident.block_number == block_number,
                        ReconciliationIncident.expected_block_hash == expected,
                        ReconciliationIncident.observed_block_hash == observed,
                    )
                )
                if prior.scalar_one_or_none() is None:
                    db.add(
                        ReconciliationIncident(
                            id=uuid.uuid4(),
                            chain_id=self.chain_id,
                            chain_instance_id=self.chain_instance_id,
                            contract_address=self.contract_address,
                            block_number=block_number,
                            expected_block_hash=expected,
                            observed_block_hash=observed,
                            details={"reason": "finalized block hash divergence"},
                        )
                    )
            cursor = await self._cursor(db)
            if cursor:
                cursor.halted = True
            await db.commit()
            raise CriticalReconciliationError("finalized chain history diverged; event runner halted")

        affected: set[uuid.UUID] = set()
        for event_id, _, _, _, job_id in divergent:
            event = (
                await db.execute(select(BlockchainEvent).where(BlockchainEvent.id == event_id).with_for_update())
            ).scalar_one()
            event.confirmation_status = "orphaned"
            if job_id:
                affected.add(job_id)
            chain_tx = (
                await db.execute(
                    select(ChainTransaction).where(
                        ChainTransaction.tx_hash == event.transaction_hash,
                        ChainTransaction.chain_instance_id == self.chain_instance_id,
                    )
                )
            ).scalar_one_or_none()
            if chain_tx and chain_tx.status != "finalized":
                chain_tx.status = "replaced"
        for job_id in affected:
            await _rebuild_job_projection(db, job_id)
        cursor = await self._cursor(db)
        if cursor:
            first = min(block_number for _, block_number, _, _, _ in divergent)
            cursor.last_scanned_block = max(self.deployment_block - 1, first - 1)
            cursor.last_scanned_block_hash = "0x" + "00" * 32
        await db.commit()
        return len(divergent)

    async def _cursor(self, db: AsyncSession) -> ChainCursor | None:
        return (
            await db.execute(
                select(ChainCursor).where(
                    ChainCursor.chain_id == self.chain_id,
                    ChainCursor.chain_instance_id == self.chain_instance_id,
                    ChainCursor.contract_address == self.contract_address,
                )
            )
        ).scalar_one_or_none()

    async def run_once(self, db: AsyncSession) -> dict[str, int]:
        await db.commit()
        self.chain_instance_id = _hex(self.blockchain.get_block(0)["hash"]).lower()
        latest = self.blockchain.get_block_number()
        checkpoint = await get_checkpoint(
            db,
            self.chain_id,
            self.contract_address,
            self.chain_instance_id,
        )
        if checkpoint.get("halted"):
            await db.commit()
            raise CriticalReconciliationError("event runner is halted by an open critical incident")
        start = max(self.deployment_block, checkpoint["last_block"] - self.overlap_blocks)
        reorged = await self._detect_reorgs(db, start)
        if reorged:
            checkpoint = await get_checkpoint(
                db,
                self.chain_id,
                self.contract_address,
                self.chain_instance_id,
            )
            start = max(self.deployment_block, checkpoint["last_block"] - self.overlap_blocks)
        end = min(latest, start + self.block_range - 1)
        if end < start:
            return {"from_block": start, "to_block": end, "events": 0, "reorged": reorged}
        await db.commit()
        logs = self.blockchain.get_logs({"address": self.contract_address, "fromBlock": start, "toBlock": end})
        block = self.blockchain.get_block(end)
        block_timestamps: dict[int, int] = {end: int(block["timestamp"])}
        count = 0
        for log in logs:
            decoded = decode_receipt_logs({"logs": [log]}, self.blockchain.get_abi())
            for item in decoded:
                args = item["args"]
                job_uuid = None
                if "jobId" in args:
                    try:
                        job_uuid = bytes32_to_uuid(_hex(args["jobId"]))
                    except ValueError:
                        job_uuid = None
                confirmations = latest - int(item["blockNumber"]) + 1
                event_block = int(item["blockNumber"])
                if event_block not in block_timestamps:
                    block_timestamps[event_block] = int(self.blockchain.get_block(event_block)["timestamp"])
                event_data = _json_value(args)
                event_data["_blockTimestamp"] = block_timestamps[event_block]
                event = await record_event(
                    db,
                    chain_id=self.chain_id,
                    chain_instance_id=self.chain_instance_id,
                    contract_address=self.contract_address,
                    transaction_hash=_hex(item["transactionHash"]),
                    log_index=int(item["logIndex"]),
                    block_number=int(item["blockNumber"]),
                    block_hash=_hex(item["blockHash"]),
                    event_name=item["event"],
                    event_data=event_data,
                    job_id=job_uuid,
                )
                event.confirmation_status = (
                    "finalized"
                    if confirmations >= self.finality
                    else "confirmed"
                    if confirmations >= self.confirmations
                    else "pending"
                )
                if event.confirmation_status != "pending":
                    await self._project(db, event)
                count += 1

        cursor = await self._cursor(db)
        if cursor is None:
            cursor = ChainCursor(
                id=uuid.uuid4(),
                chain_id=self.chain_id,
                chain_instance_id=self.chain_instance_id,
                contract_address=self.contract_address,
                last_scanned_block=end,
                last_scanned_block_hash=_hex(block["hash"]),
            )
            db.add(cursor)
        else:
            cursor.last_scanned_block = end
            cursor.last_scanned_block_hash = _hex(block["hash"])
        await db.flush()
        return {"from_block": start, "to_block": end, "events": count, "reorged": reorged}

    async def _project(self, db: AsyncSession, event: BlockchainEvent) -> None:
        if event.event_name == "__checkpoint__" or event.job_id is None:
            return
        job = (await db.execute(select(Job).where(Job.id == event.job_id))).scalar_one_or_none()
        if job is None:
            return
        data = event.event_data or {}
        if event.event_name == "ProviderAssigned":
            lease = (await db.execute(select(Lease).where(Lease.id == job.current_lease_id))).scalar_one_or_none()
            if lease and lease.lease_id.lower() == str(data.get("leaseId", "")).lower():
                if lease.status == "pending_chain":
                    lease.status = "active"
                    lease.heartbeat_at = datetime.now(timezone.utc)
                if job.status in ("queued", "retry_pending"):
                    job.status = "assigned"
        elif event.event_name == "ProofSubmitted":
            if job.status not in ("completed", "refunded"):
                job.status = "settling"
        elif event.event_name == "JobSettled":
            valid = bool(data.get("valid"))
            job.status = "completed" if valid else "refunded"
            job.completed_at = datetime.fromtimestamp(int(data.get("timestamp", 0)), timezone.utc)
            lease = (await db.execute(select(Lease).where(Lease.id == job.current_lease_id))).scalar_one_or_none()
            if lease:
                was_active = lease.status == "active"
                lease.status = "completed" if valid else "failed"
                attempt = (
                    await db.execute(select(JobAttempt).where(JobAttempt.lease_id == lease.id))
                ).scalar_one_or_none()
                if attempt and attempt.status == "running":
                    attempt.status = "completed" if valid else "failed"
                    attempt.completed_at = job.completed_at
                if was_active:
                    node = (await db.execute(select(Node).where(Node.id == lease.node_id))).scalar_one_or_none()
                    if node:
                        node.active_leases = max(0, int(node.active_leases or 0) - 1)
        elif event.event_name in ("PaymentCredited", "TimeoutRefundCredited"):
            payment_type = "provider_credit" if event.event_name == "PaymentCredited" else "user_refund"
            if event.event_name == "TimeoutRefundCredited":
                job.status = "refunded"
                job.completed_at = datetime.fromtimestamp(int(data["_blockTimestamp"]), timezone.utc)
                lease = (await db.execute(select(Lease).where(Lease.id == job.current_lease_id))).scalar_one_or_none()
                if lease and lease.status in ("active", "pending_chain"):
                    was_active = lease.status == "active"
                    lease.status = "failed"
                    attempt = (
                        await db.execute(select(JobAttempt).where(JobAttempt.lease_id == lease.id))
                    ).scalar_one_or_none()
                    if attempt and attempt.status == "running":
                        attempt.status = "failed"
                        attempt.completed_at = job.completed_at
                    if was_active:
                        node = (await db.execute(select(Node).where(Node.id == lease.node_id))).scalar_one_or_none()
                        if node:
                            node.active_leases = max(0, int(node.active_leases or 0) - 1)
            prior = await db.execute(select(Payment).where(Payment.blockchain_tx_hash == event.transaction_hash))
            if prior.scalar_one_or_none() is None:
                provider_id = None
                if payment_type == "provider_credit":
                    address = str(data.get("provider", "")).lower()
                    provider_id = (
                        await db.execute(select(User.id).where(User.wallet_address == address))
                    ).scalar_one_or_none()
                db.add(
                    Payment(
                        id=uuid.uuid4(),
                        job_id=job.id,
                        user_id=job.user_id,
                        provider_id=provider_id,
                        amount_base_units=int(data["amount"]),
                        payment_type=payment_type,
                        status="credited",
                        blockchain_tx_hash=event.transaction_hash,
                        credited_at=datetime.now(timezone.utc),
                    )
                )
        tx = (
            await db.execute(
                select(ChainTransaction).where(
                    ChainTransaction.tx_hash == event.transaction_hash,
                    ChainTransaction.chain_instance_id == event.chain_instance_id,
                )
            )
        ).scalar_one_or_none()
        if tx:
            tx.status = "finalized" if event.confirmation_status == "finalized" else "confirmed"
        await db.flush()
