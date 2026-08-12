"""风控告警 API (P4-L2)。

   POST /api/alerts/check         手动触发 3 个告警检查
   GET  /api/alerts               告警列表 (按状态过滤)
   POST /api/alerts/{id}/resolve  标记告警已处理
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.database import get_session
from app.models_risk import RiskAlert
from app.service.alert import run_all_alert_checks

router = APIRouter(prefix="/api/alerts", tags=["告警"])


def _alert_to_dict(a: RiskAlert, with_handler: bool = False) -> dict:
    base = {
        "alert_id": a.alert_id, "alert_type": a.alert_type, "alert_level": a.alert_level,
        "alert_title": a.alert_title, "alert_content": a.alert_content,
        "metric_name": a.metric_name,
        "metric_value": float(a.metric_value) if a.metric_value is not None else None,
        "threshold": float(a.threshold) if a.threshold is not None else None,
        "status": a.status,
    }
    if with_handler:
        base["handler"] = a.handler
        base["create_time"] = a.create_time
        base["resolve_time"] = a.resolve_time
    return base


@router.post("/check")
def api_check_alerts(db: Session = Depends(get_session)):
    """手动触发 3 个告警检查 (待审核积压 / 命中率突降 / 拒绝率过高)。"""
    new_alerts = run_all_alert_checks(db)
    db.commit()
    return {
        "checked_at": datetime.now().isoformat(),
        "triggered_count": len(new_alerts),
        "alerts": [_alert_to_dict(a) for a in new_alerts],
    }


@router.get("")
def api_list_alerts(
    status: str | None = Query(None, description="状态过滤: PENDING/HANDLING/RESOLVED/IGNORED"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_session),
):
    stmt = select(RiskAlert).order_by(desc(RiskAlert.create_time)).limit(limit)
    if status:
        stmt = stmt.where(RiskAlert.status == status)
    rows = list(db.scalars(stmt))
    return [_alert_to_dict(a, with_handler=True) for a in rows]


@router.post("/{alert_id}/resolve")
def api_resolve_alert(alert_id: int, handler: str = Query(...), db: Session = Depends(get_session)):
    alert = db.get(RiskAlert, alert_id)
    if not alert:
        raise HTTPException(404, "告警不存在")
    if alert.status == "RESOLVED":
        raise HTTPException(400, "告警已处理, 无需重复")
    alert.status = "RESOLVED"
    alert.handler = handler
    alert.resolve_time = datetime.now()
    db.commit()
    return {"alert_id": alert_id, "status": "RESOLVED", "handler": handler}
