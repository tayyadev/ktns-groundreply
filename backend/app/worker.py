"""Start with `python -m app.worker`. Scale by adding identical worker containers."""
import asyncio
import logging
import signal
import uuid

from sqlalchemy import delete, select

from app.agents import orchestrate
from app.db import SessionFactory
from app.jobs import claim, heartbeat, settle
from app.llm import OpenAIProvider
from app.models import (
    Chunk, Document, EvaluationCase, EvaluationRun, Job, Ticket, UsageEvent, now
)
from app.retrieval import approved_memory, retrieve_evidence
from app.text_utils import chunk_text, evaluation_passed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("groundreply.worker")


async def record_usage(org_id: uuid.UUID, entity_id: uuid.UUID, provider: OpenAIProvider) -> None:
    async with SessionFactory() as session:
        for entry in provider.meter:
            session.add(UsageEvent(
                organization_id=org_id, entity_id=entity_id, model=entry.model,
                input_tokens=entry.input_tokens, output_tokens=entry.output_tokens,
            ))
        await session.commit()


async def process_document(job: Job) -> None:
    async with SessionFactory() as session:
        doc = (await session.execute(
            select(Document).where(Document.id == job.entity_id, Document.organization_id == job.organization_id)
        )).scalar_one_or_none()
        if not doc or doc.status == "ready":
            return  # deleted or already committed by an earlier execution
        doc.status = "processing"
        doc.error = None
        content = doc.content
        await session.commit()

    passages = chunk_text(content)
    provider = OpenAIProvider()
    embeddings: list[list[float]] = []
    for start in range(0, len(passages), 32):
        embeddings.extend(await provider.embed(passages[start:start + 32]))
    if len(passages) != len(embeddings):
        raise RuntimeError("Embedding count mismatch")

    async with SessionFactory() as session:
        doc = (await session.execute(
            select(Document)
            .where(Document.id == job.entity_id, Document.organization_id == job.organization_id)
            .with_for_update()
        )).scalar_one_or_none()
        if not doc:
            return
        await session.execute(delete(Chunk).where(Chunk.document_id == doc.id, Chunk.organization_id == job.organization_id))
        session.add_all([
            Chunk(
                organization_id=job.organization_id, document_id=doc.id, position=index,
                content=passage, embedding=vector,
            )
            for index, (passage, vector) in enumerate(zip(passages, embeddings, strict=True))
        ])
        doc.status = "ready"
        doc.chunk_count = len(passages)
        await session.commit()
    await record_usage(job.organization_id, job.entity_id, provider)


async def process_ticket(job: Job) -> None:
    async with SessionFactory() as session:
        ticket = (await session.execute(
            select(Ticket).where(Ticket.id == job.entity_id, Ticket.organization_id == job.organization_id)
        )).scalar_one_or_none()
        if not ticket:
            return
        if ticket.status in ("approved", "rejected", "awaiting_approval", "needs_review"):
            return  # do not overwrite a completed AI draft or human decision on delayed retries
        ticket.status = "processing"
        ticket.error = None
        question, subject, email = ticket.question, ticket.subject, ticket.requester_email
        await session.commit()

    async with SessionFactory() as session:
        memory = await approved_memory(session, job.organization_id, email)
    provider = OpenAIProvider()

    async def retrieve(vector: list[float]):
        async with SessionFactory() as session:
            return await retrieve_evidence(session, job.organization_id, vector)

    result = await orchestrate(provider, question, subject, memory, retrieve)
    async with SessionFactory() as session:
        ticket = (await session.execute(
            select(Ticket).where(Ticket.id == job.entity_id, Ticket.organization_id == job.organization_id)
            .with_for_update()
        )).scalar_one_or_none()
        if not ticket or ticket.status in ("approved", "rejected"):
            return
        ticket.status = result.status
        ticket.category = result.category
        ticket.priority = result.priority
        ticket.draft = result.draft
        ticket.citations = result.citations
        ticket.review_flags = result.flags
        ticket.trace = result.trace
        ticket.processed_at = now()
        await session.commit()
    await record_usage(job.organization_id, job.entity_id, provider)


