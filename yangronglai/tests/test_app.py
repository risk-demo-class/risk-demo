from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api import app
from app.bootstrap import initialize_database
from app.config import settings
from app.database import close_database, get_session_factory
from app.models_risk import (
    RiskAppeal,
    RiskAppealEvidence,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeatureSnapshot,
    RiskLabel,
    RiskRuleHit,
)
from app.engine.model_manager import model_manager


@pytest.fixture
async def initialized_database(tmp_path) -> AsyncIterator[None]:
    original_driver = settings.DB_DRIVER
    original_path = settings.SQLITE_PATH
    original_model = settings.ENABLE_MODEL_ENGINE
    original_graph = settings.ENABLE_GRAPH_ENGINE
    settings.DB_DRIVER = "sqlite"
    settings.SQLITE_PATH = str(tmp_path / "bankrisk-test.db")
    settings.ENABLE_MODEL_ENGINE = False
    settings.ENABLE_GRAPH_ENGINE = False
    await close_database()
    await initialize_database(seed_demo=True)
    try:
        yield
    finally:
        await close_database()
        settings.DB_DRIVER = original_driver
        settings.SQLITE_PATH = original_path
        settings.ENABLE_MODEL_ENGINE = original_model
        settings.ENABLE_GRAPH_ENGINE = original_graph


@pytest.fixture
async def client(initialized_database) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "BankRisk-AI"
    assert body["stage"] == "complete-three-layer"


