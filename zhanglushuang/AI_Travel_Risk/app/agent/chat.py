"""
轻量 Agent 对话层.

按关键词路由到不同工具, 不依赖 langchain.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import query_cases, query_dashboard_stats, query_user_profile

logger = logging.getLogger(__name__)


async def chat(db: AsyncSession, message: str) -> str:
    """根据用户问题返回结果."""
    try:
        text = (message or "").strip()
        if not text:
            return "请描述你想查询的内容"

        if "案件" in text or "待审核" in text:
            return await query_cases(db)
        if "画像" in text or "风险分" in text:
            # 提取 user_id
            user_id = next((part for part in text.split() if part.startswith(("U", "RISK"))), None)
            if user_id:
                return await query_user_profile(db, user_id)
            return "请提供用户ID, 例如: 查一下 RISK001 的风险画像"
        if "统计" in text or "仪表盘" in text or "数量" in text:
            return await query_dashboard_stats(db)

        return (
            "我可以帮你: 查案件、查用户画像、查仪表盘统计、触发风控检查。"
            "请换一种说法再试一次。"
        )
    except Exception:
        logger.exception("Agent 对话处理失败")
        return "Agent 处理失败, 请稍后再试"
