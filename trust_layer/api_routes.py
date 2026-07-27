"""
New FastAPI routes for the trust layer. Mount this router from the
existing api.py with:

    from trust_layer.api_routes import router as trust_router
    app.include_router(trust_router, prefix="/trust")

No existing PDS routes are modified.
"""
from fastapi import APIRouter, HTTPException, Query

from . import hash_chain, qr_service, tigergraph_client as tg, sync
from .models import ComplaintCreate, VerifyResponse, ChainIntegrityResponse

router = APIRouter()


@router.get("/verify/{event_id}", response_model=VerifyResponse)
def verify_event(event_id: str):
    """Beneficiary/auditor-facing: recompute the event's position in the
    hash chain and confirm nothing was altered after the fact."""
    record = hash_chain.verify_single_event(event_id)
    if not record:
        raise HTTPException(status_code=404, detail="Event not found")

    chain_status = hash_chain.verify_chain()
    tamper_check = "ok" if chain_status.get("valid") else "mismatch"

    return VerifyResponse(**record, tamper_check=tamper_check)


@router.get("/verify-chain", response_model=ChainIntegrityResponse)
def verify_chain_integrity():
    """Full-chain audit: walk every event and confirm the hash chain is intact."""
    return ChainIntegrityResponse(**hash_chain.verify_chain())


@router.get("/qr/{event_id}")
def get_event_qr(event_id: str):
    record = hash_chain.verify_single_event(event_id)
    if not record:
        raise HTTPException(status_code=404, detail="Event not found")
    return qr_service.generate_event_qr(event_id, record["event_hash"])


@router.get("/analytics/anomalous-shops")
def anomalous_shops(threshold: float = Query(0.5, ge=0.0, le=1.0)):
    try:
        return {"shops": tg.get_anomalous_shops(threshold)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"TigerGraph unavailable: {exc}")


@router.get("/analytics/repeat-offenders")
def repeat_offenders(top_n: int = Query(10, ge=1, le=100)):
    try:
        return {"shops": tg.get_repeat_offenders(top_n)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"TigerGraph unavailable: {exc}")


@router.get("/analytics/regional-clusters")
def regional_clusters(region: str):
    try:
        return {"region": region, "data": tg.get_regional_clusters(region)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"TigerGraph unavailable: {exc}")


@router.get("/analytics/suspicious-beneficiaries")
def suspicious_beneficiaries(distinct_shop_threshold: int = Query(3, ge=2, le=20)):
    try:
        return {"beneficiaries": tg.get_suspicious_beneficiaries(distinct_shop_threshold)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"TigerGraph unavailable: {exc}")


@router.get("/batch/{batch_id}/journey")
def batch_journey(batch_id: str):
    try:
        return {"batch_id": batch_id, "journey": tg.get_batch_journey(batch_id)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"TigerGraph unavailable: {exc}")


@router.post("/complaints")
def create_complaint(complaint: ComplaintCreate):
    complaint_id = sync.on_complaint(
        shop_id=complaint.shop_id, reason=complaint.reason, event_id=complaint.event_id,
    )
    return {"complaint_id": complaint_id, "status": "recorded"}
