"""
规则更新接口 null 处理回归测试.

背景 (2026-08-11): 前端 parseInt('')=NaN → JSON 序列化成 null,
PUT /api/rules/{id} 带 risk_score=null 会把 NOT NULL 列写成 NULL → MySQL 1048.
修复: update 用 model_dump(exclude_unset=True, exclude_none=True), 显式 null 不更新.

跑法: pytest tests/test_rule_update_null.py -v
"""
import time

import pytest

from app.database import AsyncSessionLocal
from app.models import RiskRule
from app.routers.rule import api_update_rule
from app.schemas import RuleUpdate


def _unique_rule_id() -> str:
    """软删后 rule_id 主键仍占用, 测试用时间戳唯一 ID 避免撞主键 (1062)."""
    return f"R{int(time.time() * 1000)}"


@pytest.mark.asyncio
async def test_update_rule_ignores_explicit_null():
    """PUT 带 risk_score=null → 忽略该字段, 原值保持不变 (不再 1048)."""
    async with AsyncSessionLocal() as db:
        rule_id = _unique_rule_id()
        rule = RiskRule(
            rule_id=rule_id, rule_name="null 测试规则", rule_category="综合风险",
            event_type="通用",
            rule_condition='{"field": "order_total_amount", "op": ">", "value": 1}',
            risk_level="低", risk_score=42, action="通过", priority=0,
        )
        db.add(rule)
        await db.commit()
        try:
            resp = await api_update_rule(rule_id, RuleUpdate(risk_score=None), db)
            assert resp.risk_score == 42, "显式 null 不应覆盖原分值"
        finally:
            await db.delete(rule)
            await db.commit()


@pytest.mark.asyncio
async def test_update_rule_normal_value_updates():
    """正常传分值 → 正常更新."""
    async with AsyncSessionLocal() as db:
        rule_id = _unique_rule_id()
        rule = RiskRule(
            rule_id=rule_id, rule_name="null 测试规则", rule_category="综合风险",
            event_type="通用",
            rule_condition='{"field": "order_total_amount", "op": ">", "value": 1}',
            risk_level="低", risk_score=42, action="通过", priority=0,
        )
        db.add(rule)
        await db.commit()
        try:
            resp = await api_update_rule(rule_id, RuleUpdate(risk_score=88), db)
            assert resp.risk_score == 88
        finally:
            await db.delete(rule)
            await db.commit()
