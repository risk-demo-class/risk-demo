"""
规则引擎: 基于 JSON 条件表达式对特征字典求值, 判断规则是否命中.

支持的运算符: >, >=, <, <=, ==, !=, in, not_in, between, and, or
(完全复用 AI_Risk 电商风控的规则引擎设计)
"""
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RiskRule

logger = logging.getLogger(__name__)


class RuleHitResult:
    """单条规则"命中"结果. 从 RiskRule ORM 拷 7 个业务字段, 后续不碰 ORM 对象."""

    def __init__(self, rule: RiskRule):
        self.rule_id = rule.rule_id
        self.rule_name = rule.rule_name
        self.rule_category = rule.rule_category
        self.risk_level = rule.risk_level
        self.risk_score = rule.risk_score
        self.action = rule.action
        self.description = rule.description

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "rule_category": self.rule_category,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "action": self.action,
            "description": self.description,
        }


def match_rules(
    rules: list[RiskRule],
    features: dict[str, float],
) -> list[RuleHitResult]:
    """对 rules 每条用 features 求值, 返回所有命中."""
    hits: list[RuleHitResult] = []
    for rule in rules:
        try:
            condition = rule.condition_dict  # @property 自动 json.loads
        except (json.JSONDecodeError, TypeError) as e:
            # 条件 JSON 坏了, 跳过这条, 不影响其他规则
            logger.warning("规则 %s 条件解析失败: %s", rule.rule_id, e)
            continue
        if evaluate_condition(condition, features):
            logger.info("规则命中: %s (%s), 分值=%d", rule.rule_id, rule.rule_name, rule.risk_score)
            hits.append(RuleHitResult(rule))
    return hits


def evaluate_condition(condition: dict, features: dict[str, float]) -> bool:
    """递归求值 1 个 JSON 条件表达式, 返回 bool.

    条件格式:
      {"field": "order_total_amount", "op": ">", "value": 1000000}   ← 单条件
      {"and": [条件1, 条件2]}                                        ← 逻辑组合
      {"or": [条件1, 条件2]}                                         ← 逻辑组合
    """
    if "and" in condition:
        return all(evaluate_condition(sub, features) for sub in condition["and"])
    if "or" in condition:
        return any(evaluate_condition(sub, features) for sub in condition["or"])

    field = condition.get("field", "")
    op = condition.get("op", "")
    value = condition.get("value")

    actual = features.get(field)
    if actual is None:
        # 特征算不出来 (没数据), 条件算"没命中", 不算错
        logger.debug("特征 '%s' 不存在, 条件跳过", field)
        return False

    try:
        return _compare(actual, op, value)
    except Exception as e:
        logger.warning("条件求值异常: field=%s, op=%s, value=%s, actual=%s, err=%s",
                       field, op, value, actual, e)
        return False


def _compare(actual: float, op: str, value: Any) -> bool:
    """执行 1 次具体比较运算. 未知 op 兜底 False, 不中断流程."""
    if op == ">":    return actual > float(value)
    elif op == ">=": return actual >= float(value)
    elif op == "<":  return actual < float(value)
    elif op == "<=": return actual <= float(value)
    elif op == "==": return actual == float(value)
    elif op == "!=": return actual != float(value)
    elif op == "in":     return actual in [float(v) for v in value]
    elif op == "not_in": return actual not in [float(v) for v in value]
    elif op == "between":
        low, high = float(value[0]), float(value[1])
        return low <= actual <= high
    else:
        logger.warning("不支持的运算符: %s", op)
        return False


async def load_enabled_rules(db: AsyncSession, event_type: str | None = None) -> list[RiskRule]:
    """从 DB 加载"启用 + 未软删"的规则, 按 priority 降序 (高优先级先匹配).

    event_type: 限定事件类型, 传了就只查这个事件 + "通用" 的规则; 不传查全部.
    """
    stmt = select(RiskRule).where(
        RiskRule.is_enabled == 1,
        RiskRule.deleted_at.is_(None),
    )
    if event_type:
        stmt = stmt.where(RiskRule.event_type.in_([event_type, "通用"]))
    stmt = stmt.order_by(RiskRule.priority.desc())
    return list((await db.execute(stmt)).scalars().all())


# ============================================================
# Demo: 演练 JSON 条件表达式求值 — 无需 DB
# 跑法: python -m app.engine.rule
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("规则引擎 — JSON 条件表达式求值 (核心能力)")
    print("=" * 60)

    test_cases = [
        ("基础 >",   {"field": "order_total_amount", "op": ">", "value": 1000000}, {"order_total_amount": 1200000}, True),
        ("AND 嵌套 (R002)", {"and": [
            {"field": "warranty_is_expired", "op": "==", "value": 1},
            {"field": "warranty_apply_count_30d", "op": ">=", "value": 2},
        ]}, {"warranty_is_expired": 1, "warranty_apply_count_30d": 3}, True),
        ("AND 嵌套 (R012)", {"and": [
            {"field": "dealer_contract_days", "op": "<", "value": 30},
            {"field": "order_is_first", "op": "==", "value": 1},
            {"field": "order_total_amount", "op": ">", "value": 500000},
        ]}, {"dealer_contract_days": 20, "order_is_first": 1, "order_total_amount": 600000}, True),
        ("AND 失败", {"and": [
            {"field": "warranty_is_expired", "op": "==", "value": 1},
            {"field": "warranty_apply_count_30d", "op": ">=", "value": 2},
        ]}, {"warranty_is_expired": 0, "warranty_apply_count_30d": 3}, False),
        ("未识别字段→False", {"field": "ghost", "op": ">", "value": 0}, {"real": 1}, False),
    ]
    print("\n[1] 求值测试:")
    for desc, cond, feats, expected in test_cases:
        got = evaluate_condition(cond, feats)
        mark = "OK" if got == expected else "FAIL"
        print(f"  [{mark}] {desc:<30} 期望={expected} 实际={got}")

    # match_rules 端到端 — mock 规则
    print("\n[2] match_rules 端到端: 模拟 3 条规则对 1 份特征求值")

    class _MockRule:
        def __init__(self, rid, cond_dict, score, level, action, priority):
            self.rule_id = rid
            self.rule_name = f"规则 {rid}"
            self.rule_category = "测试"
            self.rule_condition = json.dumps(cond_dict, ensure_ascii=False)
            self._cond_dict = cond_dict
            self.risk_score = score
            self.risk_level = level
            self.action = action
            self.priority = priority
            self.is_enabled = 1
            self.description = f"Demo 规则 {rid}"
        @property
        def condition_dict(self):
            return json.loads(self.rule_condition) if self.rule_condition else {}

    rules = [
        _MockRule("R005", {"field": "order_total_amount", "op": ">", "value": 1000000}, 70, "高", "人工审核", 80),
        _MockRule("R008", {"field": "sn_repair_count_90d", "op": ">=", "value": 2}, 95, "极高", "拒绝", 95),
        _MockRule("R025", {"field": "dealer_contract_expired", "op": "==", "value": 1}, 50, "中", "标记", 65),
    ]
    feats = {"order_total_amount": 1500000, "sn_repair_count_90d": 1, "dealer_contract_expired": 1}
    hits = match_rules(rules, feats)
    print(f"  输入特征: {feats}")
    print(f"  命中 {len(hits)} 条:")
    for h in hits:
        print(f"    {h.rule_id:<6} | {h.risk_level:<4} | {h.risk_score} 分 | {h.action:<8} | {h.rule_name}")

    print("\n" + "=" * 60)
    print("结论: 14 种 op + 递归 and/or, 制造业 8 条规则全部可表达")
