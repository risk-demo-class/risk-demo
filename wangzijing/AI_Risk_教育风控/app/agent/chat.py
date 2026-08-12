"""
AI Agent 入口 (基于 LangChain DeepAgents).
模型: 阿里云百炼 qwen-plus (settings.LLM_* 配置). 工具: 8 个 @tool.
"""

import asyncio
import json
import logging
import re
from typing import Optional

import ulid
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent

from app.agent.tools import (
    ALL_TOOLS,
    analyze_rule_effectiveness,
    query_cases,
    query_dashboard_stats,
    query_user_profile,
)
from app.config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是教育行业风控系统的AI助手，负责协助风控分析师完成以下工作:

1. **风险检查**: 对课程报名、退费申请、学历认证执行实时风控评估
2. **案件管理**: 查询和分析待审核/已处理的风控案件
3. **用户画像**: 查看用户的风险评分、行为特征、历史记录
4. **黑名单管理**: 查询、添加、移除黑名单
5. **数据分析**: 统计仪表盘、趋势分析、规则命中效果
6. **业务查询**: 查看课程报名、学习进度、退费、认证和设备数据

工作原则:
- 根据用户问题，选择合适的工具获取数据
- 用中文回答，结果需要简洁清晰
- 对风险数据给出专业的分析解读
- 可以组合多个工具完成复杂分析任务
- 当数据不足时，主动补充查询相关信息
- 身份证、学号、设备和IP只展示哈希值，不索取或输出真实个人信息
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


def _parse_tool_json(raw: str) -> dict:
    """解析本地工具结果；工具失败时把可读错误交给上层展示。"""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(raw or "本地工具没有返回有效数据") from exc


