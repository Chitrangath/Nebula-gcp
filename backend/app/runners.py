"""Executable bounded runtime runners for Phase 3 Integration Closure."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import ChainTransaction, Lease
from app.services.assignment_dispatcher import AssignmentDispatcher
from app.services.blockchain_events import CriticalReconciliationError, EventPoller, reconcile_job_state
from app.services.blockchain_service import Web3Backend
from app.services.chain_outbox import get_chain_instance_id
from app.services.escrow_confirmation import ReceiptConfirmer
from app.services.retry_policy import reconcile_expired_leases
from app.services.scheduler import schedule_next_job
from app.services.settlement_coordinator import SettlementCoordinator
from app.services.storage import build_storage, storage_config_from_settings
from app.services.tx_signer import Web3Signer

logger = logging.getLogger("nebula.runners")


def build_runtime():
    chain = Web3Backend(settings.ARBITRUM_SEPOLIA_RPC, timeout=settings.RPC_TIMEOUT_SECONDS)
    signer = Web3Signer(settings.ARBITRUM_SEPOLIA_RPC)
    storage = build_storage(storage_config_from_settings(settings))
    dispatcher = AssignmentDispatcher(
        blockchain=chain,
        signer=signer,
        contract_address=settings.NEBULA_PAYMENT_CONTRACT,
        chain_id=settings.CHAIN_ID,
        rpc_url=settings.ARBITRUM_SEPOLIA_RPC,
        receipt_timeout=settings.RPC_TIMEOUT_SECONDS,
    )
    receipt_confirmer = ReceiptConfirmer(
        blockchain=chain,
        chain_id=settings.CHAIN_ID,
        contract_address=settings.NEBULA_PAYMENT_CONTRACT,
        confirmations_required=settings.CONFIRMATION_DEPTH,
        batch_size=settings.RUNNER_BATCH_SIZE,
    )
    settlement = SettlementCoordinator(
        blockchain=chain,
        signer=signer,
        storage=storage,
        contract_address=settings.NEBULA_PAYMENT_CONTRACT,
        chain_id=settings.CHAIN_ID,
        batch_size=settings.RUNNER_BATCH_SIZE,
        claim_ttl_seconds=settings.PROOF_CLAIM_TTL_SECONDS,
    )
    poller = EventPoller(
        blockchain=chain,
        chain_id=settings.CHAIN_ID,
        contract_address=settings.NEBULA_PAYMENT_CONTRACT,
        deployment_block=settings.CONTRACT_DEPLOYMENT_BLOCK,
        block_range=settings.EVENT_BLOCK_RANGE,
        overlap_blocks=settings.EVENT_OVERLAP_BLOCKS,
        confirmations=settings.CONFIRMATION_DEPTH,
        finality=settings.FINALITY_DEPTH,
    )
    return chain, storage, receipt_confirmer, dispatcher, settlement, poller


async def assignment_once(dispatcher: AssignmentDispatcher) -> dict[str, int]:
    scheduled = 0
    async with async_session() as db:
        for _ in range(settings.RUNNER_BATCH_SIZE):
            if await schedule_next_job(db) is None:
                break
            scheduled += 1
        await db.commit()
    async with async_session() as db:
        dispatched = len(await dispatcher.dispatch_pending_assignments(db))
        await db.commit()
    confirmed = 0
    chain_instance_id = get_chain_instance_id(dispatcher._blockchain)
    async with async_session() as db:
        rows = await db.execute(
            select(ChainTransaction).where(
                ChainTransaction.tx_type == "assignProvider",
                ChainTransaction.status == "submitted",
                ChainTransaction.chain_id == dispatcher._chain_id,
                ChainTransaction.chain_instance_id == chain_instance_id,
                ChainTransaction.contract_address == dispatcher._contract_address,
            )
        )
        for intent in rows.scalars().all():
            if intent.lease_id and await dispatcher.confirm_assignment(
                db,
                lease_id=intent.lease_id,
                tx_hash=intent.tx_hash,
                block_number=0,
                block_hash="",
            ):
                confirmed += 1
        await db.commit()
    return {"scheduled": scheduled, "dispatched": dispatched, "confirmed": confirmed}


async def reconciliation_once() -> int:
    async with async_session() as db:
        await reconcile_expired_leases(db)
        leases = await db.execute(select(Lease.job_id).distinct())
        job_ids = list(leases.scalars().all())
        for job_id in job_ids:
            await reconcile_job_state(db, job_id)
        await db.commit()
        return len(job_ids)


async def run(name: str, once: bool) -> None:
    _, _, receipt_confirmer, dispatcher, settlement, poller = build_runtime()
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    while not stopped.is_set():
        try:
            if name == "receipts":
                async with async_session() as db:
                    result = await receipt_confirmer.run_once(db)
            elif name == "assignment":
                result = await assignment_once(dispatcher)
            elif name == "settlement":
                async with async_session() as db:
                    result = await settlement.run_once(db)
            elif name == "events":
                async with async_session() as db:
                    result = await poller.run_once(db)
                    await db.commit()
            else:
                result = {"reconciled": await reconciliation_once()}
        except asyncio.CancelledError:
            raise
        except CriticalReconciliationError:
            # A finalized-history divergence is a safety stop, not a
            # transient outage.  Preserve the existing fail-closed behavior.
            logger.exception("runner_critical_reconciliation_failure name=%s", name)
            raise
        except Exception:
            # RPC providers, database connections, and object storage can all
            # fail transiently.  A child process that exits here leaves jobs
            # stuck forever (most visibly in `settling`).  Keep the runner
            # alive and retry; the session context has already rolled back.
            logger.exception("runner_cycle_failed name=%s; retrying", name)
            result = None
        if result is not None:
            logger.info("runner_cycle name=%s result=%s", name, result)
        if once:
            return
        try:
            delay = (
                settings.RUNNER_POLL_INTERVAL_SECONDS
                if result is not None
                else settings.RUNNER_ERROR_BACKOFF_SECONDS
            )
            await asyncio.wait_for(stopped.wait(), delay)
        except TimeoutError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "runner",
        choices=["receipts", "assignment", "settlement", "events", "reconciliation"],
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run(args.runner, args.once))


if __name__ == "__main__":
    main()
