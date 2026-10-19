from typing import Annotated
import uuid

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Membership, Organization, User
from app.security import Actor, check_csrf, decode_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_actor(
    request: Request,
    session: SessionDep,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> Actor:
    token = request.cookies.get("groundreply_session")
    if not token:
        raise HTTPException(status_code=401, detail="Sign in required")
    claims = decode_session(token)
    row = (
        await session.execute(
            select(User, Membership, Organization)
            .join(Membership, Membership.user_id == User.id)
            .join(Organization, Organization.id == Membership.organization_id)
            .where(User.id == uuid.UUID(claims["sub"]))
            .order_by(Membership.id)
            .limit(1)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=401, detail="User no longer belongs to a workspace")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_csrf(claims, x_csrf_token)
    user, membership, org = row
    return Actor(user.id, org.id, user.email, org.name, membership.role, org.plan, claims)


ActorDep = Annotated[Actor, Depends(get_actor)]


def require_write(actor: Actor) -> None:
    if actor.role not in ("owner", "agent"):
        raise HTTPException(status_code=403, detail="Read-only workspace role")


def require_owner(actor: Actor) -> None:
    if actor.role != "owner":
        raise HTTPException(status_code=403, detail="Workspace owner access required")
