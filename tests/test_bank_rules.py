"""银行信贷风控 - 规则库测试 (RED 基线).

1. DB 加载的 30 条规则必须是银行规则 (6 大场景分类 + 银行特征条件)
2. 银行规则命中行为 (多头借贷/负债率/逾期史) + 一票否决
"""
import logging
from types import SimpleNamespace

import pytest

from app.engine.decision import check_veto
from app.engine.rule import match_rules
from tests.test_bank_features import BANK_FEATURE_COLUMNS

BANK_CATEGORIES = ["欺诈风险", "信用风险", "反洗钱", "账户风险", "贷后风险", "合规风险"]


def _mock_rule(rid, condition_dict, score=50, level="中", action="标记", name="规则", category="信用风险"):
    rule = SimpleNamespace(
        rule_id=rid, rule_name=name, rule_category=category,
        risk_level=level, risk_score=score, action=action,
        description=f"描述-{rid}", priority=0,
    )
    rule.condition_dict = condition_dict
    return rule


# ============================================================
# 1. DB 规则库 (集成测试, 需要 init_db 后的真数据)
# ============================================================

def test_rules_loaded_with_bank_categories():
    """init_db 后规则库非空且全部为银行分类."""
    import asyncio
    from app.database import AsyncSessionLocal, async_engine
    from app.engine.rule import load_enabled_rules

    async def _load():
        async with AsyncSessionLocal() as s:
            return await load_enabled_rules(s)

    rules = asyncio.run(_load())
    asyncio.run(async_engine.dispose())
    assert len(rules) >= 30, f"应加载至少 30 条银行规则, 当前 {len(rules)}"
    categories = {r.rule_category for r in rules}
    assert categories <= set(BANK_CATEGORIES), f"存在非银行分类: {categories - set(BANK_CATEGORIES)}"


def test_rules_use_bank_feature_fields():
    """规则条件引用的特征字段必须是银行 25 维特征名."""
    import asyncio
    from app.database import AsyncSessionLocal, async_engine
    from app.engine.rule import load_enabled_rules

    async def _load():
        async with AsyncSessionLocal() as s:
            return await load_enabled_rules(s)

    rules = asyncio.run(_load())
    asyncio.run(async_engine.dispose())
    bad = []
    for r in rules:
        for cond in r.condition_dict.get("rules", [r.condition_dict]):
            field = cond.get("field")
            if field and field not in BANK_FEATURE_COLUMNS:
                bad.append((r.rule_id, field))
    assert not bad, f"规则引用了非银行特征字段: {bad}"


# ============================================================
# 2. 银行规则命中行为 (纯函数, 无 DB)
# ============================================================

class TestBankRuleHits:
    def test_multi_loan_rule_hits(self):
        """多头借贷: 近 7 天申请 >= 3 → 命中."""
        rule = _mock_rule("R101", {"field": "cust_loans_7d", "op": ">=", "value": 3}, score=70, level="高", category="欺诈风险")
        hits = match_rules([rule], {"cust_loans_7d": 4, "cust_total_loans": 10})
        assert len(hits) == 1 and hits[0].rule_id == "R101"

    def test_debt_ratio_rule_hits(self):
        """负债率过高: loan_debt_ratio >= 0.5 → 信用风险命中."""
        rule = _mock_rule("R201", {"field": "loan_debt_ratio", "op": ">=", "value": 0.5}, score=75, level="高", category="信用风险")
        hits = match_rules([rule], {"loan_debt_ratio": 0.6})
        assert len(hits) == 1 and hits[0].rule_category == "信用风险"

    def test_overdue_history_rule_hits(self):
        """历史逾期: cust_overdue_rate >= 0.3 → 命中."""
        rule = _mock_rule("R202", {"field": "cust_overdue_rate", "op": ">=", "value": 0.3}, score=80, level="高", category="信用风险")
        assert len(match_rules([rule], {"cust_overdue_rate": 0.5})) == 1

    def test_veto_rule_forces_reject(self):
        """一票否决: 极高规则命中 → check_veto True."""
        rule = _mock_rule("R205", {"field": "cust_reject_count", "op": ">=", "value": 5}, score=95, level="极高", category="信用风险")
        hits = match_rules([rule], {"cust_reject_count": 6})
        assert check_veto(hits) is True

    def test_no_hit_on_normal_feature(self):
        """正常客户特征不命中极高规则."""
        rule = _mock_rule("R205", {"field": "cust_reject_count", "op": ">=", "value": 5}, score=95, level="极高", category="信用风险")
        assert match_rules([rule], {"cust_reject_count": 0}) == []