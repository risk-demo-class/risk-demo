from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api import app
from app.database import get_db_async
from app.models import EventType
from app.models_risk import (
    CaseStatus,
    RiskActionLog,
    RiskBlacklist,
    RiskCase,
    RiskRule,
)
from app.schemas import RiskCheckRequest
from app.service.event import process_event
from scripts.seed_demo_data import seed_demo_data
from scripts.seed_rules import seed_rules


async def _seed(factory) -> None:
    async with factory() as db:
        async with db.begin():
            await seed_rules(db)
            await seed_demo_data(db)


def _override_database(factory):
    async def override_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db_async] = override_db


async def test_rule_crud_toggle_soft_delete_and_audit(session_factory) -> None:
    await _seed(session_factory)
    _override_database(session_factory)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            listed = await client.get("/api/rules")
            created = await client.post(
                "/api/rules",
                json={
                    "rule_id": "B021",
                    "rule_name": "测试高额转账",
                    "rule_category": "转账欺诈",
                    "event_type": "转账",
                    "rule_condition": {"field": "txn_amount", "op": ">=", "value": 88888},
                    "risk_level": "高",
                    "risk_score": 70,
                    "action": "人工审核",
                    "priority": 50,
                },
            )
            invalid = await client.post(
                "/api/rules",
                json={
                    "rule_id": "BAD",
                    "rule_name": "坏字段",
                    "rule_category": "转账欺诈",
                    "event_type": "转账",
                    "rule_condition": {"field": "fake_amount", "op": ">=", "value": 1},
                    "risk_level": "高",
                    "risk_score": 70,
                    "action": "人工审核",
                },
            )
            toggled = await client.put("/api/rules/B021/toggle")
            deleted = await client.delete("/api/rules/B021")
            after_delete = await client.get("/api/rules/B021")
    finally:
        app.dependency_overrides.clear()

    assert listed.json()["total"] == 20
    assert created.status_code == 201
    assert invalid.status_code == 400
    assert toggled.json()["is_enabled"] is False
    assert deleted.status_code == 200
    assert after_delete.status_code == 404
    async with session_factory() as db:
        rule = await db.get(RiskRule, "B021")
        audit_count = await db.scalar(select(func.count(RiskActionLog.log_id)))
    assert rule is not None and rule.deleted_at is not None
    assert audit_count == 3


async def test_blacklist_values_are_masked_and_delete_is_soft(session_factory) -> None:
    await _seed(session_factory)
    _override_database(session_factory)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = await client.post(
                "/api/blacklist",
                json={
                    "blacklist_type": "银行账户",
                    "blacklist_value": "DEMO_ACCOUNT_HASH_123456789",
                    "reason": "自动化测试",
                    "operator": "tester",
                },
            )
            row_id = created.json()["blacklist_id"]
            listed = await client.get("/api/blacklist?blacklist_type=银行账户")
            removed = await client.delete(f"/api/blacklist/{row_id}?operator=tester")
            listed_after = await client.get("/api/blacklist?blacklist_type=银行账户")
    finally:
        app.dependency_overrides.clear()

    assert created.status_code == 201
    assert "DEMO_ACCOUNT_HASH_123456789" not in created.text
    assert listed.json()["items"][0]["blacklist_value_masked"].startswith("DEMO")
    assert removed.status_code == 200
    assert listed_after.json()["total"] == 0
    async with session_factory() as db:
        row = await db.get(RiskBlacklist, row_id)
        audit_count = await db.scalar(select(func.count(RiskActionLog.log_id)))
    assert row is not None and row.deleted_at is not None
    assert audit_count == 2


async def test_case_review_state_machine_and_reject_with_blacklist_are_atomic(session_factory) -> None:
    await _seed(session_factory)
    async with session_factory() as db:
        response = await process_event(
            db,
            RiskCheckRequest(
                event_type=EventType.CARD_PAYMENT,
                source_id="T90002",
                user_id="U90001",
            ),
        )
    assert response.decision.value == "人工审核"

    _override_database(session_factory)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            cases = await client.get("/api/cases")
            case_id = cases.json()["items"][0]["case_id"]
            detail = await client.get(f"/api/cases/{case_id}")
            rejected = await client.post(
                f"/api/cases/{case_id}/review",
                json={
                    "new_status": "已拒绝",
                    "reviewer": "auditor1",
                    "review_comment": "客户无法确认新设备交易",
                    "add_to_blacklist": True,
                    "blacklist_type": "用户",
                },
            )
            illegal = await client.post(
                f"/api/cases/{case_id}/review",
                json={
                    "new_status": "已通过",
                    "reviewer": "auditor1",
                    "review_comment": "试图从终态回退",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert cases.json()["total"] == 1
    assert len(detail.json()["features"]) == 25
    assert rejected.status_code == 200
    assert rejected.json()["case_status"] == "已拒绝"
    assert illegal.status_code == 400
    async with session_factory() as db:
        case = await db.get(RiskCase, case_id)
        blacklisted = await db.scalar(
            select(RiskBlacklist).where(
                RiskBlacklist.blacklist_type == "用户",
                RiskBlacklist.blacklist_value == "U90001",
                RiskBlacklist.deleted_at.is_(None),
            )
        )
        audit_count = await db.scalar(select(func.count(RiskActionLog.log_id)))
    assert case is not None and case.case_status is CaseStatus.REJECTED
    assert blacklisted is not None
    assert audit_count == 2


async def test_assessment_detail_and_dashboard_use_real_decision_data(session_factory) -> None:
    await _seed(session_factory)
    async with session_factory() as db:
        normal = await process_event(
            db,
            RiskCheckRequest(event_type=EventType.TRANSFER, source_id="T10001", user_id="U10001"),
        )
        risk = await process_event(
            db,
            RiskCheckRequest(event_type=EventType.TRANSFER, source_id="T90001", user_id="U90001"),
        )

    _override_database(session_factory)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assessments = await client.get("/api/assessments")
            detail = await client.get(f"/api/assessments/{risk.assessment_id}")
            dashboard = await client.get("/api/dashboard/overview")
            profile = await client.get("/api/profile/U10001")
    finally:
        app.dependency_overrides.clear()

    assert normal.assessment_id is not None
    assert assessments.status_code == 200 and assessments.json()["total"] == 2
    assert len(detail.json()["features"]) == 25
    assert detail.json()["rule_count"] == 4
    assert dashboard.json()["today_assessments"] == 2
    assert dashboard.json()["today_high_risk"] == 1
    assert dashboard.json()["top_rules"][0]["hit_count"] == 1
    assert profile.status_code == 200
    assert profile.json()["assessment_count"] == 1
