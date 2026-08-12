from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.main import app
from models import InboundPayment, RiskRule


client = TestClient(app)


def test_health_dashboard_rules_and_model() -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["database"] == "pingpong"

    dashboard = client.get("/api/dashboard/stats")
    assert dashboard.status_code == 200
    assert dashboard.json()["inbound_count"] >= 500

    rules = client.get("/api/rules")
    assert rules.status_code == 200
    assert len(rules.json()) == 36

    metrics = client.get("/api/model/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["val_auc"] > 0.5
    assert metrics.json()["val_f1"] > 0


def test_rules_are_present_in_mysql() -> None:
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(RiskRule)) == 36


def test_inbound_check_without_persistence() -> None:
    with SessionLocal() as db:
        inbound_id = db.scalar(select(InboundPayment.id).order_by(InboundPayment.received_at.desc()))
    response = client.post(
        "/api/risk/check",
        json={"inbound_payment_id": inbound_id, "persist": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] in {"ALLOW", "FLAG", "MANUAL_REVIEW", "REJECT"}
    assert body["model_loaded"] is True
    model_features = client.get("/api/model/metrics").json()["feature_columns"]
    assert len(model_features) == 41
    assert set(model_features).issubset(body["features"])
