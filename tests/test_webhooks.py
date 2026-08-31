import pytest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Tenant, Plan, Subscription, WebhookEvent
from app.routers.webhooks import router as webhook_router
from fastapi.testclient import TestClient
from fastapi import FastAPI, Depends
from app.database import get_db
import stripe
from unittest.mock import patch, MagicMock

# Test DB Setup
TEST_DATABASE_URL = "sqlite:///./test_webhooks.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI()
app.include_router(webhook_router)

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
    from app.database import get_db
    def override_get_db():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

def setup_tenant_with_pro_plan(db):
    tenant = Tenant(name="Test Tenant")
    db.add(tenant)
    db.commit()

    plan = Plan(name="pro", api_call_limit=1000, ai_token_limit=1000, price_cents=2000)
    db.add(plan)
    db.commit()
    return tenant

def test_webhook_bad_signature(client, db):
    """PART 2a: Bad signature should return 400 and not change DB."""
    tenant = setup_tenant_with_pro_plan(db)

    with patch("stripe.Webhook.construct_event") as mock_construct:
        # Fixed SignatureVerificationError arguments
        mock_construct.side_effect = stripe.error.SignatureVerificationError("Invalid signature", "invalid_sig")

        response = client.post(
            "/webhooks/stripe",
            content=b"invalid payload",
            headers={"stripe-signature": "invalid_sig"}
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid signature"

        sub = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).first()
        assert sub is None

def test_webhook_duplicate_event_id(client, db):
    """PART 2b: Duplicate event_id should be detected and not processed twice."""
    tenant = setup_tenant_with_pro_plan(db)
    event_id = "evt_test_123"

    mock_event = {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_test_1",
                "subscription": "sub_test_1",
                "metadata": {"tenant_id": str(tenant.id)}
            }
        }
    }

    with patch("stripe.Webhook.construct_event") as mock_construct:
        mock_construct.return_value = mock_event

        response1 = client.post(
            "/webhooks/stripe",
            content=b"payload",
            headers={"stripe-signature": "valid_sig"}
        )
        assert response1.status_code == 200
        assert response1.json()["status"] == "processed"

        sub = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).first()
        assert sub is not None
        assert sub.status == "active"

        response2 = client.post(
            "/webhooks/stripe",
            content=b"payload",
            headers={"stripe-signature": "valid_sig"}
        )
        assert response2.status_code == 200
        assert response2.json()["status"] == "already processed"

        sub_count = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).count()
        assert sub_count == 1
