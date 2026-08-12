"""
规则引擎: 基于 JSON 条件表达式对特征字典求值, 判断规则是否命中.

支持 14 种运算符: >=, >, <=, <, ==, !=, in, not_in, contains, not_contains,
                 regex, between, startswith, endswith
以及 and / or 逻辑组合 (可递归嵌套).
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.models import RiskRule

logger = logging.getLogger(__name__)


# ============================================================
# 规则命中结果
# ============================================================

@dataclass
class RuleHitResult:
    """单条规则"命中"结果. 从 RiskRule ORM 拷 7 个业务字段, 后续不碰 ORM 对象."""

    rule_id: str
    rule_name: str
    rule_category: str
    risk_level: str
    risk_score: int
    action: str
    description: Optional[str]

    @classmethod
    def from_rule(cls, rule: RiskRule) -> "RuleHitResult":
        """从 RiskRule ORM 对象构造 (拷 7 个字段, 跟 ORM 解耦)."""
        return cls(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            rule_category=rule.rule_category,
            risk_level=rule.risk_level,
            risk_score=rule.risk_score,
            action=rule.action,
            description=rule.description,
        )

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


# ============================================================
# 条件求值
# ============================================================

def evaluate_condition(condition: dict, features: dict) -> bool:
    """递归求值 1 个 JSON 条件表达式, 返回 bool.

    条件格式:
      {"field": "txn_amount", "op": ">", "value": 5000}     ← 单条件
      {"and": [条件1, 条件2]}                                  ← 逻辑组合
      {"or": [条件1, 条件2]}                                   ← 逻辑组合
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
        logger.warning(
            "条件求值异常: field=%s, op=%s, value=%s, actual=%s, err=%s",
            field, op, value, actual, e,
        )
        return False


def _compare(actual: Any, op: str, value: Any) -> bool:
    """执行 1 次具体比较运算. 未知 op 兜底 False, 不中断流程.

    14 种 op 分两类:
      数值型 (9): >, >=, <, <=, ==, !=, in, not_in, between
      字符串型 (5): contains, not_contains, regex, startswith, endswith
    """
    # ---- 数值型运算 ----
    if op == ">":
        return float(actual) > float(value)
    elif op == ">=":
        return float(actual) >= float(value)
    elif op == "<":
        return float(actual) < float(value)
    elif op == "<=":
        return float(actual) <= float(value)
    elif op == "==":
        return float(actual) == float(value)
    elif op == "!=":
        return float(actual) != float(value)
    elif op == "in":
        return float(actual) in [float(v) for v in value]
    elif op == "not_in":
        return float(actual) not in [float(v) for v in value]
    elif op == "between":
        # value = [min, max] 闭区间, 包含两端
        low, high = float(value[0]), float(value[1])
        return low <= float(actual) <= high
    # ---- 字符串型运算 ----
    elif op == "contains":
        return str(value) in str(actual)
    elif op == "not_contains":
        return str(value) not in str(actual)
    elif op == "regex":
        return re.search(str(value), str(actual)) is not None
    elif op == "startswith":
        return str(actual).startswith(str(value))
    elif op == "endswith":
        return str(actual).endswith(str(value))
    else:
        logger.warning("不支持的运算符: %s", op)
        return False


# ============================================================
# 规则加载 + 批量匹配
# ============================================================

async def load_rules(
    db: AsyncSession, event_type: Optional[str] = None,
) -> list[RiskRule]:
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


def evaluate_rules(
    rules: list[RiskRule],
    features: dict,
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
            logger.info(
                "规则命中: %s (%s), 分值=%d",
                rule.rule_id, rule.rule_name, rule.risk_score,
            )
            hits.append(RuleHitResult.from_rule(rule))
    return hits


# ============================================================
# Demo: 演练 14 种 op + and/or 嵌套求值 — 无需 DB
# 跑法: python bank_risk/app/engine/rule.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("规则引擎 — JSON 条件表达式求值 (14 种 op + and/or 嵌套)")
    print("=" * 60)

    # 14 种 op 测试
    test_cases = [
        # (描述, 条件, 特征, 期望)
        ("基础 >=",         {"field": "txn_amount", "op": ">=", "value": 5000},
                           {"txn_amount": 8000}, True),
        ("基础 >",          {"field": "txn_amount", "op": ">", "value": 5000},
                           {"txn_amount": 8000}, True),
        ("基础 <=",         {"field": "txn_amount", "op": "<=", "value": 5000},
                           {"txn_amount": 5000}, True),
        ("基础 <",          {"field": "txn_amount", "op": "<", "value": 5000},
                           {"txn_amount": 3000}, True),
        ("基础 ==",         {"field": "txn_is_night", "op": "==", "value": 1},
                           {"txn_is_night": 1}, True),
        ("基础 !=",         {"field": "txn_channel", "op": "!=", "value": 0},
                           {"txn_channel": 2}, True),
        ("in",             {"field": "txn_channel", "op": "in", "value": [1, 2, 3]},
                           {"txn_channel": 2}, True),
        ("not_in",         {"field": "txn_channel", "op": "not_in", "value": [1, 2]},
                           {"txn_channel": 3}, True),
        ("contains",       {"field": "user_device_count", "op": "contains", "value": "5"},
                           {"user_device_count": 15}, True),
        ("not_contains",   {"field": "user_credit_score", "op": "not_contains", "value": "X"},
                           {"user_credit_score": 700}, True),
        ("regex",          {"field": "user_credit_score", "op": "regex", "value": r"^7\d"},
                           {"user_credit_score": 750}, True),
        ("between",        {"field": "txn_amount", "op": "between", "value": [1000, 5000]},
                           {"txn_amount": 3000}, True),
        ("startswith",     {"field": "user_device_count", "op": "startswith", "value": "5"},
                           {"user_device_count": "50"}, True),
        ("endswith",       {"field": "txn_amount", "op": "endswith", "value": "000"},
                           {"txn_amount": "5000"}, True),
        ("AND 嵌套",        {"and": [
            {"field": "user_login_fail_count_7d", "op": ">=", "value": 5},
            {"field": "user_device_count", "op": ">=", "value": 3},
        ]}, {"user_login_fail_count_7d": 6, "user_device_count": 5}, True),
        ("OR 嵌套",         {"or": [
            {"field": "txn_amount", "op": ">=", "value": 10000},
            {"field": "txn_ip_is_tor", "op": "==", "value": 1},
        ]}, {"txn_amount": 500, "txn_ip_is_tor": 1}, True),
        ("未识别字段→False", {"field": "ghost", "op": ">", "value": 0},
                           {"real": 1}, False),
    ]
    print("\n[1] 14 种 op + and/or 嵌套求值:")
    for desc, cond, feats, expected in test_cases:
        got = evaluate_condition(cond, feats)
        mark = "OK" if got == expected else "FAIL"
        print(f"  [{mark}] {desc:<30} 期望={expected} 实际={got}")

    print("\n" + "=" * 60)
    print("结论: 14 种 op + 递归 and/or, 复杂规则如 AND 嵌套也能正确求值")
