"""Step 5 manufacturing JSON-rule data and real-feature integration tests."""

from __future__ import annotations

import json
import os
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.engine.feature import compute_all_features
from app.engine.ml_model import FEATURE_COLUMNS
from app.engine.rule import evaluate_condition, load_enabled_rules, match_rules
from app.models import RiskBlacklist, RiskRule, WarrantyClaim


EXPECTED_RULES = {
    "R001": {
        "name": "跨区域串货拦截",
        "category": "物流风险",
        "event_type": "物流投诉",
        "level": "极高",
        "score": 95,
        "action": "拒绝",
        "priority": 100,
        "fields": {"addr_is_new", "order_discount_rate"},
    },
    "R002": {
        "name": "经销商累计高频保修",
        "category": "售后滥用",
        "event_type": "售后申请",
        "level": "高",
        "score": 70,
        "action": "人工审核",
        "priority": 80,
        "fields": {"user_postsale_count"},
    },
    "R003": {
        "name": "新经销商大额采购",
        "category": "订单欺诈",
        "event_type": "下单",
        "level": "高",
        "score": 75,
        "action": "人工审核",
        "priority": 90,
        "fields": {"user_cancel_count", "order_total_amount"},
    },
    "R004": {
        "name": "老旧设备高额保修",
        "category": "售后滥用",
        "event_type": "售后申请",
        "level": "高",
        "score": 75,
        "action": "人工审核",
        "priority": 85,
        "fields": {"order_pay_interval_sec", "order_total_amount"},
    },
    "R005": {
        "name": "经销商多异常区域暴露",
        "category": "地址风险",
        "event_type": "通用",
        "level": "高",
        "score": 65,
        "action": "人工审核",
        "priority": 70,
        "fields": {"addr_province_count", "addr_total_count"},
    },
    "R006": {
        "name": "同设备重复保修拦截",
        "category": "售后滥用",
        "event_type": "售后申请",
        "level": "极高",
        "score": 92,
        "action": "拒绝",
        "priority": 95,
        "fields": {"order_sku_count"},
    },
    "R007": {
        "name": "高额保修缺少材料",
        "category": "售后滥用",
        "event_type": "售后申请",
        "level": "中",
        "score": 45,
        "action": "标记",
        "priority": 60,
        "fields": {"order_total_amount", "order_category_count"},
    },
}


def _condition_fields(condition: dict) -> set[str]:
    if "and" in condition:
        return set().union(*(_condition_fields(item) for item in condition["and"]))
    if "or" in condition:
        return set().union(*(_condition_fields(item) for item in condition["or"]))
    return {condition["field"]}


def _condition_ops(condition: dict) -> set[str]:
    if "and" in condition:
        return {"and"}.union(*(_condition_ops(item) for item in condition["and"]))
    if "or" in condition:
        return {"or"}.union(*(_condition_ops(item) for item in condition["or"]))
    return {condition["op"]}


@pytest_asyncio.fixture
async def db_session():
    db_name = os.getenv("STEP5_DB_NAME")
    if not db_name:
        pytest.skip("Set STEP5_DB_NAME to run manufacturing-rule integration tests.")

    from app.config import settings

    url = URL.create(
        "mysql+aiomysql",
        username=settings.DB_USER,
        password=settings.DB_PASSWORD,
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=db_name,
        query={"charset": "utf8mb4"},
    )
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_database_contains_exactly_seven_valid_enabled_rules(db_session):
    rules = list((await db_session.execute(
        select(RiskRule).order_by(RiskRule.rule_id)
    )).scalars().all())
    assert [rule.rule_id for rule in rules] == list(EXPECTED_RULES)

    allowed_ops = {">", ">=", "<", "<=", "==", "!=", "in", "not_in", "between", "and", "or"}
    allowed_event_types = {"下单", "支付", "售后申请", "物流投诉", "通用"}
    allowed_categories = {"订单欺诈", "支付风险", "账户风险", "售后滥用", "地址风险", "物流风险"}
    for rule in rules:
        expected = EXPECTED_RULES[rule.rule_id]
        assert rule.rule_name == expected["name"]
        assert rule.rule_category == expected["category"]
        assert rule.event_type == expected["event_type"]
        assert rule.risk_level == expected["level"]
        assert rule.risk_score == expected["score"]
        assert rule.action == expected["action"]
        assert rule.priority == expected["priority"]
        assert rule.is_enabled == 1
        assert rule.deleted_at is None
        assert rule.description
        assert rule.event_type in allowed_event_types
        assert rule.rule_category in allowed_categories

        condition = json.loads(rule.rule_condition)
        fields = _condition_fields(condition)
        assert fields == expected["fields"]
        assert fields <= set(FEATURE_COLUMNS)
        assert "assessment_count" not in fields
        assert _condition_ops(condition) <= allowed_ops


