"""
规则引擎: 基于 JSON 条件表达式对特征字典求值, 判断规则是否命中.

参照 ai_risk/app/engine/rule.py, 改 import 为 TelecomRiskRule.
支持的运算符: >, >=, <, <=, ==, !=, in, not_in, between, and, or

电信规则示例 (见 sql/init_risk_tables.sql):
  R001 GOIP短时高频: {"field":"cdr_out_count_1h","op":">=","value":20}
  R003 猫池一机多卡: {"field":"dev_cards_on_imei","op":">=","value":5}
"""
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models_risk import TelecomRiskRule

logger = logging.getLogger(__name__)


class RuleScoreLevelMismatchError(ValueError):
    """风险等级跟分数不匹配 (业务校验失败)."""


def validate_rule_score_level(risk_level: str, risk_score: int) -> None:
    """校验 risk_score 是否落在 risk_level 对应区间."""
    if risk_level not in settings.RISK_LEVEL_SCORE_MAP:
        raise RuleScoreLevelMismatchError(
            f"未知风险等级: {risk_level}, 应是 {list(settings.RISK_LEVEL_SCORE_MAP.keys())} 之一"
        )
    if not isinstance(risk_score, int) or not (0 <= risk_score <= 100):
        raise RuleScoreLevelMismatchError(f"risk_score 必须是 0-100 整数, 当前 {risk_score!r}")
    low, high = settings.RISK_LEVEL_SCORE_MAP[risk_level]
    if not (low <= risk_score <= high):
        raise RuleScoreLevelMismatchError(
            f"风险等级 {risk_level} 对应区间 [{low}, {high}], 当前 risk_score={risk_score} 越界"
        )


class RuleHitResult:
    """单条规则"命中"结果. 从 TelecomRiskRule ORM 拷 7 个业务字段."""

    def __init__(self, rule: TelecomRiskRule):
        self.rule_id = rule.rule_id
        self.rule_name = rule.rule_name
        self.rule_category = rule.rule_category
        self.risk_level = rule.risk_level
        self.risk_score = rule.risk_score
        self.action = rule.action
        self.description = rule.description

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id, "rule_name": self.rule_name,
            "rule_category": self.rule_category, "risk_level": self.risk_level,
            "risk_score": self.risk_score, "action": self.action,
            "description": self.description,
        }


def match_rules(
    rules: list[TelecomRiskRule],
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
    """递归求值 JSON 条件表达式, 返回 bool.

    单条件: {"field":"cdr_out_count_1h","op":">=","value":20}
    组合:   {"and":[条件1, 条件2]}  /  {"or":[条件1, 条件2]}
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
        return False
    try:
        return _compare(actual, op, value)
    except Exception as e:
        logger.warning("条件求值异常: field=%s, op=%s, err=%s", field, op, e)
        return False


def _compare(actual: float, op: str, value: Any) -> bool:
    """执行 1 次比较. 未知 op 兜底 False."""
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


async def load_enabled_rules(db: AsyncSession, event_type: str | None = None) -> list[TelecomRiskRule]:
    """加载"启用 + 未软删"的规则, 按 priority 降序.

    event_type: 传了就查该事件 + "通用"; 不传查全部.
    """
    stmt = select(TelecomRiskRule).where(
        TelecomRiskRule.is_enabled == 1,
        TelecomRiskRule.deleted_at.is_(None),
    )
    if event_type:
        stmt = stmt.where(TelecomRiskRule.event_type.in_([event_type, "通用"]))
    stmt = stmt.order_by(TelecomRiskRule.priority.desc())
    return list((await db.execute(stmt)).scalars().all())


if __name__ == "__main__":
    from types import SimpleNamespace

    print("=" * 60)
    print("电信规则引擎 — JSON 条件求值 Demo")
    print("=" * 60)
    cases = [
        ("GOIP短时高频", {"field": "cdr_out_count_1h", "op": ">=", "value": 20},
         {"cdr_out_count_1h": 30}, True),
        ("猫池一机多卡", {"field": "dev_cards_on_imei", "op": ">=", "value": 5},
         {"dev_cards_on_imei": 5}, True),
        ("一证多卡+渠道异常", {"and": [
            {"field": "cust_card_count", "op": ">=", "value": 5},
            {"field": "channel_open_count_1h", "op": ">=", "value": 8},
        ]}, {"cust_card_count": 6, "channel_open_count_1h": 10}, True),
        ("国际诈骗 OR 物联网突增", {"or": [
            {"field": "cdr_intl_incoming_24h", "op": ">=", "value": 10},
            {"field": "iot_data_burst_ratio", "op": ">=", "value": 10},
        ]}, {"cdr_intl_incoming_24h": 20, "iot_data_burst_ratio": 0}, True),
        ("未命中", {"field": "cdr_out_count_1h", "op": ">=", "value": 20},
         {"cdr_out_count_1h": 3}, False),
    ]
    for desc, cond, feats, expected in cases:
        got = evaluate_condition(cond, feats)
        mark = "OK" if got == expected else "FAIL"
        print(f"  [{mark}] {desc:<20} 期望={expected} 实际={got}")
    print("=" * 60)