async def process_evaluation(job: Job) -> None:
    async with SessionFactory() as session:
        run = (await session.execute(
            select(EvaluationRun)
            .where(EvaluationRun.id == job.entity_id, EvaluationRun.organization_id == job.organization_id)
        )).scalar_one_or_none()
        if not run or run.status == "completed":
            return
        cases = (await session.execute(
            select(EvaluationCase).where(EvaluationCase.organization_id == job.organization_id)
            .order_by(EvaluationCase.created_at).limit(20)
        )).scalars().all()
        snapshot = [(str(c.id), c.question, c.must_include, c.expect_abstain) for c in cases]
        run.status = "processing"
        run.error = None
        await session.commit()

    results = []
    provider = OpenAIProvider()

    async def retrieve(vector: list[float]):
        async with SessionFactory() as session:
            return await retrieve_evidence(session, job.organization_id, vector)

    for case_id, question, must_include, expect_abstain in snapshot:
        output = await orchestrate(provider, question, "Evaluation case", [], retrieve)
        passed = evaluation_passed(
            output.draft, output.citations, must_include, expect_abstain, output.abstained,
            review_ok=(output.status == "awaiting_approval"),
        )
        results.append({
            "case_id": case_id, "question": question, "passed": passed,
            "abstained": output.abstained, "citations": len(output.citations),
            "status": output.status, "preview": output.draft[:220],
        })

    async with SessionFactory() as session:
        run = (await session.execute(
            select(EvaluationRun).where(EvaluationRun.id == job.entity_id, EvaluationRun.organization_id == job.organization_id)
        )).scalar_one_or_none()
        if not run:
            return
        run.status = "completed"
        run.passed = sum(item["passed"] for item in results)
        run.total = len(results)
        run.results = results
        run.finished_at = now()
        await session.commit()
    await record_usage(job.organization_id, job.entity_id, provider)


async def process(job: Job) -> None:
    if job.kind == "index_document":
        await process_document(job)
    elif job.kind == "draft_ticket":
        await process_ticket(job)
    elif job.kind == "run_evaluation":
        await process_evaluation(job)
    else:
        raise ValueError(f"Unsupported job type: {job.kind}")


async def mark_failure(job: Job, detail: str) -> None:
    async with SessionFactory() as session:
        if job.kind == "index_document":
            doc = (await session.execute(select(Document).where(Document.id == job.entity_id, Document.organization_id == job.organization_id))).scalar_one_or_none()
            if doc and doc.status != "ready":
                doc.status = "failed"
                doc.error = detail
        elif job.kind == "draft_ticket":
            ticket = (await session.execute(select(Ticket).where(Ticket.id == job.entity_id, Ticket.organization_id == job.organization_id))).scalar_one_or_none()
            if ticket and ticket.status not in ("approved", "rejected"):
                ticket.status = "failed"
                ticket.error = detail
        elif job.kind == "run_evaluation":
            run = (await session.execute(select(EvaluationRun).where(EvaluationRun.id == job.entity_id, EvaluationRun.organization_id == job.organization_id))).scalar_one_or_none()
            if run and run.status != "completed":
                run.status = "failed"
                run.error = detail
        await session.commit()


async def heartbeat_loop(job: Job, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            try:
                async with SessionFactory() as session:
                    await heartbeat(session, job.id, job.lease_token)
            except Exception:
                log.exception("Could not extend lease for %s", job.id)


async def run() -> None:
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stopping.set)
        except NotImplementedError:
            pass
    log.info("Worker started")
    while not stopping.is_set():
        try:
            async with SessionFactory() as session:
                job = await claim(session)
            if not job:
                try:
                    await asyncio.wait_for(stopping.wait(), timeout=1.5)
                except asyncio.TimeoutError:
                    pass
                continue
            heartbeat_stop = asyncio.Event()
            pulse = asyncio.create_task(heartbeat_loop(job, heartbeat_stop))
            error = None
            try:
                await process(job)
            except Exception as exc:
                # Do not log model inputs or sensitive customer content.
                error = f"{type(exc).__name__}: Processing failed; review server logs"
                log.error("Job %s (%s) failed; exception_type=%s", job.id, job.kind, type(exc).__name__)
            finally:
                heartbeat_stop.set()
                await pulse
            async with SessionFactory() as session:
                dead = await settle(session, job.id, job.lease_token, error)
            if dead:
                await mark_failure(job, error or "Retries exhausted")
        except Exception:
            log.exception("Worker loop error")
            await asyncio.sleep(3)
    log.info("Worker exiting")


if __name__ == "__main__":
    asyncio.run(run())