async def _local_tool_reply(message: str) -> str:
    """无大模型密钥时，为四个只读快捷问题提供确定性本地查询。"""
    text = message.strip()
    upper_text = text.upper()

    if "规则" in text and any(word in text for word in ("效果", "命中", "分析", "统计")):
        data = _parse_tool_json(await analyze_rule_effectiveness.ainvoke({}))
        rules = sorted(data.get("rules", []), key=lambda item: item.get("hit_count", 0), reverse=True)
        lines = [
            "**规则效果分析（本地查询）**",
            f"- 评估总数：{data.get('total_assessments', 0)}",
        ]
        if rules:
            lines.append("- 高频规则：")
            lines.extend(
                f"  {index}. {item.get('rule_id', '-')} {item.get('rule_name', '')}："
                f"命中 {item.get('hit_count', 0)} 次，命中率 {item.get('hit_rate_pct', 0)}%"
                for index, item in enumerate(rules[:5], 1)
            )
        else:
            lines.append("- 当前还没有规则命中数据。")
        return "\n".join(lines)

    if any(word in text for word in ("待审", "案件", "复核")):
        data = _parse_tool_json(await query_cases.ainvoke({"status": "待审核", "page": 1}))
        stats = data.get("statistics", {})
        cases = data.get("cases", [])
        lines = [
            "**待审核案件（本地查询）**",
            f"- 待审核：{stats.get('pending', data.get('total', 0))} 条",
            f"- 审核中：{stats.get('reviewing', 0)} 条",
        ]
        if cases:
            lines.append("- 前5条待审案件：")
            lines.extend(
                f"  {index}. {item.get('case_id', '-')}｜用户 {item.get('user_id', '-')}｜"
                f"{item.get('case_category') or '未分类'}｜{item.get('case_status', '-')}"
                for index, item in enumerate(cases[:5], 1)
            )
        else:
            lines.append("- 当前没有待审核案件。")
        return "\n".join(lines)

    user_match = re.search(r"\b(?:RISK|EDU)\d+\b", upper_text)
    if user_match and any(word in text for word in ("用户", "画像", "风险", "分析")):
        user_id = user_match.group(0)
        data = _parse_tool_json(await query_user_profile.ainvoke({"user_id": user_id}))
        if data.get("has_profile") is False:
            features = data.get("computed_features", {})
            return "\n".join([
                f"**用户 {user_id} 风险画像（实时计算）**",
                "- 尚未形成持久化风险画像，已读取当前业务特征。",
                f"- 累计报名：{features.get('user_total_orders', 0):g} 次",
                f"- 成功退费：{features.get('user_refund_count', 0):g} 次",
                f"- 成功退费率：{features.get('user_refund_rate', 0):.2%}",
                f"- 关联设备：{features.get('user_address_count', 0):g} 个",
                f"- 认证失败：{features.get('user_complaint_count', 0):g} 次",
            ])
        return "\n".join([
            f"**用户 {user_id} 风险画像（本地查询）**",
            f"- 风险分：{data.get('risk_score', 0)} / 100",
            f"- 风险等级：{data.get('risk_level', '低')}",
            f"- 累计报名：{data.get('total_orders', 0)} 次",
            f"- 成功退费：{data.get('total_refunds', 0)} 次",
            f"- 退费率：{float(data.get('refund_rate', 0) or 0):.2%}",
            f"- 关联设备：{data.get('address_count', 0)} 个",
            f"- 认证失败：{data.get('complaint_count', 0)} 次",
            f"- 历史评估：{data.get('assessment_count', 0)} 次",
        ])

    if any(word in text for word in ("统计", "态势", "趋势", "今天", "今日", "看板")):
        data = _parse_tool_json(await query_dashboard_stats.ainvoke({}))
        trend = data.get("trend_7d", [])
        seven_day_total = sum(int(item.get("count", 0)) for item in trend)
        seven_day_high = sum(int(item.get("high_risk_count", 0)) for item in trend)
        lines = [
            "**今日风控态势（本地查询）**",
            f"- 今日评估：{data.get('today_assessments', 0)} 条",
            f"- 今日高风险：{data.get('today_high_risk', 0)} 条",
            f"- 今日通过率：{data.get('pass_rate', 0)}%",
            f"- 待审核案件：{data.get('pending_cases', 0)} 条",
            f"- 近7天评估：{seven_day_total} 条，其中高风险 {seven_day_high} 条",
        ]
        top_rules = data.get("top_rules", [])
        if top_rules:
            lines.append(
                "- 命中最多规则：" + "、".join(
                    f"{item.get('rule_id')}（{item.get('hit_count', 0)}次）"
                    for item in top_rules[:3]
                )
            )
        return "\n".join(lines)

    return (
        "当前处于**本地查询模式**，可以查询“今日风险态势”“待审案件”"
        "“用户 RISK009 风险画像”或“规则效果分析”。如需开放式AI问答，请在 `.env` "
        "中配置有效的 `LLM_API_KEY` 后重启系统。"
    )


async def chat(
    message: str,
    session_id: Optional[str] = None,
) -> tuple[str, str]:
    """与 AI Agent 对话 (异步). 异常被捕获返 "Agent 执行出错: {e}" 不 raise."""
    if not session_id:
        session_id = f"sess_{ulid.new().str.lower()}"

    # 加锁保护: 避免两个请求同时改同一 session 丢消息
    async with _sessions_lock:
        history = _sessions.setdefault(session_id, [])
        history.append(HumanMessage(content=message))

    if not settings.LLM_API_KEY.strip():
        try:
            reply = await _local_tool_reply(message)
        except Exception:
            logger.exception("本地查询模式执行异常")
            reply = "本地风控查询暂时失败，请检查MySQL连接和数据库初始化状态。"
        async with _sessions_lock:
            _sessions[session_id].append(AIMessage(content=reply))
        return reply, session_id

    try:
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
    except Exception:
        logger.exception("Agent 执行异常")
        reply = "AI服务暂时不可用，请检查大模型密钥、网络连接和模型名称后重试。"

    return reply, session_id


def clear_session(session_id: str) -> bool:
    """清除指定会话的历史消息. 内存存储, 进程重启就全没了."""
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False
