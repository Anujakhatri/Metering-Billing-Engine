import pytest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Tenant, Plan, Subscription, UsageEvent
from app.meter_service import record_usage
from app.quota_service import check_quota, QuotaExceededError
from app.routers.billing import generate
from fastapi.testclient import TestClient
from app.main import app
from app.schemas import GenerateRequest
import sqlalchemy

# Test DB Setup
TEST_DATABASE_URL = "sqlite:///./test_metering.db"
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

@pytest.fixture
def client(db):
    from app.main import app as fastapi_app
    from app.database import get_db

    def override_get_db():
        try:
            yield db
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = override_get_db
    client = TestClient(fastapi_app)
    yield client
    fastapi_app.dependency_overrides.clear()

def setup_tenant_with_plan(db, limit=1000):
    tenant = Tenant(name="Test Tenant")
    db.add(tenant)
    db.commit()

    plan = Plan(name="Test Plan", api_call_limit=limit, ai_token_limit=limit)
    db.add(plan)
    db.commit()

    sub = Subscription(tenant_id=tenant.id, plan_id=plan.id, status="active")
    db.add(sub)
    db.commit()
    return tenant

def test_idempotency_single_row(db):
    """Condition 1: Submitting the same idempotency key twice results in exactly ONE row."""
    tenant = setup_tenant_with_plan(db)
    key = "idempotency-123"

    # First attempt
    record_usage(db, tenant.id, "api_call", 1, key)
    db.commit()

    # Second attempt (same key)
    try:
        record_usage(db, tenant.id, "api_call", 1, key)
        db.commit()
    except Exception:
        pass # record_usage raises DuplicateRequestError, which is expected

    count = db.query(UsageEvent).filter(UsageEvent.idempotency_key == key).count()
    assert count == 1

def test_quota_exactly_at_limit(db, client):
    """Condition 2: Request that brings usage from 999 -> 1000 is ALLOWED."""
    tenant = setup_tenant_with_plan(db, limit=1000)

    # Pre-fill to 999
    for i in range(999):
        record_usage(db, tenant.id, "api_call", 1, f"init-{i}")
    db.commit()

    # Request 1 more (1000/1000)
    response = client.post(
        "/billing/generate",
        json={"tenant_id": str(tenant.id), "usage_type": "api_call", "quantity": 1},
        headers={"Idempotency-Key": "final-one"}
    )
    assert response.status_code == 201

def test_quota_exceeded(db, client):
    """Condition 3: Request that brings usage from 1000 -> 1001 is REJECTED with 429."""
    tenant = setup_tenant_with_plan(db, limit=1000)

    # Pre-fill to 1000
    for i in range(1000):
        record_usage(db, tenant.id, "api_call", 1, f"init-{i}")
    db.commit()

    # Request 1 more (1001/1000)
    response = client.post(
        "/billing/generate",
        json={"tenant_id": str(tenant.id), "usage_type": "api_call", "quantity": 1},
        headers={"Idempotency-Key": "too-many"}
    )
    assert response.status_code == 429

def test_idempotent_retry_double_counting(db, client):
    """
    Edge Case: Quota check on retry must NOT double-count the request.
    If usage is 999, request 1 unit (key K1) -> Allowed (1000).
    If retry request 1 unit (key K1) -> Should be Allowed (because it's the same request).
    If not handled, check_quota will see 1000 + 1 > 1000 and return 429.
    """
    tenant = setup_tenant_with_plan(db, limit=1000)

    # Pre-fill to 999
    for i in range(999):
        record_usage(db, tenant.id, "api_call", 1, f"init-{i}")
    db.commit()

    key = "retry-key-123"

    # First attempt: 999 -> 1000. Should be ALLOWED.
    response1 = client.post(
        "/billing/generate",
        json={"tenant_id": str(tenant.id), "usage_type": "api_call", "quantity": 1},
        headers={"Idempotency-Key": key}
    )
    assert response1.status_code == 201

    # Second attempt (Retry): Usage is now 1000.
    # Request 1 unit (same key).
    # If double-counting happens, this will be 429.
    response2 = client.post(
        "/billing/generate",
        json={"tenant_id": str(tenant.id), "usage_type": "api_call", "quantity": 1},
        headers={"Idempotency-Key": key}
    )

    # This is the critical assertion. It should be 201 (duplicate=True), not 429.
    assert response2.status_code == 201, f"Retry was rejected with {response2.status_code} (Double-counting bug!)"
