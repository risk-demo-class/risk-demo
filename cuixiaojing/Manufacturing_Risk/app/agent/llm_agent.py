"""
LLM 模式 Agent (LangChain DeepAgent, 惰性加载).

只有 .env 配了 LLM_API_KEY 且 langchain/deepagents 已安装时才启用;
否则 chat.py 走内置规则模式 (零依赖兜底).

依赖 (可选): deepagents / langchain / langchain-openai
安装: uv pip install --python .venv/bin/python deepagents langchain langchain-openai
"""
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_agent = None
_llm_available: Optional[bool] = None


def llm_available() -> bool:
    """LLM 模式是否可用 (有 key + 依赖已装)."""
    global _llm_available
    if _llm_available is not None:
        return _llm_available
    if not settings.LLM_API_KEY:
        _llm_available = False
        return False
    try:
        import langchain_openai  # noqa: F401
        import deepagents  # noqa: F401
        _llm_available = True
    except ImportError:
        logger.warning("langchain/deepagents 未安装, AI 助手走内置规则模式")
        _llm_available = False
    return _llm_available


SYSTEM_PROMPT = """你是制造业风控系统的AI助手，负责协助风控分析师完成以下工作:

1. **风险检查**: 对经销商订货/保修申请/售后维修/串货举报事件执行实时风控评估
2. **案件管理**: 查询和分析待审核/已处理的风控案件
3. **经销商画像**: 查看经销商的风险评分、订货统计、保修/维修记录、合同状态
4. **黑名单管理**: 查询、添加、移除黑名单 (经销商ID/设备SN/维修工/用户)
5. **数据分析**: 统计仪表盘、趋势分析、规则命中效果
6. **业务查询**: 查看订货单、保修记录、串货举报等业务数据

工作原则:
- 根据用户问题，选择合适的工具获取数据
- 用中文回答，结果需要简洁清晰
- 对风险数据给出专业的分析解读
- 可以组合多个工具完成复杂分析任务
- 当数据不足时，主动补充查询相关信息

【重要: 序号快捷指令】用户可能直接输入数字 1-6 (或"第N项") 表示选择欢迎语中的任务序号:
  1 = 风险检查 (需要经销商ID/事件/业务ID, 缺参数就引导用户补充)
  2 = 查询案件列表
  3 = 查询经销商风险画像 (需要经销商ID, 如 D002)
  4 = 仪表盘统计和趋势
  5 = 黑名单管理 (默认列出黑名单)
  6 = 规则命中效果分析
遇到纯数字或"第N项"时, 必须按上表执行对应任务, 不要自行解释成其他含义。
"""


