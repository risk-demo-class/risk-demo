from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api import app
from app.database import get_db_async
from app.engine.feature import FEATURE_COLUMNS, compute_features
from app.models import Decision, EventType, RiskLevel
from app.models_risk import RiskAssessment, RiskCase, RiskEvent, RiskFeature, RiskUserProfile
from app.schemas import RiskCheckRequest
from app.service.enrichment import enrich_request_context
from app.service.event import process_event
from app.service.validator import validate_business_entity
from scripts.seed_demo_data import seed_demo_data
from scripts.seed_rules import seed_rules


async def _seed(factory) -> None:
    async with factory() as db:
        async with db.begin():
            await seed_rules(db)
            await seed_demo_data(db)


async def test_feature_contract_has_exactly_25_values(session_factory) -> None:
    await _seed(session_factory)
    async with session_factory() as db:
        request = RiskCheckRequest(event_type=EventType.TRANSFER, source_id="T10001", user_id="U10001")
        context = await validate_business_entity(db, request)
        context = await enrich_request_context(db, context)
        features = await compute_features(db, context)

    assert tuple(features) == FEATURE_COLUMNS
    assert len(features) == 25
    assert features["txn_amount"] == 1000
    assert features["txn_cross_city"] == 0


async def test_normal_transfer_persists_complete_audit_chain(session_factory) -> None:
    await _seed(session_factory)
    async with session_factory() as db:
        response = await process_event(
            db,
            RiskCheckRequest(event_type=EventType.TRANSFER, source_id="T10001", user_id="U10001"),
        )

    assert response.decision is Decision.PASS
    assert response.assessment_id and response.event_id
    assert len(response.features) == 25
    assert response.ml_score is None

    async with session_factory() as db:
        feature_count = await db.scalar(
            select(func.count(RiskFeature.feature_id)).where(RiskFeature.event_id == response.event_id)
        )
        assessment = await db.get(RiskAssessment, response.assessment_id)
        profile = await db.get(RiskUserProfile, "U10001")
    assert feature_count == 25
    assert assessment is not None
    assert profile is not None and profile.assessment_count == 1


async def test_extreme_transfer_is_vetoed_and_creates_rejected_case(session_factory) -> None:
    await _seed(session_factory)
    async with session_factory() as db:
        response = await process_event(
            db,
            RiskCheckRequest(event_type=EventType.TRANSFER, source_id="T90001", user_id="U90001"),
        )

    assert response.decision is Decision.REJECT
    assert response.risk_level is RiskLevel.EXTREME
    assert response.final_score >= 90
    assert "B004" in {rule.rule_id for rule in response.triggered_rules}

    async with session_factory() as db:
        case = await db.scalar(select(RiskCase).where(RiskCase.assessment_id == response.assessment_id))
    assert case is not None
    assert case.case_status.value == "已拒绝"
    assert case.reviewer == "system"


async def test_blacklist_short_circuit_does_not_write_event_or_assessment(session_factory) -> None:
    await _seed(session_factory)
    async with session_factory() as db:
        response = await process_event(
            db,
            RiskCheckRequest(event_type=EventType.TRANSFER, source_id="T10003", user_id="U10001"),
        )

    assert response.decision is Decision.REJECT
    assert response.blocked_by == "收款账户"
    assert response.event_id is None
    assert response.assessment_id is None
    assert response.ml_score is None

    async with session_factory() as db:
        event_count = await db.scalar(select(func.count(RiskEvent.event_id)))
        assessment_count = await db.scalar(select(func.count(RiskAssessment.assessment_id)))
    assert event_count == 0
    assert assessment_count == 0


async def test_horizontal_access_is_rejected(session_factory) -> None:
    await _seed(session_factory)
    async with session_factory() as db:
        try:
            await process_event(
                db,
                RiskCheckRequest(event_type=EventType.TRANSFER, source_id="T90001", user_id="U10001"),
            )
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 403
        else:
            raise AssertionError("使用其他客户交易ID必须被拒绝")


async def test_risk_check_http_endpoint_is_exposed(session_factory) -> None:
    await _seed(session_factory)

    async def override_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db_async] = override_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/risk/check",
                json={"event_type": "贷款申请", "source_id": "LN90001", "user_id": "U90001"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "拒绝"
    assert payload["features"]["loan_debt_ratio"] == 0.8
    assert len(payload["features"]) == 25

