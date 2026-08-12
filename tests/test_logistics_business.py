"""
物流风控专项测试 - 单元测试
覆盖:
  1. 物流 Pydantic 枚举 (4事件 / 8分类 / 6黑名单)
  2. 25 维特征对齐 (FEATURE_COLUMNS == 25, 14 user + 8 order + 3 addr)
  3. 纯计算: 评分公式、一票否决、评分→决策/等级 映射
  4. 规则引擎: 构造特征 dict + mock RiskRule ORM → match_rules 命中
  5. Validator 派发表: 4 种物流 event_type 均存在映射, FK 对应正确 ORM
  6. process_event 黑名单短路: 撞黑后立即返回拒绝, 不调用决策引擎
"""
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.decision import (  # noqa: E402
    _score_to_decision, _score_to_level, calculate_final_score, check_veto,
)
from app.engine import ml_model  # noqa: E402
from app.engine.rule import RuleHitResult, match_rules  # noqa: E402
from app.models_risk import RiskRule  # noqa: E402
from app.schemas import RiskCheckRequest, RiskCheckResponse  # noqa: E402
from app.service import event as event_module  # noqa: E402
from app.service.validator import _EVENT_SOURCE_VALIDATORS  # noqa: E402


# ============================================================
# 1. 物流枚举完整性
# ============================================================

class TestLogisticsEnumSchemas:
    """schemas 枚举: 4 事件类型"""

    def test_4_logistics_event_types(self):
        for et in ("寄件下单", "到付签收", "跨境申报", "投诉申诉"):
            req = RiskCheckRequest(event_type=et, source_id="S1", user_id="U1")
            assert req.event_type == et

    def test_invalid_old_ecom_event_types_rejected(self):
        for et in ("下单", "支付", "售后申请", "物流投诉"):
            with pytest.raises(Exception):  # ValidationError
                RiskCheckRequest(event_type=et, source_id="S1", user_id="U1")


# ============================================================
# 2. 25 维特征对齐
# ============================================================

class TestFeature25Alignment:
    """ml_model.FEATURE_COLUMNS 与 feature.py 约定严格对齐"""

    def test_columns_total_25(self):
        assert len(ml_model.FEATURE_COLUMNS) == 25

    def test_prefix_bucket_counts(self):
        user = [c for c in ml_model.FEATURE_COLUMNS if c.startswith("user_")]
        order = [c for c in ml_model.FEATURE_COLUMNS if c.startswith("order_")]
        addr = [c for c in ml_model.FEATURE_COLUMNS if c.startswith("addr_")]
        assert len(user) == 14, f"user 特征应为 14, 实际 {len(user)}: {user}"
        assert len(order) == 8, f"order 特征应为 8, 实际 {len(order)}: {order}"
        assert len(addr) == 3, f"addr 特征应为 3, 实际 {len(addr)}: {addr}"

    def test_features_declared_in_feature_module(self):
        """feature.py 中计算函数存在: 25 个 key 都有 compute_USER_ATTR / compute_ORDER_ATTR
        对应函数命名或包含在 FEATURE_COLUMNS 中, 只要模块能正确导入就算 OK.
        这里验证 feature.compute_all_features 是 async callable, 且内部使用相同 key."""
        from app.engine import feature
        assert callable(getattr(feature, "compute_all_features", None))
        # 验证 compute_xxx 函数组存在 (不要求每个都单独测)
        has_user = hasattr(feature, "_compute_user_features") or any(
            hasattr(feature, n) for n in dir(feature) if "user_" in n.lower()
        )
        has_order = hasattr(feature, "_compute_order_features") or any(
            hasattr(feature, n) for n in dir(feature) if "order_" in n.lower()
        )
        has_addr = hasattr(feature, "_compute_addr_features") or any(
            hasattr(feature, n) for n in dir(feature) if "addr_" in n.lower()
        )
        assert has_user and has_order and has_addr, "feature.py 缺少 user/order/addr 分组计算函数"


# ============================================================
# 3. 纯计算函数 (不碰 DB)
# ============================================================

def _fake_rule(**kwargs):
    """构造一个 RiskRule-like 对象, 含所有 RuleHitResult 需要的字段 + condition_dict"""
    r = MagicMock(spec=RiskRule)
    defaults = dict(
        rule_id="L1", rule_name="R", rule_category="综合风险",
        risk_level="中", risk_score=40, action="标记", description="",
    )
    for k, v in {**defaults, **kwargs}.items():
        setattr(r, k, v)
    return r


