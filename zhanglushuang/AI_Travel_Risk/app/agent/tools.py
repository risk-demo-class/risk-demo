"""
AI Agent 工具集.

每个工具只做一件事, chat 层负责按用户问题路由.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RiskAssessment, RiskCase, RiskRule, RiskUserProfile

logger = logging.getLogger(__name__)


async def query_cases(db: AsyncSession) -> str:
    """查询案件数量与状态分布."""
    try:
        total = int((await db.execute(select(func.count()).select_from(RiskCase))).scalar() or 0)
        pending = int(
            (
                await db.execute(
                    select(func.count()).select_from(RiskCase).where(RiskCase.case_status == "待审核")
                )
            ).scalar()
            or 0
        )
        return f"当前案件 {total} 条, 其中待审核 {pending} 条"
    except Exception:
        logger.exception("Agent 查询案件失败")
        return "案件查询失败, 请稍后再试"


async def query_user_profile(db: AsyncSession, user_id: str) -> str:
    """查询用户风险画像."""
    try:
        row = (
            await db.execute(
                select(RiskUserProfile).where(RiskUserProfile.user_id == user_id).limit(1)
            )
        ).scalar_one_or_none()
        if not row:
            return f"用户 {user_id} 暂无画像"
        return (
            f"用户 {user_id}: 风险分 {row.risk_score}, 等级 {row.risk_level}, "
            f"订单 {row.total_orders}, 退改 {row.total_refunds}, 评估 {row.assessment_count}"
        )
    except Exception:
        logger.exception("Agent 查询画像失败")
        return "画像查询失败"


async def query_dashboard_stats(db: AsyncSession) -> str:
    """查询仪表盘统计."""
    try:
        case_total = int((await db.execute(select(func.count()).select_from(RiskCase))).scalar() or 0)
        assessment_total = int(
            (await db.execute(select(func.count()).select_from(RiskAssessment))).scalar() or 0
        )
        rule_total = int(
            (
                await db.execute(
                    select(func.count()).select_from(RiskRule).where(RiskRule.deleted_at.is_(None))
                )
            ).scalar()
            or 0
        )
        return f"案件 {case_total} 条, 评估 {assessment_total} 条, 启用规则 {rule_total} 条"
    except Exception:
        logger.exception("Agent 查询统计失败")
        return "统计查询失败"
