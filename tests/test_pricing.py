import pytest
from app.pricing_service import calculate_cost, get_tenant_usage_rollup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Tenant, Plan, Subscription, UsageEvent
import uuid

# Test DB Setup
TEST_DATABASE_URL = "sqlite:///./test_pricing.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

def test_pricing_pure_input():
    """Case a: Pure input tokens only."""
    usage = {"input_tokens": 1000}
    # 1000 * 150 = 150,000 micro-cents
    assert calculate_cost(usage) == 150_000

def test_pricing_mixed_input_cached():
    """Case b: Mixed input + cached_input tokens."""
    usage = {"input_tokens": 1000, "cached_input_tokens": 1000}
    # 1000*150 + 1000*75 = 150,000 + 75,000 = 225,000
    assert calculate_cost(usage) == 225_000

    # Verify it's lower than if all were fresh
    all_fresh = {"input_tokens": 2000}
    assert calculate_cost(usage) < calculate_cost(all_fresh)

def test_pricing_output_reasoning():
    """Case c: Output tokens + reasoning tokens."""
    usage = {"output_tokens": 1000, "reasoning_tokens": 1000}
    # 1000*600 + 1000*600 = 1,200,000 micro-cents
    assert calculate_cost(usage) == 1_200_000

def test_pricing_realistic_mixed():
    """Case d: A realistic mixed request."""
    usage = {
        "input_tokens": 1000,
        "cached_input_tokens": 1000,
        "output_tokens": 1000,
        "reasoning_tokens": 1000
    }
    # 150k + 75k + 600k + 600k = 1,425,000
    assert calculate_cost(usage) == 1_425_000

def test_pricing_zero_usage():
    """Case e: Zero-usage tenant."""
    assert calculate_cost({}) == 0

def test_rollup_calculation(db):
    """Case f: Seed events -> verify cost in cents."""
    tenant = Tenant(name="Cost Tenant")
    db.add(tenant)
    db.commit()

    plan = Plan(name="pro", api_call_limit=10000, ai_token_limit=100_000_000, price_cents=2000)
    db.add(plan)
    db.commit()

    sub = Subscription(tenant_id=tenant.id, plan_id=plan.id, status="active")
    db.add(sub)
    db.commit()

    # Seed usage events that total 10M mixed tokens
    # Total micro-cents for 1M mixed = 1,425,000.
    # For 10M = 14,250,000 micro-cents = 14 cents.
    # We'll seed 10 events, each with 1M tokens of each type.
    for i in range(10):
        event = UsageEvent(
            tenant_id=tenant.id,
            type="ai_tokens",
            quantity=4_000_000, # 1M * 4
            idempotency_key=f"evt-{i}",
            event_metadata={
                "input_tokens": 1_000_000,
                "cached_input_tokens": 1_000_000,
                "output_tokens": 1_000_000,
                "reasoning_tokens": 1_000_000,
            }
        )
        db.add(event)
    db.commit()

    rollup = get_tenant_usage_rollup(db, tenant.id, "ai_tokens")

    # Used = 10 * 4M = 40,000,000
    assert rollup["used"] == 40_000_000
    # Limit = 100,000,000
    assert rollup["limit"] == 100_000_000
    # Cost = (10 * 1,425,000,000) // 1,000,000 = 14,250,000,000 // 1,000,000 = 14250 cents
    assert rollup["cost"] == 14250
