import stripe
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Tenant, Plan, Subscription
from pydantic import BaseModel
import uuid

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
router = APIRouter()

class CheckoutRequest(BaseModel):
    tenant_id: uuid.UUID
    plan_name: str  # "pro"

@router.post("/checkout")
def create_checkout(payload: CheckoutRequest, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first()
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    plan = db.query(Plan).filter(Plan.name == payload.plan_name).first()
    if not plan or not plan.stripe_price_id:
        raise HTTPException(400, "Plan not found or missing Stripe price")

    # Reuse existing Stripe customer if we already have one
    subscription = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).first()
    stripe_customer_id = subscription.stripe_customer_id if subscription else None

    if not stripe_customer_id:
        customer = stripe.Customer.create(
            name=tenant.name,
            metadata={"tenant_id": str(tenant.id)},
        )
        stripe_customer_id = customer.id

    session = stripe.checkout.Session.create(
        customer=stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
        mode="subscription",
        success_url="http://localhost:8000/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="http://localhost:8000/cancel",
        metadata={"tenant_id": str(tenant.id)},  # backup — also on session
    )
    return {"checkout_url": session.url}