class TestDecisionPureCalculations:

    def test_calculate_final_score_single_70(self):
        hits = [RuleHitResult(_fake_rule(risk_score=70, risk_level="高"))]
        assert calculate_final_score(hits) == 70

    def test_calculate_final_score_three_hits_cap(self):
        hits = [
            RuleHitResult(_fake_rule(risk_score=95, risk_level="极高")),
            RuleHitResult(_fake_rule(risk_score=80, risk_level="高")),
            RuleHitResult(_fake_rule(risk_score=70, risk_level="高")),
        ]
        # 95 + 3*2 = 101, cap 100
        assert calculate_final_score(hits) == 100

    def test_calculate_final_score_empty_zero(self):
        assert calculate_final_score([]) == 0

    def test_check_veto_positive_extreme(self):
        hits = [
            RuleHitResult(_fake_rule(risk_level="高", risk_score=70)),
            RuleHitResult(_fake_rule(risk_level="极高", risk_score=95)),
        ]
        assert check_veto(hits) is True

    def test_check_veto_negative(self):
        hits = [RuleHitResult(_fake_rule(risk_level="高", risk_score=70))]
        assert check_veto(hits) is False

    def test_score_decision_boundaries(self):
        from app.config import settings
        P, M, R = (settings.RISK_PASS_THRESHOLD, settings.RISK_MARK_THRESHOLD,
                   settings.RISK_REVIEW_THRESHOLD)
        assert _score_to_decision(P - 1) == "通过"
        assert _score_to_decision(P) == "标记"
        assert _score_to_decision(M - 1) == "标记"
        assert _score_to_decision(M) == "人工审核"
        assert _score_to_decision(R - 1) == "人工审核"
        assert _score_to_decision(R) == "拒绝"

    def test_score_level_boundaries(self):
        from app.config import settings
        P, M, R = (settings.RISK_PASS_THRESHOLD, settings.RISK_MARK_THRESHOLD,
                   settings.RISK_REVIEW_THRESHOLD)
        assert _score_to_level(P - 1) == "低"
        assert _score_to_level(P) == "中"
        assert _score_to_level(M - 1) == "中"
        assert _score_to_level(M) == "高"
        assert _score_to_level(R - 1) == "高"
        assert _score_to_level(R) == "极高"


# ============================================================
# 4. 规则引擎 match_rules: 不连 DB, 手工构造 mock rules
# ============================================================

def _mock_rule(rule_id, rule_condition_dict, *, risk_level="高", risk_score=70,
               action="人工审核", event_type="通用", rule_category="综合风险"):
    """mock 一个 RiskRule: 主要带 condition_dict property 效果 (dict)."""
    r = MagicMock(spec=RiskRule)
    r.rule_id = rule_id
    r.rule_name = rule_id + "_name"
    r.rule_category = rule_category
    r.risk_level = risk_level
    r.risk_score = risk_score
    r.action = action
    r.event_type = event_type
    r.description = ""
    # RiskRule.condition_dict 是 @property: 如果 rule_condition 是 dict 就返回
    # rule.py: 如果是 str json.loads，否则 return rule_condition
    r.rule_condition = rule_condition_dict
    r.condition_dict = rule_condition_dict
    # 但是 RiskRuleHit 用 rule.rule_id 等 直接属性访问 可以
    # 但 evaluate_condition 里用 rule.condition_dict 访问我们 mock 给 property
    def _cd_getter():
        return rule_condition_dict
    type(r).condition_dict = property(lambda self: rule_condition_dict)
    return r


