"""规则引擎测试: JSON 条件求值 + 规则匹配"""
import json

from app.engine.rule import RuleHitResult, evaluate_condition, match_rules


def test_basic_operators():
    assert evaluate_condition({"field": "order_amount", "op": ">=", "value": 100000}, {"order_amount": 150000})
    assert not evaluate_condition({"field": "order_amount", "op": ">=", "value": 100000}, {"order_amount": 50000})
    assert evaluate_condition({"field": "order_is_night", "op": "==", "value": 1}, {"order_is_night": 1})
    assert evaluate_condition({"field": "addr_ip_risk", "op": "!=", "value": 0}, {"addr_ip_risk": 1})
    assert evaluate_condition({"field": "order_amount", "op": "between", "value": [10000, 50000]}, {"order_amount": 30000})
    assert evaluate_condition({"field": "purpose", "op": "in", "value": [1, 2, 3]}, {"purpose": 2})


def test_and_or_nesting():
    cond = {
        "and": [
            {"field": "user_applications_60d", "op": ">=", "value": 3},
            {"or": [
                {"field": "order_hard_query_6m", "op": ">=", "value": 6},
                {"field": "order_five_level_risk", "op": "==", "value": 1},
            ]},
        ]
    }
    feats = {"user_applications_60d": 4, "order_hard_query_6m": 8, "order_five_level_risk": 0}
    assert evaluate_condition(cond, feats)


def test_missing_field_not_hit():
    assert not evaluate_condition({"field": "ghost", "op": ">", "value": 0}, {"real": 1})


class _MockRule:
    def __init__(self, rid, cond, score=70, level="高", action="人工审核", priority=10):
        self.rule_id = rid
        self.rule_name = f"规则{rid}"
        self.rule_category = "信贷欺诈"
        self.rule_condition = json.dumps(cond, ensure_ascii=False)
        self.risk_score = score
        self.risk_level = level
        self.action = action
        self.priority = priority
        self.description = ""

    @property
    def condition_dict(self):
        return json.loads(self.rule_condition)


def test_match_rules_returns_hits():
    rules = [
        _MockRule("R001", {"field": "order_amount", "op": ">=", "value": 100000}, 65, "高"),
        _MockRule("R002", {"field": "order_is_night", "op": "==", "value": 1}, 45, "中"),
    ]
    hits = match_rules(rules, {"order_amount": 200000, "order_is_night": 0})
    assert [h.rule_id for h in hits] == ["R001"]
    assert isinstance(hits[0], RuleHitResult)


def test_match_rules_bad_condition_skipped():
    bad = _MockRule("R-BAD", {"field": "x"})  # 条件缺 op/value, 求值不抛
    bad.rule_condition = "{not-json"
    hits = match_rules([bad], {"x": 1})
    assert hits == []
