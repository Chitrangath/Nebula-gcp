"""Independent PostgreSQL schedulers must never reserve one GPU twice."""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Job, Lease, Node, SupportedModel, User
from app.services.scheduler import schedule_next_job


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_count", [1, 2])
async def test_independent_schedulers_reserve_distinct_provider_nodes(provider_count):
    url = os.environ.get("DATABASE_URL", "")
    if urlsplit(url).path != "/nebula_test" or not url.startswith("postgresql+asyncpg://"):
        pytest.skip("requires dedicated nebula_test PostgreSQL")
    schema = "demo002_" + uuid.uuid4().hex
    admin = create_async_engine(url)
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db, db.begin():
            user = User(wallet_address="0x" + "11" * 20, role="user")
            model = SupportedModel(id="resnet50", name="ResNet50", price_base_units=50000, vram_required_gb=2)
            db.add_all([user, model])
            for index in range(provider_count):
                provider = User(wallet_address="0x" + f"{index + 2:02x}" * 20, role="provider")
                db.add(provider)
                await db.flush()
                db.add(
                    Node(
                        provider_id=provider.id,
                        status="online",
                        vram_gb=4,
                        api_key_hash=uuid.uuid4().hex * 2,
                        active_leases=0,
                        last_heartbeat=datetime.now(timezone.utc),
                    )
                )
            await db.flush()
            for _ in range(2):
                db.add(
                    Job(
                        user_id=user.id,
                        model_id=model.id,
                        chain_job_id="0x" + uuid.uuid4().hex * 2,
                        status="queued",
                        price_base_units=50000,
                        deadline=datetime.now(timezone.utc) + timedelta(hours=1),
                        current_attempt=0,
                    )
                )

        async def schedule():
            async with sessions() as db, db.begin():
                return await schedule_next_job(db)

        await asyncio.gather(schedule(), schedule())
        async with sessions() as db:
            leases = (await db.execute(select(Lease))).scalars().all()
        assert len(leases) == provider_count
        assert len({lease.node_id for lease in leases}) == provider_count
        assert len({lease.job_id for lease in leases}) == provider_count
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()
