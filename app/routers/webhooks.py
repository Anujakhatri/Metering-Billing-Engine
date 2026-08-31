import stripe
import os
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Subscription, Tenant, Plan, WebhookEvent
import uuid

router = APIRouter()
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # STEP 1: Verify signature — forged webhook must be rejected with 400
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid signature")

    # STEP 2: Deduplicate — replayed event must be processed only once
    existing = db.query(WebhookEvent).filter(WebhookEvent.stripe_event_id == event["id"]).first()
    if existing:
        return {"status": "already processed"}

    db.add(WebhookEvent(stripe_event_id=event["id"], type=event["type"]))
    db.commit()

    # STEP 3: Handle specific event types
    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        tenant_id = uuid.UUID(data["metadata"]["tenant_id"])
        _upsert_subscription(
            db, tenant_id,
            stripe_customer_id=data["customer"],
            stripe_subscription_id=data["subscription"],
            status="active",
            plan_name="pro",
        )

    elif event_type == "customer.subscription.updated":
        _update_subscription_status(db, data["id"], data["status"])

    elif event_type == "customer.subscription.deleted":
        _update_subscription_status(db, data["id"], "canceled")
        # also revert plan to "free" — your business rule

    return {"status": "processed"}


def _upsert_subscription(db, tenant_id, stripe_customer_id, stripe_subscription_id, status, plan_name):
    plan = db.query(Plan).filter(Plan.name == plan_name).first()
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if sub:
        sub.plan_id = plan.id
        sub.stripe_customer_id = stripe_customer_id
        sub.stripe_subscription_id = stripe_subscription_id
        sub.status = status
    else:
        sub = Subscription(
            tenant_id=tenant_id, plan_id=plan.id,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            status=status,
        )
        db.add(sub)
    db.commit()


def _update_subscription_status(db, stripe_subscription_id, status):
    sub = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == stripe_subscription_id
    ).first()
    if sub:
        sub.status = status
        db.commit()