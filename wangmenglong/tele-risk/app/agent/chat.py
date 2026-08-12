"""
AI Agent 对话 (复用 ai_risk 的 /api/agent/chat API).

设计: tele-risk 不重装 langchain/deepagents 栈, 而是把 /api/agent/chat
转发到 ai_risk 的同名端点 (HTTP), 复用其 LLM (qwen-plus) + 8 个工具 +
会话管理. 两服务同机部署 (ai_risk:8000, tele-risk:8001), 互不冲突.

好处:
  1. tele-risk 依赖轻 (不需要 langchain/openai/deepagents)
  2. 复用 ai_risk 已调试好的 Agent 能力 (LLM 握手 / 工具派发 / session 锁)
  3. ai_risk 没跑时优雅降级 (返提示, 不崩)

注意: ai_risk 的 Agent 工具是电商语义 (订单/售后), 转发时会在 message 前加
电信上下文前缀, 让 LLM 知道这是电信风控场景 (通用对话/数据分析仍可用).
"""
import logging
from typing import Optional

import httpx
import ulid

from app.config import settings

logger = logging.getLogger(__name__)

# 电信场景前缀: 让 ai_risk 的 Agent (电商工具) 知道用户问的是电信风控
_TELE_PREFIX = (
    "【电信风控系统】以下问题来自电信风控场景 (号卡/通话/GOIP/猫池/国际诈骗/物联网), "
    "如涉及具体业务工具调用请说明电信语义, 通用问答/数据分析直接回答:\n\n"
)


async def chat(message: str, session_id: Optional[str] = None) -> tuple[str, str]:
    """与 AI Agent 对话: 转发到 ai_risk 的 /api/agent/chat.

    返回 (reply, session_id). ai_risk 不可达时降级返提示, 不抛异常.
    """
    if not settings.AI_AGENT_ENABLED:
        return ("AI Agent 未启用 (config.AI_AGENT_ENABLED=False). "
                "开启后复用 ai_risk 的 Agent API."), session_id or f"sess_{ulid.new().str.lower()}"

    if not session_id:
        session_id = f"sess_{ulid.new().str.lower()}"

    url = f"{settings.AI_RISK_API_BASE}/api/agent/chat"
    payload = {
        "message": _TELE_PREFIX + message,
        "session_id": session_id,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.AI_AGENT_CHAT_TIMEOUT_SEC) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("reply", "(空回复)"), data.get("session_id", session_id)
    except httpx.ConnectError:
        logger.warning("ai_risk Agent 不可达 (连不上 %s), 降级返回", url)
        return (
            f"AI Agent 暂不可用: 连不上 ai_risk 服务 ({settings.AI_RISK_API_BASE}). "
            "请先启动 ai_risk (cd ai_risk && python run_app.py) 再用 Agent."
        ), session_id
    except httpx.HTTPStatusError as e:
        logger.warning("ai_risk Agent 返回非 2xx: %s", e.response.status_code)
        return f"AI Agent 调用失败 (HTTP {e.response.status_code}): {e}", session_id
    except Exception as e:
        logger.exception("Agent 转发异常")
        return f"Agent 执行出错: {e}", session_id


def clear_session(session_id: str) -> bool:
    """清除 ai_risk 侧的会话 (转发 /api/agent/clear). 同步 best-effort, 失败不报错."""
    import asyncio
    async def _clear():
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{settings.AI_RISK_API_BASE}/api/agent/clear",
                    params={"session_id": session_id},
                )
        except Exception:
            pass
    try:
        asyncio.get_running_loop().create_task(_clear())
    except RuntimeError:
        pass
    return True
