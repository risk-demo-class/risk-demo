"""告警系统 / 操作审计 / 调度器 测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal, engine
from app.main import app
from app.models_risk import RiskActionLog, RiskAlert
from app.scheduler import _run_once, is_running, start_scheduler, stop_scheduler
from app.service.alert import check_and_alert, run_all_alert_checks
from app.service.action_log import record_action


def test_ddl_new_tables_exist():
    with engine.connect() as c:
        tables = {r[0] for r in c.execute(text("SHOW TABLES"))}
    assert {"risk_alert", "risk_action_log"} <= tables
    with engine.connect() as c:
        cols = [r[0] for r in c.execute(text("SHOW COLUMNS FROM risk_assessment"))]
    assert "ml_score" in cols and "ml_decision" in cols


def test_check_and_alert_writes_row():
    with SessionLocal() as db:
        alert = check_and_alert(
            db, "BUSINESS", "P1", "测试告警", "测试内容",
            metric_name="pending_case_count", metric_value=99.0, threshold=50.0,
        )
        assert alert.status == "PENDING"
        assert alert.alert_type == "BUSINESS"
        db.rollback()  # 不污染数据


def test_record_action_writes_row():
    with SessionLocal() as db:
        record_action(
            db, operator="tester", action_type="TOGGLE_RULE", target_type="rule",
            target_id="R999", before_value={"enabled": True},
            after_value={"enabled": False}, remark="unit test",
        )
        db.commit()
    with SessionLocal() as db:
        row = db.query(RiskActionLog).filter(RiskActionLog.target_id == "R999").first()
        assert row is not None
        assert row.action_type == "TOGGLE_RULE"
        assert row.after_value == {"enabled": False}
        db.delete(row)
        db.commit()


def test_run_all_alert_checks_runs():
    with SessionLocal() as db:
        alerts = run_all_alert_checks(db)
        assert isinstance(alerts, list)
        db.rollback()


def test_scheduler_run_once_returns_dict():
    result = _run_once()
    assert {"closed_cases", "alerts_created", "errors"} <= set(result)
    assert isinstance(result["closed_cases"], int)
    assert isinstance(result["alerts_created"], int)


@pytest.mark.asyncio
async def test_scheduler_start_stop():
    assert not is_running()
    task = start_scheduler()
    assert is_running()
    await stop_scheduler()
    assert not is_running()
    assert task.done()


def test_alert_and_actionlog_endpoints():
    client = TestClient(app)
    with client:
        r = client.post("/api/alerts/check")
        assert r.status_code == 200
        assert "triggered_count" in r.json()
        assert client.get("/api/alerts").status_code == 200
        assert client.get("/api/action-logs").status_code == 200


def test_rule_toggle_writes_action_log():
    client = TestClient(app)
    with client:
        rules = client.get("/api/rules").json()["items"]
        r002 = next(r for r in rules if r["rule_id"] == "R002")
        first = client.put("/api/rules/R002/toggle", headers={"X-Operator": "tester"})
        assert first.status_code == 200
        # 恢复原状态
        client.put("/api/rules/R002/toggle", headers={"X-Operator": "tester"})
        logs = client.get("/api/action-logs?action_type=TOGGLE_RULE&page_size=50").json()["items"]
        assert any(x["target_id"] == "R002" and x["operator"] == "tester" for x in logs)
