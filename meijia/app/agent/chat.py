"""AI Agent 对话层 (基于 LangChain DeepAgents)。

模型: 配置的 LLM (默认阿里云百炼 qwen-plus, RISK_LLM_* 环境变量)。
工具: app.agent.tools.ALL_TOOLS (8 个)。会话存内存 (进程级, 重启丢失)。

LLM_API_KEY 未配置时, chat() 直接返回引导文案, 不发起 LLM 调用。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import ulid
from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.agent.tools import ALL_TOOLS
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是教育风控系统的 AI 助手，协助风控分析师完成以下工作:

1. 风险检查: 对指定用户/事件执行实时风控评估 (含规则 + ML 双轨评分)
2. 案件管理: 查询待审核/已处理的风控案件
3. 用户画像: 查看用户基本信息、账号特征、业务统计、最近风控评估
4. 黑名单管理: 查询、添加、校验黑名单
5. 数据分析: 仪表盘统计、风险趋势、规则命中效果
6. 业务查询: 用户订单、退费、学历认证、直播打赏等业务数据

工作原则:
- 根据用户问题选择合适的工具获取真实数据, 不要编造
- 用中文回答, 结果简洁清晰, 给出专业的风控解读
- 可组合多个工具完成复杂分析
- 数据不足时主动补充查询
- 可用户ID示例: RISK-STU-001 等
"""

# 全局 Agent 单例 (惰性初始化: 第 1 次 get_agent() 才创建)
_agent = None


def _create_agent():
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
    """获取全局唯一 Agent 实例 (进程内 1 个即可, 避免重复建 LLM 握手)。"""
    global _agent
    if _agent is None:
        _agent = _create_agent()
    return _agent


# 会话消息存储 (内存级别, 重启丢失)。加锁避免并发改同一 session。
_sessions: dict[str, list] = {}
_sessions_lock = asyncio.Lock()

_NO_KEY_HINT = (
    "尚未配置 LLM（需要设置 RISK_LLM_API_KEY）。请先在 .env 配置后重启服务。"
    "配置示例：RISK_LLM_API_KEY=sk-xxx（阿里云百炼等兼容 OpenAI 接口均可）。"
)


async def chat(message: str, session_id: Optional[str] = None) -> tuple[str, str]:
    """与 AI Agent 对话 (异步)。异常被捕获返回提示, 不 raise。"""
    if not session_id:
        session_id = f"sess_{ulid.new().str.lower()}"

    if not settings.LLM_API_KEY:
        return _NO_KEY_HINT, session_id

    async with _sessions_lock:
        history = _sessions.get(session_id, [])
        history.append(HumanMessage(content=message))

    agent = get_agent()
    try:
        result = await agent.ainvoke({"messages": history})
        messages = result.get("messages", [])
        if messages:
            reply = messages[-1].content or "抱歉，未能生成回复。"
            async with _sessions_lock:
                _sessions[session_id] = messages
        else:
            reply = "抱歉，未能生成回复。"
    except Exception as exc:
        logger.exception("Agent 执行异常")
        reply = f"Agent 执行出错: {exc}"

    return reply, session_id


def clear_session(session_id: str) -> bool:
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False
