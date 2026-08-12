from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.ml.model import model_metrics
from app.schemas import (
    AgentChatRequest,
    AgentClearRequest,
    BlacklistCreate,
    BlacklistRemoveRequest,
    InboundRiskRequest,
    PayoutRiskRequest,
    RiskWorkbenchRequest,
)
from app.services.assistant import assistant_status, chat, clear_session
from app.services.blacklist import list_blacklist, remove_blacklist, upsert_blacklist
from app.services.dashboard import (
    case_queue,
    dashboard_stats,
    recent_inbounds,
    recent_payouts,
    risk_trend,
    rule_catalog,
)
from app.services.risk_service import assess_business_id, assess_inbound, assess_payout


router = APIRouter(prefix="/api")


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "pingpong", "model_loaded": bool(model_metrics())}


@router.get("/dashboard/stats")
def get_dashboard_stats(db: Session = Depends(get_db)) -> dict:
    return dashboard_stats(db)


@router.get("/dashboard/trend")
def get_risk_trend(db: Session = Depends(get_db)) -> list[dict]:
    return risk_trend(db)


@router.get("/inbounds")
def get_inbounds(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db)) -> list[dict]:
    return recent_inbounds(db, limit)


@router.get("/payouts")
def get_payouts(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db)) -> list[dict]:
    return recent_payouts(db, limit)


@router.get("/rules")
def get_rules(db: Session = Depends(get_db)) -> list[dict]:
    return rule_catalog(db)


@router.get("/cases")
def get_cases(limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db)) -> list[dict]:
    return case_queue(db, limit)


@router.get("/model/metrics")
def get_model_metrics() -> dict:
    metrics = model_metrics()
    if not metrics:
        raise HTTPException(status_code=503, detail="model has not been trained")
    return metrics


@router.post("/risk/check")
def risk_check(payload: InboundRiskRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return assess_inbound(db, payload.inbound_payment_id, payload.persist)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/risk/check-payout")
def risk_check_payout(payload: PayoutRiskRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return assess_payout(db, payload.payout_id, payload.persist)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/risk/check-workbench")
def risk_check_workbench(payload: RiskWorkbenchRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return assess_business_id(db, payload.event_type, payload.business_id, payload.persist)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/blacklist")
def get_blacklist(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    entity_type: str | None = None,
    status: str = Query("ACTIVE", pattern="^(ACTIVE|EXPIRED|REMOVED|ALL)$"),
    q: str | None = Query(default=None, max_length=255),
    db: Session = Depends(get_db),
) -> dict:
    return list_blacklist(db, page, page_size, entity_type, status, q)


@router.post("/blacklist", status_code=201)
def add_blacklist(payload: BlacklistCreate, db: Session = Depends(get_db)) -> dict:
    return upsert_blacklist(db, payload)


@router.delete("/blacklist/{blacklist_id}")
def delete_blacklist(
    blacklist_id: int,
    payload: BlacklistRemoveRequest,
    db: Session = Depends(get_db),
) -> dict:
    if not remove_blacklist(db, blacklist_id, payload):
        raise HTTPException(status_code=404, detail="blacklist entry not found or already removed")
    return {"detail": "removed", "blacklist_id": blacklist_id}


@router.get("/agent/status")
def get_agent_status() -> dict:
    return assistant_status()


@router.post("/agent/chat")
def agent_chat(payload: AgentChatRequest, db: Session = Depends(get_db)) -> dict:
    return chat(db, payload.message, payload.session_id)


@router.post("/agent/clear")
def agent_clear(payload: AgentClearRequest) -> dict:
    return {"cleared": clear_session(payload.session_id)}
