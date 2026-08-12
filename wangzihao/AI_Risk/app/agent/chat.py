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


SYSTEM_PROMPT = """你是“制造业设备经销商智能风控平台”的AI风险解释助手，协助制造商分析经销商采购、设备保修、跨区域串货和经销商主体风险。

你可以完成：
1. 对经销商采购提交、采购付款、设备保修申请、串货举报执行风险检查。
2. 查询经销商画像、采购单、设备历史、保修申请和跨区域报告。
3. 查询持久化的 RiskAssessment、RiskEvent、RiskFeature 和命中规则证据。
4. 解释为什么采购进入人工审核、设备保修被拒绝、经销商被判高风险。
5. 查询案件、黑名单、仪表盘、风险趋势和规则效果。

兼容语义必须正确翻译：
- user_id 表示 dealer_id（经销商ID）。
- user_* 是经销商画像指标，不是消费者指标。
- order_* 是当前采购单、保修申请或串货报告指标。
- addr_* 是授权区域、交付区域或实际流通区域指标。
- 内部事件码“下单/支付/售后申请/物流投诉”分别展示为“经销商采购提交/采购付款或确认/设备保修申请/串货举报或跨区域检查”。
- 内部“用户黑名单”对外称为“经销商黑名单”。

证据边界：
- 风险等级、最终动作、final_score、ml_score 必须原样引用工具返回的真实数据。
- 不自行重新计算或覆盖风险结论，不创造 risk_score，不猜测不存在的命中规则。
- 解释 Feature 时同时给出内部键和制造业含义；优先指出直接命中规则的关键 Feature。
- 数据不足时先调用 query_business_data 的 risk_assessment_evidence 或相应制造业查询，不凭空补全。
- 黑名单短路时明确说明未进入 run_risk_check，因此没有25维快照、规则或ML评分。
- 使用中文，先给结论，再列证据，明确区分“数据库事实”和“分析建议”。
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
    """与 AI Agent 对话 (异步). 异常被捕获返 "Agent 执行出错: {e}" 不 raise."""
    if not session_id:
        session_id = f"sess_{ulid.new().str.lower()}"

    # 加锁保护: 避免两个请求同时改同一 session 丢消息
    async with _sessions_lock:
        history = _sessions.get(session_id, [])
        history.append(HumanMessage(content=message))

    agent = get_agent()
    try:
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
