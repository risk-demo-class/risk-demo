"""
AI Agent 入口 (基于 LangChain DeepAgents).
模型: 阿里云百炼 qwen-plus (settings.LLM_* 配置). 工具: 8 个 @tool.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import ulid
from langchain_core.messages import HumanMessage, message_to_dict, messages_from_dict
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from deepagents import create_deep_agent
from sqlalchemy import delete, select

from app.agent.tools import ALL_TOOLS
from app.config import settings
from app.database import AsyncSessionLocal
from app.models import AgentSession

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是医疗风控系统的AI助手，负责协助风控分析师完成以下工作:

1. **风险检查**: 对指定用户/事件执行实时风控评估
2. **案件管理**: 查询和分析待审核/已处理的风控案件
3. **用户画像**: 查看用户的风险评分、行为特征、历史记录
4. **黑名单查询**: 查询黑名单 (只读; 增删黑名单必须走管理后台人工操作)
5. **数据分析**: 统计仪表盘、趋势分析、规则命中效果
6. **业务查询**: 查看参保人就诊/结算/处方/药品订单等医疗业务数据

工作原则:
- 根据用户问题，选择合适的工具获取数据
- 用中文回答，结果需要简洁清晰
- 对风险数据给出专业的分析解读
- 可以组合多个工具完成复杂分析任务
- 当数据不足时，主动补充查询相关信息
"""

# 全局 Agent 单例 (惰性初始化: 第 1 次 get_agent() 才创建)
# 避免 import 时就建 LLM 连接, 留给真正需要时再建
_agent = None


def _create_agent():
    """构造 1 个 DeepAgent 实例 (LLM + 8 tools + system prompt)."""
    llm = ChatOpenAI(
        model=settings.LLM_MODEL_NAME,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.1,  # 低温=答案更确定, 适合业务场景
    )
    return create_deep_agent(
        model=llm,
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
    )


def get_agent():
    """获取全局唯一的 Agent 实例 (进程内 1 个就够, 多次创建浪费 LLM 握手)."""
    global _agent
    if _agent is None:
        _agent = _create_agent()
    return _agent


# 【2026-08-11 P1】会话存 MySQL 表 (agent_session), 解决:
#   - 4 worker 间会话不共享 (对话上下文乱跳)
#   - 无 TTL 导致内存泄漏


async def _cleanup_expired_sessions(db) -> int:
    """删除超过 AGENT_SESSION_TTL_HOURS 未活动的会话."""
    deadline = datetime.now() - timedelta(hours=settings.AGENT_SESSION_TTL_HOURS)
    result = await db.execute(
        delete(AgentSession).where(AgentSession.last_active < deadline)
    )
    return result.rowcount or 0


async def _load_history(db, session_id: str) -> list:
    """从 MySQL 加载会话历史 (LangChain message dict → 对象)."""
    row = (await db.execute(
        select(AgentSession).where(AgentSession.session_id == session_id)
    )).scalar_one_or_none()
    if not row or not row.messages:
        return []
    try:
        return messages_from_dict(json.loads(row.messages))
    except Exception:
        logger.warning("会话 %s 历史解析失败, 重新开始", session_id)
        return []


async def _save_history(db, session_id: str, messages: list) -> None:
    """保存会话历史 (upsert: 有则更新, 无则插入)."""
    serialized = json.dumps([message_to_dict(m) for m in messages], ensure_ascii=False)
    row = (await db.execute(
        select(AgentSession).where(AgentSession.session_id == session_id)
    )).scalar_one_or_none()
    now = datetime.now()
    if row:
        row.messages = serialized
        row.last_active = now
    else:
        db.add(AgentSession(
            session_id=session_id, messages=serialized,
            create_time=now, last_active=now,
        ))
    await db.commit()


async def chat(
    message: str,
    session_id: Optional[str] = None,
) -> tuple[str, str]:
    """与 AI Agent 对话 (异步). 异常被捕获返 "Agent 执行出错: {e}" 不 raise."""
    if not session_id:
        session_id = f"sess_{ulid.new().str.lower()}"

    async with AsyncSessionLocal() as db:
        await _cleanup_expired_sessions(db)
        history = await _load_history(db, session_id)
        history.append(HumanMessage(content=message))

        agent = get_agent()
        try:
            result = await agent.ainvoke({"messages": history})
            messages = result.get("messages", [])
            if messages:
                reply = messages[-1].content
                # 完整对话历史存 MySQL (含 tool 调用中间结果)
                await _save_history(db, session_id, messages)
            else:
                reply = "抱歉，未能生成回复。"
        except Exception as e:
            logger.exception("Agent 执行异常")
            reply = f"Agent 执行出错: {e}"

    return reply, session_id


async def clear_session(session_id: str) -> bool:
    """清除指定会话的历史消息 (MySQL 表)."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(AgentSession).where(AgentSession.session_id == session_id)
        )
        await db.commit()
        return (result.rowcount or 0) > 0
