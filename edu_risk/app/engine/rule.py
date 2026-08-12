"""
规则引擎 — JSON 条件表达式求值
支持 14 种 op: > >= < <= == != in not_in between and or
设计: unknown field / unknown op 兜底返回 False,不抛异常,脏数据不炸流程。
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RiskRule

logger = logging.getLogger(__name__)


def evaluate_condition(condition: dict, features: dict) -> bool:
    """递归求值一个 JSON 条件表达式。任何异常 → False。"""
    try:
        if not isinstance(condition, dict):
            return False

        if "and" in condition:
            return all(evaluate_condition(c, features) for c in condition["and"])
        if "or" in condition:
            return any(evaluate_condition(c, features) for c in condition["or"])

        field = condition.get("field")
        op = condition.get("op")
        value = condition.get("value")
        actual = features.get(field)

        # unknown field → 不命中(特征算不出来时不阻塞)
        if actual is None:
            return False

        return _compare(actual, op, value)
    except Exception:
        logger.exception("rule evaluate error: %s", condition)
        return False


def _compare(actual, op, value) -> bool:
    """单条原子比较。"""
    if op == ">":
        return actual > value
    if op == ">=":
        return actual >= value
    if op == "<":
        return actual < value
    if op == "<=":
        return actual <= value
    if op == "==":
        return actual == value
    if op == "!=":
        return actual != value
    if op == "in":
        return actual in value
    if op == "not_in":
        return actual not in value
    if op == "between":
        lo, hi = value
        return lo <= actual <= hi
    # unknown op → 兜底 False
    return False


async def load_enabled_rules(db: AsyncSession, event_type: str | None = None) -> list[RiskRule]:
    """
    加载启用规则,按 priority desc 排序。
    event_type 限定: 只加载该事件类型 + 通用规则,提升匹配效率。
    软删过滤: deleted_at IS NULL。
    """
    stmt = (
        select(RiskRule)
        .where(RiskRule.is_enabled.is_(True))
        .where(RiskRule.is_deleted.is_(False))
        .where(RiskRule.deleted_at.is_(None))
        .order_by(RiskRule.priority.desc())
    )
    if event_type:
        stmt = stmt.where((RiskRule.event_type == event_type) | (RiskRule.event_type == "通用"))
    result = await db.execute(stmt)
    return list(result.scalars().all())


def build_hits(hits: list[RiskRule], features: dict) -> list[dict]:
    """包装命中规则为字典列表。"""
    return [
        {
            "rule_id": r.rule_id,
            "rule_name": r.rule_name,
            "rule_category": r.rule_category,
            "risk_level": r.risk_level,
            "risk_score": r.risk_score,
            "action": r.action,
            "description": r.description,
        }
        for r in hits
    ]
