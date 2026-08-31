from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models import UsageEvent
import uuid

class DuplicateRequestError(Exception):
    """Raised when idempotency key already exists — caller should return the original result."""
    def __init__(self, existing_event: UsageEvent):
        self.existing_event = existing_event

def record_usage(
    db: Session,
    tenant_id: uuid.UUID,
    usage_type: str,
    quantity: int,
    idempotency_key: str,
    metadata: dict | None = None,
) -> UsageEvent:
    """
    Records a usage event exactly once per (tenant_id, idempotency_key).
    If the key was already used, raises DuplicateRequestError with the
    ORIGINAL event — the caller returns that instead of creating a new one.
    """
    # Step 1: check if this exact key already recorded for this tenant
    existing = (
        db.query(UsageEvent)
        .filter(
            UsageEvent.tenant_id == tenant_id,
            UsageEvent.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        raise DuplicateRequestError(existing)

    # Step 2: try to insert. Even if two requests race past the check above,
    # the DB UNIQUE constraint catches the second one here.
    event = UsageEvent(
        tenant_id=tenant_id,
        type=usage_type,
        quantity=quantity,
        idempotency_key=idempotency_key,
        event_metadata=metadata,
    )
    db.add(event)
    try:
        db.commit()
        db.refresh(event)
        return event
    except IntegrityError:
        # Race condition: another request inserted first between our check and commit
        db.rollback()
        existing = (
            db.query(UsageEvent)
            .filter(
                UsageEvent.tenant_id == tenant_id,
                UsageEvent.idempotency_key == idempotency_key,
            )
            .first()
        )
        raise DuplicateRequestError(existing)