def _create_agent():
    """构造 1 个 DeepAgent 实例 (LLM + 8 tools + system prompt)."""
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from deepagents import create_deep_agent

    from app.agent.tools import (
        _analyze_risk_trend_impl,
        _analyze_rule_effectiveness_impl,
        _manage_blacklist_impl,
        _query_business_data_impl,
        _query_cases_impl,
        _query_dashboard_stats_impl,
        _query_dealer_profile_impl,
        _risk_check_impl,
        _safe_call,
    )

    # ---- 8 个 langchain @tool (显式参数签名, 供 LLM 生成 JSON schema) ----

    @tool(
        description=(
            "对指定经销商/用户和事件执行实时风险检查。"
            "参数: user_id (经销商ID, 如 'D002')、event_type (经销商订货/保修申请/售后维修/串货举报)、"
            "source_id (订单/保修单/举报单ID)。返回评分、风险等级、决策和命中规则。"
            "内部: 走 process_event 4 步业务流 (校验→补全→黑名单→7步决策流水线)。"
        )
    )
    async def risk_check(user_id: str, event_type: str, source_id: str) -> str:
        return await _safe_call("风险检查", _risk_check_impl,
                                user_id=user_id, event_type=event_type, source_id=source_id)

    @tool(
        description=(
            "查询风控案件列表。"
            "参数: status (案件状态筛选: 待审核/审核中/已通过/已拒绝/已关闭, 为空查全部)、page (页码, 默认1)。"
            "返回: 案件列表 + 统计信息。"
        )
    )
    async def query_cases(status: str = "", page: int = 1) -> str:
        return await _safe_call("案件查询", _query_cases_impl, status=status, page=page)

    @tool(
        description=(
            "查询经销商的风险画像。"
            "参数: user_id (经销商ID, 如 'D002')。"
            "返回: 风险评分、订货统计、保修/维修次数、合同状态; 没评估过时返回经销商档案。"
        )
    )
    async def query_dealer_profile(user_id: str) -> str:
        return await _safe_call("经销商画像查询", _query_dealer_profile_impl, user_id=user_id)

    @tool(
        description=(
            "管理风控黑名单。"
            "参数: action (add/remove/check/list)、blacklist_type (经销商ID/设备SN/维修工/用户)、"
            "value (黑名单值)、reason (加黑原因)。返回操作结果。"
        )
    )
    async def manage_blacklist(
        action: str, blacklist_type: str = "经销商ID", value: str = "", reason: str = "",
    ) -> str:
        return await _safe_call("黑名单操作", _manage_blacklist_impl,
                                action=action, blacklist_type=blacklist_type,
                                value=value, reason=reason)

    @tool(
        description=(
            "查询风控仪表盘统计数据: 今日评估数、待审案件数、拒绝案件数、启用规则数、决策分布。"
            "返回: JSON 字符串。"
        )
    )
    async def query_dashboard_stats() -> str:
        return await _safe_call("统计查询", _query_dashboard_stats_impl)

    @tool(
        description=(
            "分析指定天数内的风控趋势。"
            "参数: days (分析天数, 默认30)。"
            "返回: 每日评估量 / 风险等级分布 / 决策分布 (JSON)。"
        )
    )
    async def analyze_risk_trend(days: int = 30) -> str:
        return await _safe_call("趋势分析", _analyze_risk_trend_impl, days=days)

    @tool(
        description=(
            "分析所有启用规则的命中效果: 每条规则的命中次数、命中率。"
            "返回: JSON 字符串 (total_assessments / rules[...])。"
        )
    )
    async def analyze_rule_effectiveness() -> str:
        return await _safe_call("规则效果分析", _analyze_rule_effectiveness_impl)

    @tool(
        description=(
            "查询制造业业务数据。"
            "参数: query_type (dealer_orders 经销商订货单/dealer_info 经销商档案/warranty_list 保修维修记录/"
            "report_list 串货举报/order_detail 订单详情/recent_orders 最近订货)、"
            "dealer_id、order_id、limit (返回数量, 默认10)。返回业务数据 (JSON)。"
        )
    )
    async def query_business_data(
        query_type: str, dealer_id: str = "", order_id: str = "", limit: int = 10,
    ) -> str:
        return await _safe_call("业务数据查询", _query_business_data_impl,
                                query_type=query_type, dealer_id=dealer_id,
                                order_id=order_id, limit=limit)

    llm = ChatOpenAI(
        model=settings.LLM_MODEL_NAME,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.1,  # 低温=答案更确定, 适合业务场景
    )
    return create_deep_agent(
        model=llm,
        tools=[risk_check, query_cases, query_dealer_profile, manage_blacklist,
               query_dashboard_stats, analyze_risk_trend, analyze_rule_effectiveness,
               query_business_data],
        system_prompt=SYSTEM_PROMPT,
    )


def get_agent():
    """获取全局唯一的 Agent 实例 (进程内 1 个就够, 多次创建浪费 LLM 握手)."""
    global _agent
    if _agent is None:
        _agent = _create_agent()
        logger.info("DeepAgent 创建成功: model=%s tools=8", settings.LLM_MODEL_NAME)
    return _agent


async def chat_llm(message: str, history: list) -> tuple[str, list]:
    """走 LLM 对话 (history 为 langchain 消息列表), 返回 (reply, 新 history)."""
    agent = get_agent()
    try:
        result = await agent.ainvoke({"messages": history})
        messages = result.get("messages", [])
        if messages:
            return messages[-1].content, messages
        return "抱歉，未能生成回复。", history
    except Exception as e:
        logger.exception("LLM Agent 执行异常")
        return f"Agent 执行出错: {e}", history
