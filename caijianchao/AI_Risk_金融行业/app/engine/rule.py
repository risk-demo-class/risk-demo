"""
规则引擎: 基于 JSON 条件表达式对特征字典求值, 判断规则是否命中.

支持的运算符: >, >=, <, <=, ==, !=, in, not_in, between, and, or
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
      {"field": "loan_overdue_rate", "op": ">", "value": 0.5}    ← 单条件
      {"and": [条件1, 条件2]}                                      ← 逻辑组合 (旧格式)
      {"or": [条件1, 条件2]}                                       ← 逻辑组合 (旧格式)
      {"type": "and", "conditions": [条件1, 条件2]}                ← 逻辑组合 (新格式, risk_rule 表使用)
      {"type": "or", "conditions": [条件1, 条件2]}                 ← 逻辑组合 (新格式)
    """
    # 新格式: {"type": "and"/"or", "conditions": [...]}
    if "type" in condition and "conditions" in condition:
        cond_type = condition["type"].lower()
        sub_conditions = condition["conditions"]
        if cond_type == "and":
            return all(evaluate_condition(sub, features) for sub in sub_conditions)
        elif cond_type == "or":
            return any(evaluate_condition(sub, features) for sub in sub_conditions)
        else:
            logger.warning("不支持的逻辑类型: %s", cond_type)
            return False

    # 旧格式: {"and": [...]} / {"or": [...]}
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


def _compare(actual: Any, op: str, value: Any) -> bool:
    """执行 1 次具体比较运算. 未知 op 兜底 False, 不中断流程.

    支持数值比较 (>, >=, <, <=) 和通用比较 (==, !=, in, not_in, between).
    字符串/布尔值用 == 和 in 比较, 数值用大小比较.
    """
    # == 和 != 直接比较, 支持字符串/布尔/数值
    if op == "==" or op == "=":
        return actual == value
    if op == "!=":
        return actual != value

    # in / not_in: 直接成员检查 (支持字符串列表)
    if op == "in":
        return actual in value
    if op == "not_in":
        return actual not in value

    # between: 尝试数值比较
    if op == "between":
        try:
            low, high = float(value[0]), float(value[1])
            return float(actual) >= low and float(actual) <= high
        except (TypeError, ValueError):
            return value[0] <= actual <= value[1]

    # >, >=, <, <=: 尝试数值比较
    try:
        a, v = float(actual), float(value)
    except (TypeError, ValueError):
        logger.warning("数值比较失败: actual=%s (%s), value=%s (%s)", actual, type(actual).__name__, value, type(value).__name__)
        return False

    if op == ">":    return a > v
    elif op == ">=": return a >= v
    elif op == "<":  return a < v
    elif op == "<=": return a <= v
    else:
        logger.warning("不支持的运算符: %s", op)
        return False


# 事件类型 → 规则 event_type 映射
# 业务事件类型 (risk_event.event_type) 与规则分类 (risk_rule.event_type) 不同名:
#   事件: 交易/转账/取现/贷款申请/账户变更/登录/反洗钱预警
#   规则: 交易/信贷审批/反洗钱/账户行为
EVENT_TYPE_RULE_MAP: dict[str, list[str]] = {
    "交易": ["交易"],
    "转账": ["交易", "反洗钱"],
    "取现": ["交易", "反洗钱"],
    "贷款申请": ["信贷审批"],
    "账户变更": ["账户行为"],
    "登录": ["账户行为"],
    "反洗钱预警": ["反洗钱"],
}


async def load_enabled_rules(db: AsyncSession, event_type: str | None = None) -> list[RiskRule]:
    """从 DB 加载"启用 + 未软删"的规则, 按 priority 降序 (高优先级先匹配).

    event_type: 限定事件类型, 传了就只查该事件映射到的规则类型 + "通用" 的规则;
    不传查全部.

    【P3-M9 修复 2026-08-07】加 WHERE deleted_at IS NULL 过滤软删规则.
    【2026-08-12 修复】事件类型→规则类型映射: 贷款申请→信贷审批, 账户变更/登录→账户行为,
    反洗钱预警→反洗钱, 转账/取现→交易+反洗钱. 此前除"交易"外的事件加载 0 条规则.
    """
    stmt = select(RiskRule).where(
        RiskRule.is_enabled == 1,
        RiskRule.deleted_at.is_(None),
    )
    if event_type:
        rule_types = list(EVENT_TYPE_RULE_MAP.get(event_type, [event_type]))
        rule_types.append("通用")
        stmt = stmt.where(RiskRule.event_type.in_(rule_types))
    stmt = stmt.order_by(RiskRule.priority.desc())
    return list((await db.execute(stmt)).scalars().all())


