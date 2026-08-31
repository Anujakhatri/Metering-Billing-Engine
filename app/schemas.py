from pydantic import BaseModel, Field
from typing import Optional, Dict
import uuid

class GenerateRequest(BaseModel):
    tenant_id: uuid.UUID
    usage_type: str = Field(..., description="api_call | ai_tokens")
    quantity: int
    token_breakdown: Optional[Dict[str, int]] = None

class GenerateResponse(BaseModel):
    event_id: uuid.UUID
    quantity: int
    duplicate: bool
