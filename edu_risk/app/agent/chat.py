"""
AI Agent — 懒加载 DeepAgent
_agent = None 全局,第一次 get_agent() 才创建(避免 import 时建 LLM 连接)。
温度 0.1(业务稳定) + 内存级会话 + asyncio.Lock + 60s 超时。
"""
import asyncio
import logging

from app.agent.tools import ALL_TOOLS
from app.config import settings

logger = logging.getLogger(__name__)

_agent = None                 # 懒加载
_sessions: dict = {}          # 内存级会话历史(重启丢失,生产换 Redis)
_lock = asyncio.Lock()

SYSTEM_PROMPT = """你是教育行业风控系统 EduRisk 的 AI 助手,负责协助风控分析专家完成:
1. 风险检查(报名/缴费/退费/考试/作业)
2. 案件管理(查询/状态流转)
3. 学员风险画像
4. 黑名单管理
5. 数据分析(大盘统计/趋势/规则命中率)
6. 教育业务查询(课程/报名/缴费/退费/考试)

工作原则:
- 根据问题选择合适的工具
- 中文回答,简洁清晰
- 给出专业的风控分析解读
- 可组合多个工具完成任务
- 数据不足时主动向用户补充询问
"""


def get_agent():
    """懒加载: 第一次调用才创建 LLM Agent。"""
    global _agent
    if _agent is None:
        _agent = _create_agent()
    return _agent


def _create_agent():
    """创建 DeepAgent(教学版: 若未配置 LLM_API_KEY 则降级为工具代理,不阻塞服务)。"""
    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=settings.LLM_TEMPERATURE,
            timeout=settings.AI_AGENT_CHAT_TIMEOUT_SEC,
        )
        # 教学版用 LangChain AgentExecutor 编排(DeepAgents 可替换)
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("placeholder", "{chat_history}"),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])
        agent = create_tool_calling_agent(llm, ALL_TOOLS, prompt)
        executor = AgentExecutor(
            agent=agent, tools=ALL_TOOLS,
            handle_parsing_errors=True,
            verbose=settings.DEBUG,
            max_iterations=6,
        )
        return executor
    except Exception as e:
        logger.warning("LLM Agent 创建失败,降级为无模型模式: %s", e)
        return None


async def stream_chat(agent, session_id: str, message: str, db):
    """SSE 流式聊天。Agent 为 None(未配 Key)时返回降级提示。"""
    async with _lock:
        history = _sessions.get(session_id, [])

    if agent is None:
        yield _sse("text", "当前未配置 LLM_API_KEY,AI 助手不可用。请在 .env 配置后重启。")
        return

    try:
        result = await agent.ainvoke({
            "input": message,
            "chat_history": history,
        })
        answer = result.get("output", "")
        _append_history(session_id, message, answer)

        # 工具调用记录
        for step in result.get("intermediate_steps", []):
            tool_name = getattr(step[0], "tool", "?")
            tool_input = getattr(step[0], "tool_input", {})
            yield _sse("tool", f"调用工具 {tool_name}: {tool_input}")

        yield _sse("text", answer)
        yield _sse("done", "")
    except Exception as e:
        logger.exception("agent chat error")
        yield _sse("error", str(e))


def _append_history(session_id: str, question: str, answer: str):
    _sessions.setdefault(session_id, []).append(
        {"role": "user", "content": question})
    _sessions[session_id].append(
        {"role": "assistant", "content": answer})
    # 内存裁剪: 只保留最近 10 轮
    if len(_sessions[session_id]) > 20:
        _sessions[session_id] = _sessions[session_id][-20:]


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"