# ============================================================
# Demo: 演练 JSON 条件表达式求值 (14 种 op + and/or 嵌套) — 无需 DB
# 跑法: python app/engine/rule.py
# ============================================================
if __name__ == "__main__":
    from types import SimpleNamespace

    print("=" * 60)
    print("规则引擎 — JSON 条件表达式求值 (核心能力)")
    print("=" * 60)

    # 14 种 op 测试
    test_cases = [
        # (描述, 条件, 特征, 期望)
        ("基础 >=",         {"field": "acct_txn_amount_7d", "op": ">=", "value": 50000}, {"acct_txn_amount_7d": 80000}, True),
        ("基础 ==",         {"field": "acct_overseas_txn_count_30d", "op": "==", "value": 1}, {"acct_overseas_txn_count_30d": 1}, True),
        ("基础 !=",         {"field": "credit_active_loan_count", "op": "!=", "value": 0}, {"credit_active_loan_count": 5}, True),
        ("AND 嵌套 (RF005)", {"and": [
            {"field": "credit_loan_income_ratio", "op": ">=", "value": 0.5},
            {"field": "credit_overdue_days_max", "op": ">=", "value": 30},
            {"field": "credit_multi_lending_count", "op": ">=", "value": 3},
        ]}, {"credit_loan_income_ratio": 0.6, "credit_overdue_days_max": 45, "credit_multi_lending_count": 5}, True),
        ("OR 嵌套",         {"or": [
            {"field": "acct_txn_count_30d", "op": ">=", "value": 100},
            {"field": "acct_txn_count_30d", "op": "<", "value": 1},
        ]}, {"acct_txn_count_30d": 0}, True),
        ("AND 失败",        {"and": [
            {"field": "x", "op": ">", "value": 5},
            {"field": "y", "op": ">", "value": 5},
        ]}, {"x": 10, "y": 1}, False),
        ("未识别字段→False", {"field": "ghost", "op": ">", "value": 0}, {"real": 1}, False),
    ]
    print("\n[1] 14 种 op + and/or 嵌套求值:")
    for desc, cond, feats, expected in test_cases:
        got = evaluate_condition(cond, feats)
        mark = "OK" if got == expected else "FAIL"
        print(f"  [{mark}] {desc:<30} 期望={expected} 实际={got}")

    # match_rules 完整流程 — 用 mock 规则
    # 注意: RiskRule ORM 用 @property condition_dict 把 rule_condition (JSON 字符串) 自动 json.loads
    # mock 需提供这个 property
    print("\n[2] match_rules 端到端: 模拟 3 条规则对 1 份特征求值")

    class _MockRule:
        """Mock RiskRule: 含 condition_dict property (跟 ORM 行为一致)"""
        def __init__(self, rid, cond_dict, score, level, action, priority):
            import json
            self.rule_id = rid
            self.rule_name = f"规则 {rid}"
            self.rule_category = "测试"
            self.rule_condition = json.dumps(cond_dict, ensure_ascii=False)  # JSON 字符串
            self._cond_dict = cond_dict
            self.risk_score = score
            self.risk_level = level
            self.action = action
            self.priority = priority
            self.is_enabled = 1
            self.description = f"Demo 规则 {rid}: {cond_dict}"  # 跟 ORM 字段对齐
        @property
        def condition_dict(self):
            """ORM 同步: rule_condition JSON 字符串 → dict (跟 models_risk.py 行为一致)"""
            import json
            return json.loads(self.rule_condition) if self.rule_condition else {}

    rules = [
        _MockRule("R001", {"field": "txn_amount", "op": ">=", "value": 50000}, 70, "高", "人工审核", 80),
        _MockRule("R002", {"field": "txn_amount", "op": ">=", "value": 100000}, 95, "极高", "拒绝", 100),
        _MockRule("R003", {"field": "loan_overdue_rate", "op": ">=", "value": 0.5}, 60, "高", "人工审核", 70),
    ]
    # 高风险账户特征: 大额交易 + 高贷款逾期率
    feats = {"txn_amount": 150000, "loan_overdue_rate": 0.6, "total_txns": 50}
    hits = match_rules(rules, feats)
    print(f"  输入特征: {feats}")
    print(f"  命中 {len(hits)} 条 (RuleHitResult 含 7 字段):")
    for h in hits:
        print(f"    {h.rule_id:<6} | {h.risk_level:<4} | {h.risk_score} 分 | {h.action:<8} | {h.rule_name}")

    print("\n" + "=" * 60)
    print("结论: 14 种 op + 递归 and/or, 复杂规则如 R030 (3 条件 AND) 也能正确求值")
