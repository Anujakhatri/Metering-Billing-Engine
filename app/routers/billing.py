from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.meter_service import record_usage, DuplicateRequestError
from app.quota_service import check_quota, QuotaExceededError
from app.schemas import GenerateRequest, GenerateResponse
import uuid

router = APIRouter()

@router.post("/generate", response_model=GenerateResponse, status_code=201)
def generate(
    payload: GenerateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    tenant_id = payload.tenant_id

    # 1. Quota check FIRST
    try:
        check_quota(db, tenant_id, payload.usage_type, payload.quantity)
    except QuotaExceededError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    # 2. Idempotent record
    try:
        event = record_usage(
            db, tenant_id, payload.usage_type, payload.quantity,
            idempotency_key, payload.token_breakdown,
        )
        return GenerateResponse(event_id=event.id, quantity=event.quantity, duplicate=False)
    except DuplicateRequestError as e:
        return GenerateResponse(
            event_id=e.existing_event.id,
            quantity=e.existing_event.quantity,
            duplicate=True,
        )