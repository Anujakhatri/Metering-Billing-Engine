from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import UsageEvent, Subscription
from datetime import datetime, timezone
import uuid

class QuotaExceededError(Exception):
    def __init__(self, message: str, status_code: int):
        self.message = message
        self.status_code = status_code  # 429 or 402

def check_quota(db: Session, tenant_id: uuid.UUID, usage_type: str, requested_qty: int, idempotency_key: str | None = None):
    """
    Raises QuotaExceededError if adding requested_qty would exceed the plan limit.
    Boundary rule: usage can go UP TO the limit exactly. Anything that would
    push it OVER the limit is rejected.

    If idempotency_key is provided and already exists, the request is allowed
    since it's a retry and usage was already counted.
    """
    if idempotency_key:
        existing = db.query(UsageEvent).filter(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.idempotency_key == idempotency_key
        ).first()
        if existing:
            return  # Already counted, allow the retry

    subscription = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not subscription:
        raise QuotaExceededError("No active subscription found", 402)

    if subscription.status != "active":
        raise QuotaExceededError(f"Subscription status is '{subscription.status}' — payment required", 402)

    plan = subscription.plan
    limit = plan.api_call_limit if usage_type == "api_call" else plan.ai_token_limit

    # Sum this month's usage of this type for this tenant
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    current_usage = (
        db.query(func.coalesce(func.sum(UsageEvent.quantity), 0))
        .filter(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.type == usage_type,
            UsageEvent.created_at >= month_start,
        )
        .scalar()
    )

    if current_usage + requested_qty > limit:
        raise QuotaExceededError(
            f"Quota exceeded: {current_usage}/{limit} {usage_type} used this month. "
            f"Requested {requested_qty} more would exceed your plan limit.",
            429,
        )