@pytest.mark.asyncio
async def test_load_enabled_rules_keeps_priority_order_and_event_filter(db_session):
    all_rules = await load_enabled_rules(db_session)
    assert [rule.rule_id for rule in all_rules] == [
        "R001", "R006", "R003", "R004", "R002", "R005", "R007",
    ]
    purchase_rules = await load_enabled_rules(db_session, "下单")
    assert [rule.rule_id for rule in purchase_rules] == ["R003", "R005"]
    warranty_rules = await load_enabled_rules(db_session, "售后申请")
    assert [rule.rule_id for rule in warranty_rules] == ["R006", "R004", "R002", "R005", "R007"]
    diversion_rules = await load_enabled_rules(db_session, "物流投诉")
    assert [rule.rule_id for rule in diversion_rules] == ["R001", "R005"]


RULE_BOUNDARY_CASES = {
    "R001": [
        ({"addr_is_new": 1, "order_discount_rate": 1}, True),
        ({"addr_is_new": 0, "order_discount_rate": 1}, False),
        ({"addr_is_new": 1, "order_discount_rate": 0}, False),
    ],
    "R002": [
        ({"user_postsale_count": 9}, False),
        ({"user_postsale_count": 10}, True),
        ({"user_postsale_count": 11}, True),
    ],
    "R003": [
        ({"user_cancel_count": 29, "order_total_amount": 1_000_000}, True),
        ({"user_cancel_count": 30, "order_total_amount": 1_000_000}, False),
        ({"user_cancel_count": 29, "order_total_amount": 999_999}, False),
    ],
    "R004": [
        ({"order_pay_interval_sec": 157_679_999, "order_total_amount": 100_000}, False),
        ({"order_pay_interval_sec": 157_680_000, "order_total_amount": 100_000}, True),
        ({"order_pay_interval_sec": 157_680_000, "order_total_amount": 99_999}, False),
    ],
    "R005": [
        ({"addr_province_count": 1, "addr_total_count": 5}, False),
        ({"addr_province_count": 2, "addr_total_count": 5}, True),
        ({"addr_province_count": 2, "addr_total_count": 4}, False),
    ],
    "R006": [
        ({"order_sku_count": 2}, False),
        ({"order_sku_count": 3}, True),
        ({"order_sku_count": 4}, True),
    ],
    "R007": [
        ({"order_total_amount": 99_999, "order_category_count": 0}, False),
        ({"order_total_amount": 100_000, "order_category_count": 0}, True),
        ({"order_total_amount": 100_000, "order_category_count": 1}, False),
    ],
}


@pytest.mark.asyncio
@pytest.mark.parametrize("rule_id", list(EXPECTED_RULES))
async def test_each_rule_has_hit_non_hit_and_boundary_cases(db_session, rule_id):
    rule = (await db_session.execute(
        select(RiskRule).where(RiskRule.rule_id == rule_id)
    )).scalar_one()
    condition = json.loads(rule.rule_condition)
    results = [
        evaluate_condition(condition, features)
        for features, _ in RULE_BOUNDARY_CASES[rule_id]
    ]
    expected = [expected_result for _, expected_result in RULE_BOUNDARY_CASES[rule_id]]
    assert results == expected
    assert True in results
    assert False in results


