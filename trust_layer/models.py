from pydantic import BaseModel
from typing import Optional


class ComplaintCreate(BaseModel):
    shop_id: str
    reason: str
    event_id: Optional[str] = None


class VerifyResponse(BaseModel):
    event_id: str
    shop_id: str
    item: str
    weight_g: float
    change_g: float
    timestamp: str
    event_hash: str
    tamper_check: str  # "ok" | "mismatch" | "not_found"


class ChainIntegrityResponse(BaseModel):
    valid: bool
    records_checked: Optional[int] = None
    broken_at_id: Optional[int] = None
    reason: Optional[str] = None
