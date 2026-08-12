"""
银行风控系统 - AI 风控分析 Agent
===============================
基于 LLM 的智能风控助手, 支持自然语言交互查询和分析.

【功能】
  - 查询用户风险画像: "帮我分析用户 3 的风险情况"
  - 查询规则配置: "当前有哪些转账相关的规则?"
  - 查询黑名单: "查看银行卡号类型的黑名单"
  - 交易分析: "用户 5 最近的交易记录"
  - 风险事件复盘: "用户 8 的历史风险事件"
  - 给出风控建议: "针对用户 12 的情况, 有什么风控建议?"

【工作流程】
  1. 用户输入自然语言问题
  2. Agent 理解意图 → 选择对应工具
  3. 执行工具调用 → 获取数据
  4. LLM 分析数据 → 生成自然语言回复

【技术栈】
  LLM: 阿里云百炼 (qwen-plus)
  框架: OpenAI-compatible API
"""
import json
import logging
from datetime import datetime

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import (
    query_user_info,
    query_user_transactions,
    query_user_risk_events,
    query_rule_config,
    query_blacklist,
    analyze_user_risk,
)
from app.config import settings

logger = logging.getLogger(__name__)

# 工具定义 (OpenAI function calling 格式)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_user_risk",
            "description": "综合分析用户风险画像, 返回用户信息、交易统计、风险事件汇总和风险等级评估",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "用户 ID"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_user_transactions",
            "description": "查询用户近期交易记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "用户 ID"},
                    "limit": {"type": "integer", "description": "返回条数, 默认 20"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_rule_config",
            "description": "查询风控规则配置, 可按场景过滤 (登录/转账/贷款/信用卡)",
            "parameters": {
                "type": "object",
                "properties": {
                    "scene": {"type": "string", "description": "场景: 登录/转账/贷款/信用卡"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_blacklist",
            "description": "查询有效黑名单, 可按类型过滤",
            "parameters": {
                "type": "object",
                "properties": {
                    "bl_type": {"type": "integer", "description": "类型: 1=设备, 2=IP, 3=银行卡号, 4=身份证, 5=手机号"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_user_risk_events",
            "description": "查询用户历史风险事件",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer", "description": "用户 ID"},
                    "limit": {"type": "integer", "description": "返回条数, 默认 20"},
                },
                "required": ["user_id"],
            },
        },
    },
]

TOOL_MAP = {
    "analyze_user_risk": analyze_user_risk,
    "query_user_transactions": query_user_transactions,
    "query_rule_config": query_rule_config,
    "query_blacklist": query_blacklist,
    "query_user_risk_events": query_user_risk_events,
    "query_user_info": query_user_info,
}

SYSTEM_PROMPT = """你是银行风控系统的 AI 分析助手. 你可以帮助风控人员:
1. 查询和分析用户风险画像
2. 查看规则配置和命中情况
3. 查询黑名单
4. 分析交易模式, 识别欺诈风险
5. 给出风控处置建议

你的回复应该:
- 专业、准确、基于数据
- 对高风险发现重点标注
- 给出具体可行的建议
- 使用中文回复

注意: 所有数据查询都通过工具函数完成, 不要编造数据.
"""


async def chat(
    db: AsyncSession,
    message: str,
    context: dict | None = None,
) -> dict:
    """
    AI 风控助手对话入口.

    Args:
        db: 数据库 Session
        message: 用户消息
        context: 上下文 (如当前查看的案件/用户)

    Returns:
        {"reply": str, "tool_calls_made": list[str], "timestamp": str}
    """
    if not settings.LLM_API_KEY:
        return {
            "reply": "AI Agent 未配置 (LLM_API_KEY 为空), 请先配置 .env 中的 LLM_API_KEY.",
            "tool_calls_made": [],
            "timestamp": datetime.now().isoformat(),
        }

    client = AsyncOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        timeout=settings.AI_AGENT_CHAT_TIMEOUT_SEC,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    if context:
        messages.append({
            "role": "system",
            "content": f"当前上下文: {json.dumps(context, ensure_ascii=False)}",
        })
    messages.append({"role": "user", "content": message})

    tool_calls_made = []

    try:
        # 第一轮: LLM 决定是否调用工具
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL_NAME,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.3,
        )

        assistant_msg = response.choices[0].message

        # 如果 LLM 选择调用工具
        if assistant_msg.tool_calls:
            messages.append(assistant_msg)

            for tool_call in assistant_msg.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)

                tool_calls_made.append(f"{func_name}({func_args})")

                # 执行工具
                tool_func = TOOL_MAP.get(func_name)
                if tool_func:
                    try:
                        result = await tool_func(db, **func_args)
                    except Exception as e:
                        result = {"error": str(e)}
                else:
                    result = {"error": f"未知工具: {func_name}"}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })

            # 第二轮: LLM 基于工具结果生成回复
            final_response = await client.chat.completions.create(
                model=settings.LLM_MODEL_NAME,
                messages=messages,
                temperature=0.3,
            )
            reply = final_response.choices[0].message.content or "分析完成, 但未生成文本回复."

        else:
            reply = assistant_msg.content or "分析完成."

    except Exception as e:
        logger.exception("AI Agent 对话异常: %s", e)
        reply = f"AI 分析服务暂时不可用: {str(e)}"

    return {
        "reply": reply,
        "tool_calls_made": tool_calls_made,
        "timestamp": datetime.now().isoformat(),
    }