async def _hit_ids(db_session, event_type: str, features: dict[str, float]) -> set[str]:
    rules = await load_enabled_rules(db_session, event_type)
    return {hit.rule_id for hit in match_rules(rules, features)}


@pytest.mark.asyncio
async def test_real_purchase_features_distinguish_normal_and_new_large_dealer(db_session):
    normal = await compute_all_features(db_session, "DLR001", "PO001", "华东-上海中心仓")
    risky = await compute_all_features(db_session, "DLR002", "PO002", "华北-北京临时交付点")
    assert "R003" not in await _hit_ids(db_session, "下单", normal)
    risky_rules = await load_enabled_rules(db_session, "下单")
    risky_hits = match_rules(risky_rules, risky)
    r003 = next(hit for hit in risky_hits if hit.rule_id == "R003")
    assert r003.risk_score == 75
    assert r003.action == "人工审核"


@pytest.mark.asyncio
async def test_real_warranty_features_distinguish_normal_and_high_frequency_risk(db_session):
    normal = await compute_all_features(db_session, "DLR001", "CLM001", "华东")
    normal_hits = await _hit_ids(db_session, "售后申请", normal)
    assert not ({"R002", "R004", "R006", "R007"} & normal_hits)

    for index in range(1, 10):
        db_session.add(WarrantyClaim(
            claim_id=f"STEP5-RISK-{index}",
            device_id="DEV005",
            dealer_id="DLR003",
            fault_desc="Step 5 高频高金额保修规则测试",
            claim_amount=250_000 if index == 9 else 2_000,
            photos=[] if index == 9 else ["evidence.jpg"],
            create_time=datetime.now(),
        ))
    await db_session.flush()

    risky = await compute_all_features(db_session, "DLR003", "STEP5-RISK-9", "华南")
    risky_hits = match_rules(await load_enabled_rules(db_session, "售后申请"), risky)
    hit_map = {hit.rule_id: (hit.risk_score, hit.action) for hit in risky_hits}
    assert {
        "R002": (70, "人工审核"),
        "R004": (75, "人工审核"),
        "R006": (92, "拒绝"),
        "R007": (45, "标记"),
    }.items() <= hit_map.items()


@pytest.mark.asyncio
async def test_real_region_features_distinguish_normal_and_cross_region(db_session):
    normal = await compute_all_features(db_session, "DLR001", "CRR001", "华东")
    risky = await compute_all_features(db_session, "DLR004", "CRR002", "华北")
    assert "R001" not in await _hit_ids(db_session, "物流投诉", normal)
    risky_hits = match_rules(await load_enabled_rules(db_session, "物流投诉"), risky)
    r001 = next(hit for hit in risky_hits if hit.rule_id == "R001")
    assert r001.risk_score == 95
    assert r001.action == "拒绝"


@pytest.mark.asyncio
async def test_blacklisted_dealer_stops_before_run_risk_check(db_session, monkeypatch):
    from app.schemas import RiskCheckRequest
    from app.service import event as event_module

    db_session.add(RiskBlacklist(
        blacklist_type="用户",
        blacklist_value="DLR001",
        reason="Step 5 独立验证黑经销商",
        expire_time=None,
        deleted_at=None,
    ))
    await db_session.flush()

    run_mock = AsyncMock(side_effect=AssertionError("黑名单经销商不得进入 run_risk_check"))
    monkeypatch.setattr(event_module, "run_risk_check", run_mock)

    response = await event_module.process_event(db_session, RiskCheckRequest(
        event_type="下单",
        source_id="PO001",
        user_id="DLR001",
    ))
    assert response.decision == "拒绝"
    assert response.blocked_by == "用户"
    assert response.assessment_id == "blacklist_reject"
    assert run_mock.await_count == 0
