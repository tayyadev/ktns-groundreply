"""Workspace-scoped vector retrieval and approved-history memory."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Chunk, Document, Ticket
from app.text_utils import Evidence


async def retrieve_evidence(
    session: AsyncSession, org_id: uuid.UUID, vector: list[float], limit: int = 5
) -> list[Evidence]:
    distance = Chunk.embedding.cosine_distance(vector).label("distance")
    stmt = (
        select(Chunk, Document.title, distance)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.organization_id == org_id, Document.organization_id == org_id, Document.status == "ready")
        .order_by(distance)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        Evidence(
            id=f"K{i}", document_id=str(chunk.document_id), title=title,
            content=chunk.content, similarity=round(1 - float(d), 4),
        )
        for i, (chunk, title, d) in enumerate(rows, start=1)
        if float(d) <= get_settings().max_cosine_distance
    ]


async def approved_memory(session: AsyncSession, org_id: uuid.UUID, requester_email: str | None) -> list[str]:
    if not requester_email:
        return []
    results = (
        await session.execute(
            select(Ticket)
            .where(
                Ticket.organization_id == org_id,
                Ticket.requester_email == requester_email.lower(),
                Ticket.status == "approved",
            )
            .order_by(Ticket.approved_at.desc())
            .limit(3)
        )
    ).scalars().all()
    return [f"Earlier issue: {t.question[:350]}\nApproved response: {(t.draft or '')[:500]}" for t in results]
