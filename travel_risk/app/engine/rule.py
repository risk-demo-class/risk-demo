"""
规则引擎: 基于 JSON 条件表达式对特征字典求值, 判断规则是否命中.

支持的运算符: >, >=, <, <=, ==, !=, in, not_in, between, and, or
"""
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import RiskRule

logger = logging.getLogger(__name__)


class RuleScoreLevelMismatchError(ValueError):
    """风险等级跟分数不匹配 (业务校验失败)."""


def validate_rule_score_level(risk_level: str, risk_score: int) -> None:
    """校验 risk_score 是否落在 risk_level 对应区间. 不匹配抛 RuleScoreLevelMismatchError."""
    if risk_level not in settings.RISK_LEVEL_SCORE_MAP:
        raise RuleScoreLevelMismatchError(
            f"未知风险等级: {risk_level}, 应该是 {list(settings.RISK_LEVEL_SCORE_MAP.keys())} 之一"
        )
    if not isinstance(risk_score, int) or not (0 <= risk_score <= 100):
        raise RuleScoreLevelMismatchError(
            f"risk_score 必须是 0-100 整数, 当前 {risk_score!r}"
        )
    low, high = settings.RISK_LEVEL_SCORE_MAP[risk_level]
    if not (low <= risk_score <= high):
        raise RuleScoreLevelMismatchError(
            f"风险等级 {risk_level} 对应分数区间 [{low}, {high}], "
            f"当前 risk_score={risk_score} 越界"
        )


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
            condition = rule.condition_dict
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("规则 %s 条件解析失败: %s", rule.rule_id, e)
            continue
        if evaluate_condition(condition, features):
            logger.info("规则命中: %s (%s), 分值=%d", rule.rule_id, rule.rule_name, rule.risk_score)
            hits.append(RuleHitResult(rule))
    return hits


def evaluate_condition(condition: dict, features: dict[str, float]) -> bool:
    """递归求值 1 个 JSON 条件表达式, 返回 bool."""
    if "and" in condition:
        return all(evaluate_condition(sub, features) for sub in condition["and"])
    if "or" in condition:
        return any(evaluate_condition(sub, features) for sub in condition["or"])

    field = condition.get("field", "")
    op = condition.get("op", "")
    value = condition.get("value")

    actual = features.get(field)
    if actual is None:
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
    """从 DB 加载"启用 + 未软删"的规则, 按 priority 降序.

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
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("规则引擎 — JSON 条件表达式求值 (核心能力)")
    print("=" * 60)

    test_cases = [
        ("基础 >=",         {"field": "order_total_amount", "op": ">=", "value": 20000}, {"order_total_amount": 30000}, True),
        ("AND 嵌套 (R027)", {"and": [
            {"field": "user_refund_rate", "op": ">=", "value": 0.3},
            {"field": "user_claim_count", "op": ">=", "value": 1},
            {"field": "user_device_count", "op": ">=", "value": 2},
        ]}, {"user_refund_rate": 0.5, "user_claim_count": 2, "user_device_count": 3}, True),
        ("OR 嵌套",         {"or": [
            {"field": "user_total_bookings", "op": ">=", "value": 100},
            {"field": "user_total_bookings", "op": "<", "value": 1},
        ]}, {"user_total_bookings": 0}, True),
        ("未识别字段→False", {"field": "ghost", "op": ">", "value": 0}, {"real": 1}, False),
    ]
    for desc, cond, feats, expected in test_cases:
        got = evaluate_condition(cond, feats)
        mark = "OK" if got == expected else "FAIL"
        print(f"  [{mark}] {desc:<30} 期望={expected} 实际={got}")
