"""
Agent 工具集: 规则查询 / 风险解释 / 统计
"""
import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RiskAssessment, RiskRule


async def count_enabled_rules(db: AsyncSession) -> dict:
    """工具: 统计各风险场景的启用规则数"""
    rows = (await db.execute(
        select(RiskRule.rule_category, func.count())
        .where(RiskRule.is_enabled == 1, RiskRule.deleted_at.is_(None))
        .group_by(RiskRule.rule_category)
    )).all()
    return {"场景规则数": {cat: int(c) for cat, c in rows}}


async def search_rules(db: AsyncSession, keyword: str) -> list[dict]:
    """工具: 按关键词搜索规则"""
    like = f"%{keyword}%"
    rows = (await db.execute(
        select(RiskRule).where(
            RiskRule.deleted_at.is_(None),
            (RiskRule.rule_name.like(like)) | (RiskRule.rule_id.like(like)) | (RiskRule.description.like(like)),
        ).limit(10)
    )).scalars().all()
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
        for r in rows
    ]


async def risk_distribution(db: AsyncSession) -> dict:
    """工具: 最近评估的决策分布"""
    rows = (await db.execute(
        select(RiskAssessment.decision, func.count()).group_by(RiskAssessment.decision)
    )).all()
    return {"决策分布": {d: int(c) for d, c in rows}}


async def list_rules_summary(db: AsyncSession) -> list[dict]:
    """工具: 全部启用规则清单 (供 LLM 上下文)."""
    rows = (await db.execute(
        select(RiskRule).where(
            RiskRule.is_enabled == 1,
            RiskRule.deleted_at.is_(None),
        ).order_by(RiskRule.priority.desc())
    )).scalars().all()
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
        for r in rows
    ]


async def explain_features() -> str:
    """工具: 输出 28 维特征清单"""
    from app.engine.ml_model import FEATURE_COLUMNS
    return "28 维特征: " + ", ".join(FEATURE_COLUMNS)