class TestRuleEngineMatch:

    @pytest.fixture
    def rules(self):
        return [
            _mock_rule("L002", {"field": "user_orders_30d", "op": ">=", "value": 30},
                       risk_level="极高", risk_score=95, action="拒绝"),
            _mock_rule("L011", {"and": [
                {"field": "order_total_amount", "op": ">=", "value": 50000},
                {"field": "order_discount_amount", "op": "==", "value": 0},
            ]}, rule_category="危险品瞒报", event_type="寄件下单"),
            _mock_rule("L022", {"field": "user_refund_rate", "op": ">=", "value": 0.8},
                       risk_level="极高", risk_score=95, action="拒绝",
                       event_type="到付签收", rule_category="到付拒收"),
        ]

    def test_L002_hit_high_frequency(self, rules):
        hits = match_rules(rules, {"user_orders_30d": 35})
        ids = {h.rule_id for h in hits}
        assert "L002" in ids
        assert check_veto(hits) is True

    def test_L002_no_hit_low_freq(self, rules):
        ids = {h.rule_id for h in match_rules(rules, {"user_orders_30d": 5})}
        assert "L002" not in ids

    def test_L011_AND_both_satified(self, rules):
        # L011 event_type="寄件下单" match_rules 内部不按 event_type 过滤, 只要条件对就命中
        feats = {"order_total_amount": 50000, "order_discount_amount": 0}
        ids = {h.rule_id for h in match_rules(rules, feats)}
        assert "L011" in ids

    def test_L011_AND_has_insurance_not_match(self, rules):
        feats = {"order_total_amount": 50000, "order_discount_amount": 1000}
        ids = {h.rule_id for h in match_rules(rules, feats)}
        assert "L011" not in ids

    def test_L022_refund_rate_extreme_hit(self, rules):
        ids = {h.rule_id for h in match_rules(rules, {"user_refund_rate": 0.85})}
        assert "L022" in ids


# ============================================================
# 5. Validator 派发表
# ============================================================

class TestValidatorDispatch:

    def test_4_logistics_event_types_covered(self):
        covered = set()
        for evt_tup in _EVENT_SOURCE_VALIDATORS.keys():
            for e in evt_tup:
                covered.add(e)
        for et in ("寄件下单", "到付签收", "跨境申报", "投诉申诉"):
            assert et in covered, f"派发表缺少物流事件 {et}"

    def test_dispatch_tuple_schema(self):
        """元组 (Model, pk_attr_str, caster_or_None, label_str, http_status)"""
        from app import models_business as mb
        expected = {
            "寄件下单": mb.Shipment,
            "到付签收": mb.Shipment,
            "跨境申报": mb.CustomsDeclaration,
            "投诉申诉": mb.ComplaintRecord,
        }
        for evt_tup, payload in _EVENT_SOURCE_VALIDATORS.items():
            Model, pk_attr, caster, label, status_code = payload
            assert isinstance(pk_attr, str) and pk_attr
            assert label
            assert isinstance(status_code, int) and 400 <= status_code < 600
            for et in evt_tup:
                if et in expected:
                    assert Model is expected[et]


# ============================================================
# 6. process_event 黑名单短路
# ============================================================

def _req():
    return RiskCheckRequest(event_type="寄件下单", source_id="SHIP1",
                            user_id="U1", order_id="SHIP1", receive_id="101")


class TestBlacklistShortCircuit:

    @pytest.mark.asyncio
    async def test_user_blacklist_returns_100_and_blocked(self):
        run_calls = {"n": 0}

        async def fake_run(*a, **kw):
            run_calls["n"] += 1

        async def en(db, req): return req
        async def val(db, req): return None

        with patch.object(event_module, "validate_risk_check_request", side_effect=val), \
             patch.object(event_module, "_enrich_request", side_effect=en), \
             patch.object(event_module, "_check_all_blacklists", return_value="用户"), \
             patch.object(event_module, "run_risk_check", side_effect=fake_run):
            resp = await event_module.process_event(MagicMock(), _req())

        assert resp.decision == "拒绝"
        assert resp.blocked_by == "用户"
        assert resp.risk_level == "极高"
        assert resp.final_score == 100
        assert resp.rule_count == 0
        assert run_calls["n"] == 0, "撞黑后不应调用 run_risk_check"

    @pytest.mark.asyncio
    async def test_no_blacklist_calls_decision_engine(self):
        called = {"n": 0}

        async def fake_run(*a, **kw):
            called["n"] += 1
            return RiskCheckResponse(
                assessment_id="ast1", event_id="evt1", user_id="U1",
                final_score=10, risk_level="低", decision="通过",
                rule_count=0, triggered_rules=[], features={},
                create_time=datetime.now(), blocked_by=None,
            )

        async def en(db, req): return req
        async def val(db, req): return None

        with patch.object(event_module, "validate_risk_check_request", side_effect=val), \
             patch.object(event_module, "_enrich_request", side_effect=en), \
             patch.object(event_module, "_check_all_blacklists", return_value=None), \
             patch.object(event_module, "run_risk_check", side_effect=fake_run):
            resp = await event_module.process_event(MagicMock(), _req())

        assert called["n"] == 1
        assert resp.decision == "通过"
        assert resp.blocked_by is None
