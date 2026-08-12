"""
AI Agent 入口 (基于 LangChain DeepAgents). 银行风控场景.
模型: 阿里云百炼 qwen-plus (settings.LLM_* 配置). 工具: 8 个 @tool.
"""
import logging

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent

from bank_risk.app.agent.tools import get_all_tools
from bank_risk.app.config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是银行风控系统的 AI 助理。你可以:
1. 查询风控规则
2. 查询案件状态
3. 发起风控检查
4. 查询用户交易/贷款/登录数据
5. 查询黑名单
6. 执行 SQL 查询做数据分析

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


def get_agent():
    """获取全局唯一的 Agent 实例 (进程内 1 个就够, 多次创建浪费 LLM 握手)."""
    global _agent
    if _agent is None:
        llm = ChatOpenAI(
            model=settings.LLM_MODEL_NAME,
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            temperature=0.1,  # 低温=答案更确定, 适合业务场景
        )
        _agent = create_deep_agent(
            model=llm,
            tools=get_all_tools(),
            system_prompt=SYSTEM_PROMPT,
        )
    return _agent


async def run_agent(message: str) -> str:
    """同步对话: 返回完整回复字符串."""
    agent = get_agent()
    try:
        result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
        messages = result.get("messages", [])
        if messages:
            return messages[-1].content
        return "抱歉，未能生成回复。"
    except Exception as e:
        logger.exception("Agent 执行异常")
        return f"Agent 执行出错: {e}"


async def run_agent_stream(message: str):
    """流式对话 (async generator): 逐步 yield 内容片段."""
    agent = get_agent()
    try:
        async for event in agent.astream({"messages": [HumanMessage(content=message)]}):
            messages = event.get("messages", [])
            if messages:
                content = messages[-1].content
                if content:
                    yield content
    except Exception as e:
        logger.exception("Agent 流式执行异常")
        yield f"Agent 执行出错: {e}"
