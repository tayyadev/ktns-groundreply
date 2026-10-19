import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import quota_for
from app.dependencies import ActorDep, SessionDep, require_owner, require_write
from app.jobs import enqueue
from app.models import (
    AuditEvent, Document, EvaluationCase, EvaluationRun, Invite, Job, Membership,
    Organization, Ticket, UsageEvent, User, now,
)
from app.schemas import (
    DocumentCreate, EvaluationCaseCreate, InviteAccept, InviteCreate,
    LoginRequest, RegisterRequest, TicketCreate, TicketDecision,
)
from app.security import (
    csrf_token, decode_session, hash_password, invite_digest, make_invite_token,
    new_session_token, verify_password,
)
from app.config import get_settings

router = APIRouter(tags=["api"])


def as_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def auth_cookie(response: Response, user_id: uuid.UUID) -> None:
    response.set_cookie(
        "groundreply_session", new_session_token(user_id),
        max_age=12 * 60 * 60, httponly=True, secure=get_settings().cookie_secure,
        samesite="lax", path="/api",
    )


def audited(session: AsyncSession, actor: ActorDep, action: str, entity: uuid.UUID | None, details: dict | None = None) -> None:
    session.add(AuditEvent(
        organization_id=actor.organization_id, actor_id=actor.user_id,
        action=action, entity_id=entity, details=details or {},
    ))


def ticket_json(ticket: Ticket, detail: bool = False) -> dict:
    value = {
        "id": str(ticket.id), "subject": ticket.subject, "status": ticket.status,
        "category": ticket.category, "priority": ticket.priority,
        "requester_email": ticket.requester_email,
        "created_at": as_iso(ticket.created_at), "processed_at": as_iso(ticket.processed_at),
        "approved_at": as_iso(ticket.approved_at),
    }
    if detail:
        value.update({
            "question": ticket.question, "draft": ticket.draft,
            "citations": ticket.citations, "review_flags": ticket.review_flags,
            "trace": ticket.trace, "error": ticket.error,
        })
    return value


def document_json(doc: Document) -> dict:
    return {
        "id": str(doc.id), "title": doc.title, "status": doc.status,
        "chunk_count": doc.chunk_count, "error": doc.error, "created_at": as_iso(doc.created_at),
    }


@router.post("/auth/register", status_code=201)
async def register(payload: RegisterRequest, response: Response, session: SessionDep):
    email = str(payload.email).lower()
    if (await session.execute(select(User.id).where(User.email == email))).first():
        raise HTTPException(409, "An account already exists with this email")
    user = User(email=email, password_hash=hash_password(payload.password))
    org = Organization(name=payload.organization_name.strip())
    session.add_all([user, org])
    await session.flush()
    session.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))
    session.add(AuditEvent(
        organization_id=org.id, actor_id=user.id, action="workspace.created", entity_id=org.id,
    ))
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Account already exists") from exc
    auth_cookie(response, user.id)
    return {"ok": True}


@router.post("/auth/login")
async def login(payload: LoginRequest, response: Response, session: SessionDep):
    email = str(payload.email).lower()
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    # For unknown users, simulate password hash verification to reduce email enumeration.
    if user is None:
        verify_password(
            "$argon2id$v=19$m=65536,t=3,p=4$7g6eqvicNrNT6tnmclodvQ$d4SjmRBAWLDmrlgqRM0PbgtXK+KAOgg8BuWkNuvdXYQ",
            payload.password,
        )
    if not user or not verify_password(user.password_hash, payload.password):
        raise HTTPException(401, "Invalid email or password")
    auth_cookie(response, user.id)
    return {"ok": True}


@router.get("/auth/me")
async def me(actor: ActorDep):
    return {
        "user_id": str(actor.user_id), "email": actor.email, "role": actor.role,
        "organization_id": str(actor.organization_id),
        "organization_name": actor.organization_name, "plan": actor.plan,
        "csrf_token": csrf_token(actor.token_claims),
    }


@router.post("/auth/logout")
async def logout(response: Response, actor: ActorDep):
    response.delete_cookie("groundreply_session", path="/api")
    return {"ok": True}


