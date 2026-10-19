"""Optional Stripe Checkout and signed webhook handler. No payment credentials stored here."""
import asyncio
import uuid

import stripe
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionFactory
from app.dependencies import ActorDep, SessionDep, require_owner
from app.models import Organization, StripeEvent
from app.schemas import CheckoutRequest

router = APIRouter(prefix="/billing", tags=["billing"])


def billing_ready() -> bool:
    s = get_settings()
    return bool(s.stripe_secret_key and s.stripe_webhook_secret and s.stripe_price_starter and s.stripe_price_growth)


def quota_for(plan: str) -> int:
    return {"trial": 25, "starter": 500, "growth": 5000}.get(plan, 25)


@router.get("")
async def billing_state(actor: ActorDep):
    s = get_settings()
    return {
        "plan": actor.plan, "monthly_ticket_limit": quota_for(actor.plan),
        "checkout_enabled": billing_ready(),
        "available_plans": [{"key": "starter", "tickets": 500}, {"key": "growth", "tickets": 5000}],
    }


@router.post("/checkout")
async def checkout(payload: CheckoutRequest, actor: ActorDep, session: SessionDep):
    require_owner(actor)
    if not billing_ready():
        raise HTTPException(503, "Billing not configured; contact support")
    s = get_settings()
    stripe.api_key = s.stripe_secret_key
    org = (await session.execute(select(Organization).where(Organization.id == actor.organization_id))).scalar_one()
    price_id = s.stripe_price_starter if payload.plan == "starter" else s.stripe_price_growth
    args = dict(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        client_reference_id=str(org.id),
        subscription_data={"metadata": {"workspace_id": str(org.id)}},
        success_url=s.app_origin + "/?billing=success",
        cancel_url=s.app_origin + "/?billing=canceled",
    )
    if org.stripe_customer_id:
        args["customer"] = org.stripe_customer_id
    else:
        args["customer_email"] = actor.email
    result = await asyncio.to_thread(stripe.checkout.Session.create, **args)
    return {"url": result.url}


@router.post("/portal")
async def portal(actor: ActorDep, session: SessionDep):
    require_owner(actor)
    if not billing_ready():
        raise HTTPException(503, "Billing not configured")
    stripe.api_key = get_settings().stripe_secret_key
    org = (await session.execute(select(Organization).where(Organization.id == actor.organization_id))).scalar_one()
    if not org.stripe_customer_id:
        raise HTTPException(400, "No billing account yet")
    result = await asyncio.to_thread(
        stripe.billing_portal.Session.create,
        customer=org.stripe_customer_id,
        return_url=get_settings().app_origin + "/",
    )
    return {"url": result.url}


async def ingest_webhook(raw: bytes, signature: str | None) -> str:
    s = get_settings()
    if not billing_ready():
        raise HTTPException(503, "Billing not configured")
    if not signature:
        raise HTTPException(400, "Missing Stripe signature")
    try:
        event = stripe.Webhook.construct_event(raw, signature, s.stripe_webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise HTTPException(400, "Invalid Stripe webhook") from exc

    async with SessionFactory() as session:
        # Database transaction is the deduplication boundary. Stripe retries on 5xx.
        duplicate = (await session.execute(select(StripeEvent).where(StripeEvent.id == event["id"]))).scalar_one_or_none()
        if duplicate:
            return "duplicate"
        event_created = int(event.get("created", 0))
        data = event["data"]["object"]
        etype = event["type"]
        org = None
        if etype == "checkout.session.completed" and data.get("mode") == "subscription":
            ref = data.get("client_reference_id")
            try:
                org_uuid = uuid.UUID(ref)
            except (ValueError, TypeError):
                org_uuid = None
            if org_uuid:
                org = (await session.execute(select(Organization).where(Organization.id == org_uuid).with_for_update())).scalar_one_or_none()
                if org:
                    customer_id = data.get("customer")
                    if customer_id and (org.stripe_customer_id is None or org.stripe_customer_id == customer_id):
                        org.stripe_customer_id = customer_id
        elif etype in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
            customer = data.get("customer")
            org = (await session.execute(
                select(Organization).where(Organization.stripe_customer_id == customer).with_for_update()
            )).scalar_one_or_none()
            # A subscription.created event may arrive before checkout.completed.
            # Subscription metadata is set server-side during Checkout creation.
            if org is None and data.get("metadata", {}).get("workspace_id"):
                try:
                    from_metadata = uuid.UUID(data["metadata"]["workspace_id"])
                except (TypeError, ValueError):
                    from_metadata = None
                if from_metadata:
                    candidate = (await session.execute(
                        select(Organization).where(Organization.id == from_metadata).with_for_update()
                    )).scalar_one_or_none()
                    if candidate and (candidate.stripe_customer_id is None or candidate.stripe_customer_id == customer):
                        org = candidate
                        org.stripe_customer_id = customer
            if org and event_created >= org.billing_event_created:
                status = data.get("status")
                items = data.get("items", {}).get("data", [])
                price_ids = {item.get("price", {}).get("id") for item in items}
                if etype == "customer.subscription.deleted" or status not in ("active", "trialing"):
                    org.plan = "trial"
                elif s.stripe_price_growth in price_ids:
                    org.plan = "growth"
                elif s.stripe_price_starter in price_ids:
                    org.plan = "starter"
                else:
                    org.plan = "trial"
                org.stripe_subscription_id = data.get("id")
                org.billing_event_created = event_created
        session.add(StripeEvent(id=event["id"], event_created=event_created))
        await session.commit()
    return "processed"