async def test_dashboard_page(client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert "银行智能风控平台" in response.text
    assert "规则兜底、模型提准、图谱挖团" in response.text
    assert "信用卡" in response.text
    assert "贷款" in response.text
    assert "转账" in response.text
    assert "登录" in response.text
    assert "客户申诉" in response.text


async def test_risk_capabilities_cover_data_and_rules(client: AsyncClient) -> None:
    response = await client.get("/api/risk/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["scenarios"] == ["CARD", "LOAN", "TRANSFER", "LOGIN"]
    assert body["business_tables"] == 8
    assert body["risk_tables"] == 10
    assert body["mandatory_rules"] == 8


async def test_safe_transfer_is_persisted_and_passes(client: AsyncClient) -> None:
    response = await client.post(
        "/api/risk/check",
        json={"scenario": "TRANSFER", "source_id": "TXN_SAFE", "user_id": "U_SAFE"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert response.headers["x-request-id"] == body["request_id"]
    assert body["request_id"].startswith("REQ_")
    assert body["stage"] == "complete-three-layer"
    assert body["final_score"] == 0
    assert body["risk_level"] == "低"
    assert body["decision"] == "通过"
    assert body["appeal"] == {
        "allowed": False,
        "deadline": None,
        "page_url": None,
        "submit_url": None,
        "token": None,
    }
    assert body["hit_count"] == 0
    assert body["score_breakdown"]["additional_weight"] == 0.2
    assert body["score_breakdown"]["raw_score"] == 0
    assert body["score_breakdown"]["capped_at_100"] is False

    assessment = await client.get(f"/api/risk/assessments/{body['assessment_id']}")
    assert assessment.status_code == 200
    assert assessment.json()["event_id"] == body["event_id"]


async def test_safe_transfer_is_not_contaminated_by_transitive_graph_links(
    client: AsyncClient,
) -> None:
    """Ordinary transfer counterparties must not spread fraud labels three hops."""
    settings.ENABLE_GRAPH_ENGINE = True
    try:
        response = await client.post(
            "/api/risk/check",
            json={"scenario": "TRANSFER", "source_id": "TXN_SAFE", "user_id": "U_SAFE"},
        )
    finally:
        settings.ENABLE_GRAPH_ENGINE = False

    assert response.status_code == 200, response.text
    body = response.json()
    graph = next(component for component in body["components"] if component["component"] == "graph")
    assert graph["score"] == 0
    assert body["risk_level"] == "低"
    assert body["decision"] == "通过"


@pytest.mark.parametrize(
    ("scenario", "source_id", "user_id", "expected_rule", "expected_decision"),
    [
        ("TRANSFER", "TXN_R001", "U_R001", "R001", "拒绝"),
        ("CARD", "TXN_R002_3", "U_R002", "R002", "人工审核"),
        ("TRANSFER", "TXN_R005", "U_R005", "R005", "人工审核"),
        ("TRANSFER", "TXN_R008_3", "U_R008_C", "R008", "拒绝"),
        ("LOAN", "LOAN_R012_3", "U_R012", "R012", "人工审核"),
        ("LOGIN", "LOGIN_R018", "U_SHARED_1", "R018", "标记"),
        ("LOGIN", "LOGIN_R025", "U_R025", "R025", "标记"),
        ("TRANSFER", "TXN_R030", "U_R030", "R030", "拒绝"),
    ],
)
async def test_each_mandatory_rule_has_executable_demo(
    client: AsyncClient,
    scenario: str,
    source_id: str,
    user_id: str,
    expected_rule: str,
    expected_decision: str,
) -> None:
    response = await client.post(
        "/api/risk/check",
        json={"scenario": scenario, "source_id": source_id, "user_id": user_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert expected_rule in {hit["rule_id"] for hit in body["hits"]}
    assert body["decision"] == expected_decision


async def test_rule_catalog_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/risk/rules")
    assert response.status_code == 200, response.text
    rules = response.json()
    assert [rule["rule_id"] for rule in rules] == [
        "R001", "R002", "R005", "R008", "R012", "R018", "R025", "R030"
    ]


async def test_manual_review_persists_full_audit_chain_and_case(client: AsyncClient) -> None:
    response = await client.post(
        "/api/risk/check",
        json={"scenario": "TRANSFER", "source_id": "TXN_R005", "user_id": "U_R005"},
    )
    body = response.json()
    assert body["decision"] == "人工审核"
    async with get_session_factory()() as session:
        assert await session.get(RiskEvent, body["event_id"]) is not None
        assert await session.get(RiskAssessment, body["assessment_id"]) is not None
        assert await session.scalar(
            select(RiskFeatureSnapshot).where(RiskFeatureSnapshot.event_id == body["event_id"])
        ) is not None
        assert await session.scalar(
            select(RiskRuleHit).where(RiskRuleHit.event_id == body["event_id"])
        ) is not None
        assert await session.scalar(
            select(RiskCase).where(RiskCase.assessment_id == body["assessment_id"])
        ) is not None


async def test_unknown_event_requires_realtime_fields(client: AsyncClient) -> None:
    response = await client.post(
        "/api/risk/check",
        json={"scenario": "TRANSFER", "source_id": "UNKNOWN", "user_id": "U_SAFE"},
    )
    assert response.status_code == 422
    assert "amount" in response.json()["detail"]


async def test_api_returns_weighted_multi_rule_breakdown_and_cap(client: AsyncClient) -> None:
    response = await client.post(
        "/api/risk/check",
        json={
            "scenario": "TRANSFER",
            "source_id": "REALTIME_MULTI_RULE",
            "user_id": "U_R005",
            "event_data": {
                "amount": 60001,
                "from_card": "CARD_R005",
                "to_card": "CARD_R005_TARGET",
                "device_id": "DEV_R005",
                "ip": "10.0.0.2",
                "current_city": "上海",
                "usual_city": "北京",
                "occurred_at": datetime.now(UTC).isoformat(),
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert {hit["rule_id"] for hit in body["hits"]} >= {"R001", "R005"}
    assert body["score_breakdown"]["highest_rule_score"] == 100
    assert body["score_breakdown"]["other_rules_score_sum"] >= 75
    assert body["score_breakdown"]["capped_at_100"] is True
    assert body["final_score"] == 100


async def test_complete_three_layer_response_has_all_component_scores(client: AsyncClient) -> None:
    settings.ENABLE_MODEL_ENGINE = True
    settings.ENABLE_GRAPH_ENGINE = True
    assert model_manager.ensure_ready()
    response = await client.post(
        "/api/risk/check",
        json={"scenario": "LOGIN", "source_id": "LOGIN_R018", "user_id": "U_SHARED_1"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    component_scores = {item["component"]: item["score"] for item in body["components"]}
    assert component_scores["rule"] == 40
    assert component_scores["model"] is not None
    assert component_scores["graph"] >= 65
    assert set(body["fusion_breakdown"]["component_scores"]) == {"rule", "model", "graph"}
    assert body["final_score"] >= max(component_scores.values())


async def test_operations_and_local_agent_are_available(client: AsyncClient) -> None:
    dashboard = await client.get("/api/dashboard/overview")
    models = await client.get("/api/models/status")
    graph = await client.get("/api/graph/users/U_SHARED_1")
    agent = await client.post("/api/agent/chat", json={"message": "查询仪表盘统计"})
    assert dashboard.status_code == 200
    assert models.status_code == 200
    assert graph.status_code == 200
    assert graph.json()["nodes"]
    assert agent.status_code == 200
    assert agent.json()["tools_used"] == ["query_dashboard_stats"]


async def test_rejected_client_can_appeal_add_evidence_and_receive_reconsideration(
    client: AsyncClient,
) -> None:
    rejected = await client.post(
        "/api/risk/check",
        json={"scenario": "TRANSFER", "source_id": "TXN_R030", "user_id": "U_R030"},
    )
    assert rejected.status_code == 200, rejected.text
    rejected_body = rejected.json()
    assert rejected_body["decision"] == "拒绝"
    assert rejected_body["appeal"]["allowed"] is True
    assert rejected_body["appeal"]["page_url"] == "/appeal"
    appeal_token = rejected_body["appeal"]["token"]
    assessment_id = rejected_body["assessment_id"]

    submitted = await client.post(
        "/api/client/appeals",
        json={
            "assessment_id": assessment_id,
            "appeal_token": appeal_token,
            "reason": "该笔交易由本人操作，并可提供完整的交易证明材料。",
            "requested_resolution": "请求人工复议并解除本次限制",
        },
    )
    assert submitted.status_code == 201, submitted.text
    appeal = submitted.json()
    appeal_id = appeal["appeal_id"]
    assert appeal["status"] == "SUBMITTED"
    assert appeal["original_assessment"]["decision"] == "拒绝"
    assert "user_id" not in submitted.text
    assert "appeal_token" not in submitted.text

    replay = await client.post(
        "/api/client/appeals",
        json={
            "assessment_id": assessment_id,
            "appeal_token": appeal_token,
            "reason": "重复请求不会创建第二条申诉记录。",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["appeal_id"] == appeal_id

    denied_query = await client.get(
        f"/api/client/appeals/{appeal_id}", headers={"X-Appeal-Token": "invalid-token"}
    )
    assert denied_query.status_code == 401

    evidence = await client.post(
        f"/api/client/appeals/{appeal_id}/evidence",
        headers={"X-Appeal-Token": appeal_token},
        json={"evidence_type": "STATEMENT", "statement": "本人确认交易时间、金额和收款方均无误。"},
    )
    assert evidence.status_code == 200, evidence.text
    assert len(evidence.json()["evidence"]) == 1

    original_review_token = settings.APPEAL_REVIEW_TOKEN
    settings.APPEAL_REVIEW_TOKEN = "test-internal-review-token"
    try:
        queue = await client.get(
            "/api/internal/appeals",
            headers={"X-Internal-Approval-Token": settings.APPEAL_REVIEW_TOKEN},
        )
        assert queue.status_code == 200
        assert appeal_id in {item["appeal_id"] for item in queue.json()["items"]}

        needs_info = await client.post(
            f"/api/internal/appeals/{appeal_id}/review",
            headers={"X-Internal-Approval-Token": settings.APPEAL_REVIEW_TOKEN},
            json={
                "decision": "MORE_INFO_REQUIRED",
                "reviewer": "appeal-analyst",
                "comment": "请补充交易凭证文件哈希。",
            },
        )
        assert needs_info.status_code == 200
        assert needs_info.json()["status"] == "NEEDS_INFO"

        extra_evidence = await client.post(
            f"/api/client/appeals/{appeal_id}/evidence",
            headers={"X-Appeal-Token": appeal_token},
            json={
                "evidence_type": "TRANSACTION_PROOF",
                "file_name": "proof.pdf",
                "file_sha256": "a" * 64,
            },
        )
        assert extra_evidence.status_code == 200
        assert extra_evidence.json()["status"] == "SUBMITTED"

        overturned = await client.post(
            f"/api/internal/appeals/{appeal_id}/review",
            headers={"X-Internal-Approval-Token": settings.APPEAL_REVIEW_TOKEN},
            json={
                "decision": "OVERTURN",
                "reviewer": "appeal-analyst",
                "comment": "证据核验通过，推翻原拒绝策略结果。",
            },
        )
        assert overturned.status_code == 200, overturned.text
        assert overturned.json()["status"] == "DECISION_OVERTURNED"
    finally:
        settings.APPEAL_REVIEW_TOKEN = original_review_token

    original = await client.get(f"/api/risk/assessments/{assessment_id}")
    assert original.status_code == 200
    assert original.json()["decision"] == "拒绝"

    terminal_evidence = await client.post(
        f"/api/client/appeals/{appeal_id}/evidence",
        headers={"X-Appeal-Token": appeal_token},
        json={"evidence_type": "STATEMENT", "statement": "终态后不应继续写入材料。"},
    )
    assert terminal_evidence.status_code == 409

    async with get_session_factory()() as session:
        stored = await session.get(RiskAppeal, appeal_id)
        assert stored is not None and stored.status == "DECISION_OVERTURNED"
        assert await session.scalar(
            select(RiskAppealEvidence).where(RiskAppealEvidence.appeal_id == appeal_id)
        ) is not None
        correction = await session.scalar(
            select(RiskLabel).where(
                RiskLabel.scenario == "TRANSFER",
                RiskLabel.source_id == "TXN_R030",
                RiskLabel.label_source == "APPEAL",
            )
        )
        assert correction is not None and correction.label == "LEGIT"
