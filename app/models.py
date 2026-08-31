import uuid
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
class Plan(Base):
    __tablename__ = "plans"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String,unique=True, nullable=False)
    api_call_limit = Column(Integer, nullable=False)
    ai_token_limit = Column(Integer, nullable=False)
    price_cents = Column(Integer, nullable=False, default=0)
    
class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    plan = relationship("Plan")

class UsageEvent(Base):
    __tablename__ = "usage_events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    type = Column(String, nullable=False)          # "api_call" | "ai_tokens"
    quantity = Column(Integer, nullable=False)
    idempotency_key = Column(String, nullable=False)
    event_metadata = Column(JSON, nullable=True)    # token breakdown
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_tenant_idempotency"),
    )