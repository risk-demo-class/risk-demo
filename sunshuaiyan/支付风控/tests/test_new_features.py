from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from models import Counterparty, InboundPayment, Payout, RiskBlacklist, RiskDecision, RiskEvent


client = TestClient(app)


def test_new_pages_and_agent_status() -> None:
    for path in ["/risk-check", "/assistant", "/blacklist"]:
        assert client.get(path).status_code == 200
    status = client.get("/api/agent/status")
    assert status.status_code == 200
    assert status.json()["mode"] in {"LOCAL_ANALYSIS", "DEEPSEEK"}
    assert status.json()["fallback_enabled"] is True


def test_blacklist_crud_is_soft_delete_and_idempotent() -> None:
    payload = {
        "entity_type": "COUNTRY",
        "entity_value": "ZZ",
        "display_name": "Synthetic test country",
        "reason_code": "TEST_ONLY",
        "reason_detail": "Automated test entry",
        "severity": "MEDIUM",
        "source": "MANUAL",
        "source_refs": ["pytest"],
        "created_by": "pytest",
    }
    created = client.post("/api/blacklist", json=payload)
    assert created.status_code == 201
    row = created.json()
    assert row["status"] == "ACTIVE"

    repeated = client.post("/api/blacklist", json=payload)
    assert repeated.status_code == 201
    assert repeated.json()["id"] == row["id"]

    removed = client.request(
        "DELETE",
        f"/api/blacklist/{row['id']}",
        json={"removed_by": "pytest", "removed_reason": "test cleanup"},
    )
    assert removed.status_code == 200
    with SessionLocal() as db:
        stored = db.get(RiskBlacklist, row["id"])
        assert stored is not None
        assert stored.is_active is False
        assert stored.removed_at is not None


def test_blacklist_is_a_veto_in_unified_risk_check() -> None:
    with SessionLocal() as db:
        transaction_id = db.scalar(
            select(InboundPayment.transaction_id)
            .join(Counterparty, Counterparty.id == InboundPayment.payer_counterparty_id)
            .join(
                RiskBlacklist,
                (RiskBlacklist.entity_type == "COUNTERPARTY")
                & (RiskBlacklist.normalized_value == Counterparty.counterparty_ref),
            )
            .where(RiskBlacklist.is_active.is_(True))
            .limit(1)
        )
    assert transaction_id is not None
    response = client.post(
        "/api/risk/check-workbench",
        json={"event_type": "INBOUND", "business_id": transaction_id, "persist": False},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["decision"] == "REJECT"
    assert result["veto"] is True
    assert result["blacklist_match"] is True
    assert result["final_score"] == 100


def test_local_assistant_uses_database_context(monkeypatch) -> None:
    from app.services import assistant

    monkeypatch.setattr(assistant.settings, "deepseek_api_key", "")
    response = client.post(
        "/api/agent/chat",
        json={"message": "解释 PP-R021 规则的决策逻辑"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["session_id"].startswith("sess_")
    assert "PP-R021" in result["reply"]
    assert "贸易单据" in result["reply"]


def test_deepseek_assistant_uses_context_and_provider(monkeypatch) -> None:
    from app.services import assistant

    monkeypatch.setattr(assistant.settings, "deepseek_api_key", "test-key")
    monkeypatch.setattr(
        assistant,
        "_deepseek_reply",
        lambda message, context, history: f"DeepSeek summary: {context}",
    )
    response = client.post("/api/agent/chat", json={"message": "解释 PP-R021"})
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "DEEPSEEK"
    assert result["provider"] == "DeepSeek"
    assert "PP-R021" in result["reply"]


def test_aggregate_summary_guard_rejects_unsupported_inference() -> None:
    from app.services.assistant import _aggregate_summary_needs_rewrite

    context = "入账 800 笔；模型验证 AUC 0.773，F1 0.533。"
    assert _aggregate_summary_needs_rewrite(context, "模型处于可用区间。") is True
    assert _aggregate_summary_needs_rewrite(
        context,
        "这是合成演示数据。AUC 为 0.773，未提供目标值，无法评价优劣。",
    ) is False
    assert _aggregate_summary_needs_rewrite(
        context,
        "这是合成演示数据。风险率未提供基线，不能判定为偏高或偏低。",
    ) is False


def test_payout_workbench_can_persist_audit_chain() -> None:
    with SessionLocal() as db:
        payout = db.scalar(select(Payout).order_by(Payout.id.desc()).limit(1))
    assert payout is not None
    response = client.post(
        "/api/risk/check-workbench",
        json={"event_type": "PAYOUT", "business_id": payout.payout_id, "persist": True},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["risk_event_id"].startswith("EVT-RISK-")
    assert result["risk_decision_id"].startswith("RDEC-")
    with SessionLocal() as db:
        event = db.scalar(select(RiskEvent).where(RiskEvent.event_id == result["risk_event_id"]))
        decision = db.scalar(
            select(RiskDecision).where(RiskDecision.decision_id == result["risk_decision_id"])
        )
        assert event is not None and event.subject_type == "PAYOUT"
        assert decision is not None and decision.risk_event_id == event.id
