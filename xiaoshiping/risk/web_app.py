"""制造业风控 Web 应用：驾驶舱、风险检查、案件管理、评估历史。"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.service.event import run_risk_check
from src import db
from src.features import FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "models" / "manufacturing_xgb_model.json"
METRICS_PATH = ROOT / "models" / "training_metrics.json"
app = FastAPI(title="制造业智能风控平台", version="0.3.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")


class RiskEventStatusUpdate(BaseModel):
    handled_status: str


class RiskCaseStatusUpdate(BaseModel):
    status: str


def page_context(request: Request, active_page: str, **extra: object) -> dict:
    return {"request": request, "active_page": active_page, **extra}


def model_metrics() -> dict:
    if not METRICS_PATH.exists():
        return {"available": False}
    metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    metrics["available"] = MODEL_PATH.exists()
    return metrics


@app.get("/", response_class=HTMLResponse)
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", page_context(request, "dashboard", summary=db.dashboard_summary(), events=db.risk_events(limit=8), metrics=model_metrics()))


@app.get("/events", response_class=HTMLResponse)
def events_page(request: Request):
    return templates.TemplateResponse(request, "events.html", page_context(request, "events", events=db.risk_events(limit=100)))


@app.get("/work-orders", response_class=HTMLResponse)
def work_orders_page(request: Request):
    return templates.TemplateResponse(request, "work_orders.html", page_context(request, "work_orders", work_orders=db.work_orders()))


@app.get("/cases", response_class=HTMLResponse)
def cases_page(request: Request):
    return templates.TemplateResponse(request, "cases.html", page_context(request, "cases", cases=db.risk_cases()))


@app.get("/assessments", response_class=HTMLResponse)
def assessments_page(request: Request):
    return templates.TemplateResponse(request, "assessments.html", page_context(request, "assessments", assessments=db.assessment_history()))


@app.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request):
    return templates.TemplateResponse(request, "rules.html", page_context(request, "rules", rules=db.rules()))


@app.get("/model", response_class=HTMLResponse)
def model_page(request: Request):
    return templates.TemplateResponse(request, "model.html", page_context(request, "model", metrics=model_metrics(), features=FEATURE_COLUMNS))


@app.get("/api/dashboard")
def api_dashboard():
    return {"summary": db.dashboard_summary(), "events": db.risk_events(limit=8), "metrics": model_metrics()}


@app.get("/api/risk-events")
def api_risk_events(status: str | None = None, decision: str | None = None):
    return {"items": db.risk_events(status=status, decision=decision)}


@app.put("/api/risk-events/{risk_event_id}/status")
def api_update_risk_event(risk_event_id: str, payload: RiskEventStatusUpdate):
    if payload.handled_status not in {"OPEN", "ACKED", "CLOSED"}:
        raise HTTPException(status_code=400, detail="handled_status 必须为 OPEN、ACKED 或 CLOSED")
    if not db.update_risk_event_status(risk_event_id, payload.handled_status):
        raise HTTPException(status_code=404, detail="风险事件不存在")
    return {"ok": True, "risk_event_id": risk_event_id, "handled_status": payload.handled_status}


@app.get("/api/cases")
def api_cases():
    return {"items": db.risk_cases()}


@app.put("/api/cases/{case_id}/status")
def api_update_case(case_id: str, payload: RiskCaseStatusUpdate):
    if payload.status not in {"PENDING", "IN_REVIEW", "CLOSED"}:
        raise HTTPException(status_code=400, detail="案件状态必须为 PENDING、IN_REVIEW 或 CLOSED")
    if not db.update_case_status(case_id, payload.status):
        raise HTTPException(status_code=404, detail="案件不存在")
    return {"ok": True, "case_id": case_id, "status": payload.status}


@app.get("/api/assessments")
def api_assessments():
    return {"items": db.assessment_history()}


@app.post("/api/work-orders/{work_order_id}/assess")
def api_assess_work_order(work_order_id: str):
    try:
        return run_risk_check(work_order_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/health")
def health():
    return {"status": "ok", "database": bool(db.fetch_one("SELECT 1 AS connected")), "model": MODEL_PATH.exists()}

class BusinessDataUpdate(BaseModel):
    changes: dict[str, object]
    recheck: bool = True


@app.get("/data-management", response_class=HTMLResponse)
def data_management_page(request: Request):
    return templates.TemplateResponse(request, "data_management.html", page_context(request, "data_management"))


@app.get("/api/business-data")
def api_business_data():
    return {"items": db.business_data()}


@app.put("/api/business-data/{entity}/{record_id}")
def api_update_business_data(entity: str, record_id: str, payload: BusinessDataUpdate):
    try:
        updated = db.update_business_record(entity, record_id, payload.changes)
        if not updated:
            raise HTTPException(status_code=404, detail="业务记录不存在")
        affected_orders = db.affected_work_orders(entity, record_id)
        assessments = [run_risk_check(work_order_id) for work_order_id in affected_orders] if payload.recheck else []
        return {"ok": True, "entity": entity, "record_id": record_id, "affected_work_orders": affected_orders, "assessments": assessments}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error