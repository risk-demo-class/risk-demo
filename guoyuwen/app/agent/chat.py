"""
AI Agent 入口 (基于 LangChain DeepAgents).
模型: 阿里云百炼 qwen-plus (settings.LLM_* 配置). 工具: 8 个 @tool.
"""

import asyncio
import logging
from typing import Optional

import ulid
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from deepagents import create_deep_agent

from app.agent.tools import ALL_TOOLS
from app.config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是银行风险运营工作台的 AI 助手，负责协助风控分析师完成以下工作:

1. **风险检查**: 对登录、转账、贷款申请、绑卡 source 执行实时评估
2. **案件管理**: 查询和分析待审核/已处理的风控案件
3. **用户画像**: 查看用户的风险评分、行为特征、历史记录
4. **黑名单管理**: 查询、添加、移除黑名单
5. **数据分析**: 统计仪表盘、趋势分析、规则命中效果
6. **业务查询**: 查看转账、贷款、银行卡、登录环境和共享设备等虚构业务数据

工作原则:
- 根据用户问题，选择合适的工具获取数据
- 用中文回答，结果需要简洁清晰
- 对风险数据给出专业的分析解读
- 不把教学规则或模型分数表述为真实授信、反洗钱报告或账户处置结论
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


# 会话消息存储 (内存级别, 重启丢失, 不持久化)
_sessions: dict[str, list] = {}
_sessions_lock = asyncio.Lock()


async def chat(
    message: str,
    session_id: Optional[str] = None,
) -> tuple[str, str]:
    """与 AI Agent 对话 (异步). 任何异常都转成可读消息返回, 不向外抛 500."""
    if not session_id:
        session_id = f"sess_{ulid.new().str.lower()}"

    # 加锁保护: 避免两个请求同时改同一 session 丢消息
    async with _sessions_lock:
        history = _sessions.get(session_id, [])
        history.append(HumanMessage(content=message))
        # 首次 append 时 .get 返回临时新列表, 不写回会丢历史 (降级/异常路径不落库)
        _sessions[session_id] = history

    # LLM Key 未配置时直接降级提示 (对应 .env.example "不填则助手降级提示"),
    # 避免 ChatOpenAI 初始化抛 Missing credentials 变成裸 500.
    if not settings.LLM_API_KEY:
        return (
            "AI 助手尚未配置大模型服务：项目根目录 .env 的 LLM_API_KEY 为空。"
            "请填入阿里云百炼 API Key 后重启服务；未配置时无法进行 AI 对话，"
            "可直接使用左侧菜单的运营总览 / 风险检查 / 案件 / 规则等功能。",
            session_id,
        )

    try:
        # get_agent() 放 try 内: Agent 创建失败 (如 Key 错误) 也降级为可读消息
        agent = get_agent()
        result = await agent.ainvoke({"messages": history})
        messages = result.get("messages", [])
        if messages:
            reply = messages[-1].content
            # 把完整对话历史保存 (含 tool 调用中间结果)
            async with _sessions_lock:
                _sessions[session_id] = messages
        else:
            reply = "抱歉，未能生成回复。"
    except Exception as e:
        logger.exception("Agent 执行异常")
        reply = f"Agent 执行出错: {e}"

    return reply, session_id


def clear_session(session_id: str) -> bool:
    """清除指定会话的历史消息. 内存存储, 进程重启就全没了."""
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False
