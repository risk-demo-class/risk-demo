"""第三阶段验收：所有数据库集成测试均连接真实 MySQL 测试库。"""
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.engine.decision import _calculate_decision, check_veto
from app.engine.feature import FEATURE_NAMES, compute_all_features, resolve_event_context
from app.engine.ml_model import (
    FEATURE_COLUMNS,
    MlResult,
    is_model_loaded,
    load_model,
    predict,
)
from app.engine.rule import match_rules
from app.models import (
    RiskActionLog,
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskRule,
    RiskUserProfile,
)
from app.schemas import RiskCheckRequest
from app.service.event import _blacklist_candidates, process_event
from scripts.train_education_model import generate_training_set


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MYSQL_TEST_DB = "ai_risk_education_test"


async def _with_mysql(callback):
    """每次测试创建并关闭自己的 MySQL 引擎，避免跨 event loop 复用连接。"""
    engine = create_async_engine(
        settings.get_database_url_async(MYSQL_TEST_DB),
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            return await callback(session)
    finally:
        await engine.dispose()


def _run_mysql(callback):
    return asyncio.run(_with_mysql(callback))


async def _clear_runtime_state(db: AsyncSession) -> None:
    """只清理专用测试库的运行态风控记录，业务种子和八条规则保留。"""
    current_db = await db.scalar(text("SELECT DATABASE()"))
    if current_db != MYSQL_TEST_DB:
        raise RuntimeError(f"拒绝清理非测试库: {current_db}")
    for model in (
        RiskActionLog,
        RiskCase,
        RiskAssessment,
        RiskFeature,
        RiskEvent,
        RiskUserProfile,
        RiskBlacklist,
    ):
        await db.execute(delete(model))
    await db.commit()


RULE_DEFINITIONS = (
    ("EDU001", "零学时大额退费", "退费滥用", "退费申请", {"and": [
        {"field": "order_pay_interval_sec", "op": "<", "value": 5},
        {"field": "order_total_amount", "op": ">=", "value": 1000},
    ]}, "高", 70, "人工审核"),
    ("EDU002", "连环退费", "退费滥用", "退费申请", {"and": [
        {"field": "user_postsale_count", "op": ">=", "value": 3},
        {"field": "user_refund_amount", "op": ">=", "value": 10000},
    ]}, "高", 75, "人工审核"),
    ("EDU003", "极高退费率", "退费滥用", "通用", {"and": [
        {"field": "user_total_orders", "op": ">=", "value": 3},
        {"field": "user_refund_rate", "op": ">=", "value": 0.5},
    ]}, "极高", 95, "拒绝"),
    ("EDU004", "同设备多账号", "设备风险", "通用",
     {"field": "addr_province_count", "op": ">=", "value": 5}, "极高", 95, "拒绝"),
    ("EDU005", "新设备大额报名", "设备风险", "课程报名", {"and": [
        {"field": "addr_is_new", "op": "==", "value": 1},
        {"field": "order_total_amount", "op": ">=", "value": 10000},
    ]}, "高", 70, "人工审核"),
    ("EDU006", "凌晨大额报名", "交易异常", "课程报名", {"and": [
        {"field": "order_is_night", "op": "==", "value": 1},
        {"field": "order_total_amount", "op": ">=", "value": 5000},
    ]}, "中", 45, "标记"),
    ("EDU007", "身份连续认证失败", "认证风险", "通用",
     {"field": "user_complaint_count", "op": ">=", "value": 2}, "高", 70, "人工审核"),
    ("EDU008", "超高金额报名", "交易异常", "课程报名",
     {"field": "order_total_amount", "op": ">=", "value": 30000}, "极高", 95, "拒绝"),
)


def _make_rule(definition) -> RiskRule:
    rule_id, name, category, event_type, condition, level, score, action = definition
    return RiskRule(
        rule_id=rule_id,
        rule_name=name,
        rule_category=category,
        event_type=event_type,
        rule_condition=json.dumps(condition, ensure_ascii=False),
        risk_level=level,
        risk_score=score,
        action=action,
        is_enabled=1,
        priority=score,
        description=name,
    )


def test_feature_order_is_single_source_for_model():
    assert tuple(FEATURE_COLUMNS) == FEATURE_NAMES
    assert len(FEATURE_NAMES) == 25


def test_mysql_schema_seed_counts_and_rule_ids():
    async def scenario(db: AsyncSession):
        assert await db.scalar(text("SELECT DATABASE()")) == MYSQL_TEST_DB
        table_count = await db.scalar(text(
            "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=:db"
        ), {"db": MYSQL_TEST_DB})
        assert table_count == 16
        assert await db.scalar(text("SELECT COUNT(*) FROM user_info")) == 65
        assert await db.scalar(text("SELECT COUNT(*) FROM course")) == 20
        assert await db.scalar(text("SELECT COUNT(*) FROM order_info")) == 180
        assert await db.scalar(text("SELECT COUNT(*) FROM risk_rule")) == 8
        rule_ids = set((await db.execute(text("SELECT rule_id FROM risk_rule"))).scalars())
        assert rule_ids == {f"EDU{index:03d}" for index in range(1, 9)}

    _run_mysql(scenario)


def test_mysql_features_cover_all_education_risk_patterns():
    async def compute(db: AsyncSession, event_type: str, source_id: str, user_id: str):
        context = await resolve_event_context(
            db, event_type=event_type, source_id=source_id, user_id=user_id
        )
        return await compute_all_features(
            db,
            user_id=user_id,
            event_type=event_type,
            source_id=source_id,
            event_context=context,
        )

    async def scenario(db: AsyncSession):
        refund = await compute(db, "退费申请", "REF0005", "RISK001")
        shared = await compute(db, "课程报名", "ORD00145", "RISK009")
        verification = await compute(db, "学历认证", "VER0053", "RISK013")
        new_device = await compute(db, "课程报名", "ORD00171", "RISK017")
        night = await compute(db, "课程报名", "ORD00173", "RISK018")
        ultra = await compute(db, "课程报名", "ORD00180", "RISK020")

        assert tuple(refund) == FEATURE_NAMES and len(refund) == 25
        assert refund["order_total_amount"] == 8999
        assert refund["order_pay_interval_sec"] == 0
        assert shared["addr_province_count"] >= 5
        assert verification["user_complaint_count"] >= 2
        assert new_device["addr_is_new"] == 1
        assert new_device["order_total_amount"] >= 10000
        assert night["order_is_night"] == 1
        assert night["order_total_amount"] >= 5000
        assert ultra["order_total_amount"] >= 30000

    _run_mysql(scenario)


def test_all_eight_education_rule_conditions_can_match():
    risky = {name: 0.0 for name in FEATURE_NAMES}
    risky.update({
        "user_total_orders": 5,
        "user_postsale_count": 3,
        "user_refund_count": 3,
        "user_refund_rate": 0.6,
        "user_refund_amount": 12000,
        "user_complaint_count": 2,
        "order_total_amount": 30000,
        "order_pay_interval_sec": 0,
        "order_is_night": 1,
        "addr_province_count": 5,
        "addr_is_new": 1,
    })
    hits = match_rules([_make_rule(item) for item in RULE_DEFINITIONS], risky)
    assert {hit.rule_id for hit in hits} == {f"EDU{index:03d}" for index in range(1, 9)}
    assert check_veto(hits) is True


def test_ml_cannot_downgrade_explicit_rule_action():
    mark_hit = match_rules(
        [_make_rule(RULE_DEFINITIONS[5])],
        {"order_is_night": 1, "order_total_amount": 6000},
    )
    review_hit = match_rules(
        [_make_rule(RULE_DEFINITIONS[0])],
        {"order_pay_interval_sec": 0, "order_total_amount": 2000},
    )
    low_ml = MlResult(score=0.0, decision="通过", is_loaded=True)
    with patch("app.engine.decision.is_model_loaded", return_value=True), patch(
        "app.engine.decision.predict", return_value=low_ml
    ):
        mark_result = _calculate_decision(mark_hit, {})
        review_result = _calculate_decision(review_hit, {})
    assert mark_result[2] == "标记" and mark_result[0] >= 30
    assert review_result[2] == "人工审核" and review_result[0] >= 60


def test_mysql_blacklist_candidates_use_hashes_in_priority_order():
    async def scenario(db: AsyncSession):
        request = RiskCheckRequest(event_type="课程报名", source_id="ORD00001", user_id="EDU001")
        context = await resolve_event_context(
            db, event_type=request.event_type, source_id=request.source_id, user_id=request.user_id
        )
        candidates = await _blacklist_candidates(db, request, context)
        assert [item[0] for item in candidates] == ["用户", "学号", "身份证", "设备指纹"]
        assert all(value and (kind == "用户" or len(value) == 64) for kind, value in candidates)

    _run_mysql(scenario)


def test_mysql_full_pipeline_persists_25_features_and_veto_case():
    async def scenario(db: AsyncSession):
        await _clear_runtime_state(db)
        try:
            request = RiskCheckRequest(
                event_type="课程报名", source_id="ORD00145", user_id="RISK009"
            )
            response = await process_event(db, request)
            hit_ids = {hit.rule_id for hit in response.triggered_rules}
            assert "EDU004" in hit_ids
            assert response.decision == "拒绝"
            assert response.risk_level == "极高"
            assert len(response.features) == 25

            event_id = await db.scalar(select(RiskEvent.event_id).where(
                RiskEvent.event_source_id == "ORD00145"
            ))
            assert event_id
            assert await db.scalar(
                select(func.count()).select_from(RiskFeature).where(RiskFeature.event_id == event_id)
            ) == 25
            assert await db.scalar(select(func.count()).select_from(RiskAssessment)) == 1
            assert await db.scalar(select(func.count()).select_from(RiskCase)) == 1
        finally:
            await db.rollback()
            await _clear_runtime_state(db)

    _run_mysql(scenario)


def test_mysql_blacklist_short_circuits_without_assessment():
    async def scenario(db: AsyncSession):
        await _clear_runtime_state(db)
        try:
            db.add(RiskBlacklist(
                blacklist_type="用户", blacklist_value="EDU001", reason="MySQL集成测试"
            ))
            await db.commit()
            request = RiskCheckRequest(
                event_type="课程报名", source_id="ORD00001", user_id="EDU001"
            )
            response = await process_event(db, request)
            assert response.assessment_id == "blacklist_reject"
            assert response.blocked_by == "用户"
            assert response.decision == "拒绝"
            assert await db.scalar(select(func.count()).select_from(RiskEvent)) == 0
            assert await db.scalar(select(func.count()).select_from(RiskAssessment)) == 0
        finally:
            await db.rollback()
            await _clear_runtime_state(db)

    _run_mysql(scenario)


def test_training_data_and_trained_model_quality():
    first_X, first_y, first_scenarios = generate_training_set(rows=500, seed=20260811)
    second_X, second_y, second_scenarios = generate_training_set(rows=500, seed=20260811)
    assert np.array_equal(first_X, second_X)
    assert np.array_equal(first_y, second_y)
    assert first_scenarios == second_scenarios
    assert "正常学历认证" in first_scenarios
    assert first_X.shape == (500, 25)
    assert 0.25 < first_y.mean() < 0.45

    metrics = json.loads(
        (PROJECT_ROOT / "data" / "education_model_metrics.json").read_text(encoding="utf-8")
    )
    assert metrics["feature_count"] == 25
    assert metrics["is_fake_convergence"] is False
    assert metrics["val_auc"] >= 0.90
    assert metrics["val_f1"] >= 0.85

    if not is_model_loaded():
        assert load_model() is True
    X, y, _ = generate_training_set(rows=300, seed=20260812)
    positive_scores, negative_scores = [], []
    for vector, label in zip(X, y):
        score = predict(dict(zip(FEATURE_NAMES, map(float, vector)))).score
        (positive_scores if label else negative_scores).append(score)
    assert float(np.mean(positive_scores)) > float(np.mean(negative_scores)) + 0.35


def test_rule_seed_sql_contains_exactly_edu001_to_edu008():
    sql = (PROJECT_ROOT / "sql" / "init_risk_data.sql").read_text(encoding="utf-8")
    for index in range(1, 9):
        assert sql.count(f"('EDU{index:03d}'") == 1
    assert "R001" not in sql
