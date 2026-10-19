"""Postgres-backed job queue: SKIP LOCKED claims, leases, retries and dead letter."""
import uuid
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, now

LEASE_SECONDS = 300


def enqueue(organization_id: uuid.UUID, kind: str, entity_id: uuid.UUID) -> Job:
    return Job(organization_id=organization_id, kind=kind, entity_id=entity_id)


async def claim(session: AsyncSession) -> Job | None:
    timestamp = now()
    # Reclaim crashed workers. Heartbeats prevent lease expiry for healthy workers.
    await session.execute(
        update(Job)
        .where(Job.status == "running", Job.lease_until < timestamp)
        .values(status="retry", run_at=timestamp, lease_until=None, lease_token=None)
    )
    result = await session.execute(
        select(Job)
        .where(Job.status.in_(["pending", "retry"]), Job.run_at <= timestamp, Job.attempts < Job.max_attempts)
        .order_by(Job.run_at, Job.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if job:
        job.status = "running"
        job.attempts += 1
        job.lease_until = timestamp + timedelta(seconds=LEASE_SECONDS)
        job.lease_token = uuid.uuid4()
    await session.commit()
    return job


async def heartbeat(session: AsyncSession, job_id: uuid.UUID, lease_token: uuid.UUID) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "running", Job.lease_token == lease_token)
        .values(lease_until=now() + timedelta(seconds=LEASE_SECONDS))
    )
    await session.commit()


async def settle(session: AsyncSession, job_id: uuid.UUID, lease_token: uuid.UUID, error: str | None = None) -> bool:
    row = (await session.execute(select(Job).where(Job.id == job_id, Job.lease_token == lease_token).with_for_update())).scalar_one_or_none()
    if not row or row.status != "running":
        await session.rollback()
        return False
    row.lease_until = None
    row.lease_token = None
    if error is None:
        row.status = "succeeded"
        row.last_error = None
    else:
        row.last_error = error[:300]
        if row.attempts >= row.max_attempts:
            row.status = "dead"
        else:
            row.status = "retry"
            row.run_at = now() + timedelta(seconds=min(300, 3 * 2 ** row.attempts))
    await session.commit()
    return row.status == "dead"