@router.post("/auth/accept-invite", status_code=201)
async def accept_invite(payload: InviteAccept, response: Response, session: SessionDep):
    digest = invite_digest(payload.token)
    invite = (await session.execute(
        select(Invite).where(Invite.digest == digest).with_for_update()
    )).scalar_one_or_none()
    if not invite or invite.accepted_at or invite.expires_at < now():
        raise HTTPException(400, "Invitation invalid or expired")
    existing = (await session.execute(select(User.id).where(User.email == invite.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Email already has an account; ask the owner for a different invitation")
    user = User(email=invite.email, password_hash=hash_password(payload.password))
    session.add(user)
    await session.flush()
    session.add(Membership(user_id=user.id, organization_id=invite.organization_id, role=invite.role))
    session.add(AuditEvent(
        organization_id=invite.organization_id, actor_id=user.id,
        action="team.invite_accepted", entity_id=invite.id,
    ))
    invite.accepted_at = now()
    await session.commit()
    auth_cookie(response, user.id)
    return {"ok": True}


@router.get("/team")
async def team(actor: ActorDep, session: SessionDep):
    rows = (await session.execute(
        select(User.email, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == actor.organization_id)
        .order_by(User.email)
    )).all()
    return [{"email": email, "role": role} for email, role in rows]


@router.post("/team/invite", status_code=201)
async def invite_team(payload: InviteCreate, actor: ActorDep, session: SessionDep):
    require_owner(actor)
    email = str(payload.email).lower()
    if (await session.execute(select(User.id).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "This email already has an account")
    token, digest = make_invite_token()
    invitation = Invite(
        organization_id=actor.organization_id, email=email, role=payload.role,
        digest=digest, expires_at=now() + timedelta(days=3),
    )
    session.add(invitation)
    audited(session, actor, "team.invite_created", invitation.id, {"role": payload.role})
    await session.commit()
    # Returned once only, never persisted as plaintext. Owner copies to intended teammate.
    return {"invite_url": f"{get_settings().app_origin}/?invite={token}", "expires_in_hours": 72}


@router.get("/overview")
async def overview(actor: ActorDep, session: SessionDep):
    month = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_tickets = (await session.scalar(select(func.count()).select_from(Ticket).where(Ticket.organization_id == actor.organization_id))) or 0
    this_month = (await session.scalar(select(func.count()).select_from(Ticket).where(Ticket.organization_id == actor.organization_id, Ticket.created_at >= month))) or 0
    pending = (await session.scalar(select(func.count()).select_from(Ticket).where(Ticket.organization_id == actor.organization_id, Ticket.status.in_(["awaiting_approval", "needs_review"])))) or 0
    approved = (await session.scalar(select(func.count()).select_from(Ticket).where(Ticket.organization_id == actor.organization_id, Ticket.status == "approved"))) or 0
    docs = (await session.scalar(select(func.count()).select_from(Document).where(Document.organization_id == actor.organization_id, Document.status == "ready"))) or 0
    token_totals = (await session.execute(
        select(func.coalesce(func.sum(UsageEvent.input_tokens), 0), func.coalesce(func.sum(UsageEvent.output_tokens), 0))
        .where(UsageEvent.organization_id == actor.organization_id, UsageEvent.created_at >= month)
    )).one()
    return {
        "total_tickets": total_tickets, "this_month": this_month, "needs_action": pending,
        "approved": approved, "ready_documents": docs,
        "monthly_limit": quota_for(actor.plan), "input_tokens": int(token_totals[0]),
        "output_tokens": int(token_totals[1]),
    }


@router.get("/documents")
async def list_documents(actor: ActorDep, session: SessionDep):
    docs = (await session.execute(
        select(Document).where(Document.organization_id == actor.organization_id)
        .order_by(Document.created_at.desc()).limit(100)
    )).scalars().all()
    return [document_json(doc) for doc in docs]


@router.post("/documents", status_code=202)
async def create_document(payload: DocumentCreate, actor: ActorDep, session: SessionDep):
    require_write(actor)
    org = (await session.execute(
        select(Organization).where(Organization.id == actor.organization_id).with_for_update()
    )).scalar_one()
    count = (await session.scalar(select(func.count()).select_from(Document).where(
        Document.organization_id == actor.organization_id
    ))) or 0
    cap = {"trial": 10, "starter": 100, "growth": 1000}.get(org.plan, 10)
    if count >= cap:
        raise HTTPException(402, "Knowledge-source allowance reached for this plan")
    doc = Document(
        organization_id=actor.organization_id, created_by=actor.user_id,
        title=payload.title.strip(), content=payload.content.strip(),
    )
    session.add(doc)
    await session.flush()
    session.add(enqueue(actor.organization_id, "index_document", doc.id))
    audited(session, actor, "knowledge.created", doc.id)
    await session.commit()
    return document_json(doc)


@router.delete("/documents/{document_id}")
async def delete_document(document_id: uuid.UUID, actor: ActorDep, session: SessionDep):
    require_write(actor)
    doc = (await session.execute(select(Document).where(Document.id == document_id, Document.organization_id == actor.organization_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    await session.delete(doc)
    audited(session, actor, "knowledge.deleted", document_id)
    await session.commit()
    return {"ok": True}


@router.post("/documents/{document_id}/retry", status_code=202)
async def retry_document(document_id: uuid.UUID, actor: ActorDep, session: SessionDep):
    require_write(actor)
    doc = (await session.execute(
        select(Document).where(Document.id == document_id, Document.organization_id == actor.organization_id).with_for_update()
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.status != "failed":
        raise HTTPException(409, "Only failed indexing jobs can be retried")
    doc.status = "queued"
    doc.error = None
    session.add(enqueue(actor.organization_id, "index_document", doc.id))
    audited(session, actor, "knowledge.retry", doc.id)
    await session.commit()
    return document_json(doc)


@router.get("/tickets")
async def list_tickets(actor: ActorDep, session: SessionDep):
    tickets = (await session.execute(
        select(Ticket).where(Ticket.organization_id == actor.organization_id)
        .order_by(Ticket.created_at.desc()).limit(100)
    )).scalars().all()
    return [ticket_json(ticket) for ticket in tickets]


@router.post("/tickets", status_code=202)
async def create_ticket(payload: TicketCreate, actor: ActorDep, session: SessionDep):
    require_write(actor)
    # Lock workspace row to serialize quota checks across API replicas.
    org = (await session.execute(select(Organization).where(Organization.id == actor.organization_id).with_for_update())).scalar_one()
    month = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    consumed = (await session.scalar(select(func.count()).select_from(Ticket).where(
        Ticket.organization_id == actor.organization_id, Ticket.created_at >= month
    ))) or 0
    if consumed >= quota_for(org.plan):
        raise HTTPException(402, "Monthly draft quota reached; upgrade the workspace plan")
    ticket = Ticket(
        organization_id=actor.organization_id, created_by=actor.user_id,
        requester_email=str(payload.requester_email).lower() if payload.requester_email else None,
        subject=payload.subject.strip(), question=payload.question.strip(),
    )
    session.add(ticket)
    await session.flush()
    session.add(enqueue(actor.organization_id, "draft_ticket", ticket.id))
    audited(session, actor, "ticket.created", ticket.id)
    await session.commit()
    return ticket_json(ticket, detail=True)


@router.post("/tickets/{ticket_id}/retry", status_code=202)
async def retry_ticket(ticket_id: uuid.UUID, actor: ActorDep, session: SessionDep):
    require_write(actor)
    ticket = (await session.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.organization_id == actor.organization_id).with_for_update()
    )).scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    if ticket.status != "failed":
        raise HTTPException(409, "Only failed tickets can be retried")
    ticket.status = "queued"
    ticket.error = None
    session.add(enqueue(actor.organization_id, "draft_ticket", ticket.id))
    audited(session, actor, "ticket.retry", ticket.id)
    await session.commit()
    return ticket_json(ticket, detail=True)


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: uuid.UUID, actor: ActorDep, session: SessionDep):
    ticket = (await session.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.organization_id == actor.organization_id))).scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    return ticket_json(ticket, detail=True)


@router.post("/tickets/{ticket_id}/decision")
async def decide_ticket(ticket_id: uuid.UUID, payload: TicketDecision, actor: ActorDep, session: SessionDep):
    require_write(actor)
    ticket = (await session.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.organization_id == actor.organization_id).with_for_update()
    )).scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    if ticket.status not in ("awaiting_approval", "needs_review"):
        raise HTTPException(409, "Ticket is not awaiting a decision")
    if payload.edited_draft:
        ticket.draft = payload.edited_draft.strip()
    if payload.decision == "approve" and not ticket.draft:
        raise HTTPException(400, "Cannot approve an empty draft")
    ticket.status = "approved" if payload.decision == "approve" else "rejected"
    ticket.approved_by = actor.user_id if payload.decision == "approve" else None
    ticket.approved_at = now() if payload.decision == "approve" else None
    audited(session, actor, "ticket.approved" if payload.decision == "approve" else "ticket.rejected", ticket.id, {"manually_edited": bool(payload.edited_draft)})
    await session.commit()
    return ticket_json(ticket, detail=True)


@router.get("/evaluations/cases")
async def list_cases(actor: ActorDep, session: SessionDep):
    cases = (await session.execute(
        select(EvaluationCase).where(EvaluationCase.organization_id == actor.organization_id)
        .order_by(EvaluationCase.created_at.desc()).limit(20)
    )).scalars().all()
    return [{"id": str(c.id), "question": c.question, "must_include": c.must_include, "expect_abstain": c.expect_abstain} for c in cases]


@router.post("/evaluations/cases", status_code=201)
async def create_case(payload: EvaluationCaseCreate, actor: ActorDep, session: SessionDep):
    require_write(actor)
    n = (await session.scalar(select(func.count()).select_from(EvaluationCase).where(EvaluationCase.organization_id == actor.organization_id))) or 0
    cap = 5 if actor.plan == "trial" else 20
    if n >= cap:
        raise HTTPException(409, f"Maximum {cap} evaluation cases on this plan")
    case = EvaluationCase(organization_id=actor.organization_id, **payload.model_dump())
    session.add(case)
    audited(session, actor, "evaluation.case_created", case.id)
    await session.commit()
    return {"id": str(case.id)}


@router.delete("/evaluations/cases/{case_id}")
async def delete_case(case_id: uuid.UUID, actor: ActorDep, session: SessionDep):
    require_write(actor)
    case = (await session.execute(select(EvaluationCase).where(EvaluationCase.id == case_id, EvaluationCase.organization_id == actor.organization_id))).scalar_one_or_none()
    if not case:
        raise HTTPException(404, "Case not found")
    await session.delete(case)
    audited(session, actor, "evaluation.case_deleted", case_id)
    await session.commit()
    return {"ok": True}


@router.get("/evaluations/runs")
async def list_runs(actor: ActorDep, session: SessionDep):
    runs = (await session.execute(
        select(EvaluationRun).where(EvaluationRun.organization_id == actor.organization_id)
        .order_by(EvaluationRun.created_at.desc()).limit(20)
    )).scalars().all()
    return [{
        "id": str(r.id), "status": r.status, "passed": r.passed, "total": r.total,
        "results": r.results, "error": r.error, "created_at": as_iso(r.created_at),
    } for r in runs]


@router.post("/evaluations/run", status_code=202)
async def launch_evaluation(actor: ActorDep, session: SessionDep):
    require_write(actor)
    cases = (await session.scalar(select(func.count()).select_from(EvaluationCase).where(EvaluationCase.organization_id == actor.organization_id))) or 0
    if not cases:
        raise HTTPException(400, "Add at least one evaluation case first")
    # Limit runs, so evaluation traffic cannot bypass plan controls indefinitely.
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    run_count = (await session.scalar(select(func.count()).select_from(EvaluationRun).where(
        EvaluationRun.organization_id == actor.organization_id, EvaluationRun.created_at >= today
    ))) or 0
    run_cap = 1 if actor.plan == "trial" else 3
    if run_count >= run_cap:
        raise HTTPException(429, f"Maximum {run_cap} evaluation runs per day on this plan")
    run = EvaluationRun(organization_id=actor.organization_id, total=cases)
    session.add(run)
    await session.flush()
    session.add(enqueue(actor.organization_id, "run_evaluation", run.id))
    audited(session, actor, "evaluation.started", run.id)
    await session.commit()
    return {"id": str(run.id), "status": run.status}


@router.get("/audit")
async def audit_log(actor: ActorDep, session: SessionDep):
    require_owner(actor)
    rows = (await session.execute(
        select(AuditEvent).where(AuditEvent.organization_id == actor.organization_id)
        .order_by(AuditEvent.created_at.desc()).limit(60)
    )).scalars().all()
    return [{"action": e.action, "entity_id": str(e.entity_id) if e.entity_id else None, "created_at": as_iso(e.created_at)} for e in rows]


@router.get("/ops/metrics")
async def operational_metrics(actor: ActorDep, session: SessionDep):
    require_owner(actor)
    rows = (await session.execute(
        select(Job.status, func.count()).where(Job.organization_id == actor.organization_id).group_by(Job.status)
    )).all()
    oldest = await session.scalar(
        select(func.min(Job.created_at)).where(Job.organization_id == actor.organization_id, Job.status.in_(["pending", "retry"]))
    )
    return {
        "jobs": {status: count for status, count in rows},
        "oldest_pending_at": as_iso(oldest),
        "requires_attention": sum(count for status, count in rows if status == "dead"),
    }
