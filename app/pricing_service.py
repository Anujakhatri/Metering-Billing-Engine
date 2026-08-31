from config.pricing_config import TOKEN_RATES, PLAN_COSTS, PLAN_QUOTAS
from sqlalchemy.orm import Session
from app.models import UsageEvent, Subscription, Plan
from sqlalchemy import func
import uuid

def calculate_cost(usage: dict) -> int:
    """
    Pure function to calculate total cost in micro-cents.
    Input: usage dict with token counts.
    Output: total cost in micro-cents.
    """
    total_micro_cents = 0

    # Input tokens
    total_micro_cents += usage.get("input_tokens", 0) * TOKEN_RATES["input_tokens"]

    # Cached input tokens
    total_micro_cents += usage.get("cached_input_tokens", 0) * TOKEN_RATES["cached_input_tokens"]

    # Output tokens
    total_micro_cents += usage.get("output_tokens", 0) * TOKEN_RATES["output_tokens"]

    # Reasoning tokens (Billed as output)
    total_micro_cents += usage.get("reasoning_tokens", 0) * TOKEN_RATES["reasoning_tokens"]

    return total_micro_cents

def get_tenant_usage_rollup(db: Session, tenant_id: uuid.UUID, usage_type: str):
    """
    Aggregates a tenant's usage for the current billing period.
    Returns { "used": int, "limit": int, "cost": int }
    'cost' is returned in cents.
    """
    # 1. Get current plan limit
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if not sub:
        return {"used": 0, "limit": 0, "cost": 0}

    plan = sub.plan
    # Determine limit based on usage_type
    limit = plan.api_call_limit if usage_type == "api_call" else plan.ai_token_limit

    # 2. Sum usage for current month
    # Simplified: sum all for now, or add date filter
    total_used = db.query(func.coalesce(func.sum(UsageEvent.quantity), 0))\
        .filter(UsageEvent.tenant_id == tenant_id, UsageEvent.type == usage_type)\
        .scalar() or 0

    # 3. Calculate Cost
    cost_cents = 0
    if usage_type == "ai_tokens":
        # Aggregate detailed token counts from event_metadata
        # metadata: {"input_tokens": X, "cached_input_tokens": Y, ...}
        metadata_sum = db.query(UsageEvent.event_metadata)\
            .filter(UsageEvent.tenant_id == tenant_id, UsageEvent.type == usage_type)\
            .all()

        combined_usage = {
            "input_tokens": 0,
            "cached_input_tokens": 0,
            "output_tokens": 0,
            "reasoning_tokens": 0
        }

        for (meta,) in metadata_sum:
            if meta:
                for k, v in meta.items():
                    if k in combined_usage:
                        combined_usage[k] += v

        # Calculate in micro-cents then convert to cents
        micro_cents = calculate_cost(combined_usage)
        cost_cents = micro_cents // 1_000_000
    elif usage_type == "api_call":
        # For API calls, we might have a fixed cost per call or just monthly plan
        # As per requirements, focus is on AI token pricing.
        # We'll treat API calls as free once plan is paid.
        cost_cents = 0

    return {
        "used": total_used,
        "limit": limit,
        "cost": cost_cents
    }
