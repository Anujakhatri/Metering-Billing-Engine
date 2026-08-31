from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.meter_service import record_usage, DuplicateRequestError
from app.quota_service import check_quota, QuotaExceededError
from app.pricing_service import get_tenant_usage_rollup
from app.schemas import GenerateRequest, GenerateResponse
import uuid

router = APIRouter()

@router.get("/usage/{usage_type}")
def get_usage(usage_type: str, tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    if usage_type not in ["api_call", "ai_tokens"]:
        raise HTTPException(400, "Invalid usage type. Must be 'api_call' or 'ai_tokens'")

    rollup = get_tenant_usage_rollup(db, tenant_id, usage_type)
    return rollup

@router.post("/generate", response_model=GenerateResponse, status_code=201)

def generate(
    payload: GenerateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    tenant_id = payload.tenant_id

    # 1. Quota check FIRST
    try:
        check_quota(db, tenant_id, payload.usage_type, payload.quantity, idempotency_key)
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