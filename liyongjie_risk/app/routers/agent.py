"""
银行风控系统 - AI Agent 对话 API
================================
POST /api/agent/chat  — AI 风控助手对话

基于 LLM 的智能风控助手, 支持自然语言交互查询和分析.
当 openai 未安装或 LLM_API_KEY 未配置时, 返回模拟回复以保证前端可用.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import AgentChatRequest, AgentChatResponse

logger = logging.getLogger(__name__)

agent_router = APIRouter(prefix="/api/agent", tags=["AI Agent"])

# 尝试导入 LLM 客户端 (如果 openai 未安装则降级到模拟回复)
_OPENAI_AVAILABLE = False
_AGENT_CHAT = None
try:
    from app.agent.chat import chat as _agent_chat_impl
    _AGENT_CHAT = _agent_chat_impl
    _OPENAI_AVAILABLE = True
except Exception as e:
    logger.warning("AI Agent 初始化失败 (可能缺少 openai 包): %s, 将使用模拟回复", e)


def _fallback_reply(message: str) -> str:
    """模拟 AI 回复 (当 LLM 不可用时)."""
    t = message.lower() if message else ""
    if "统计" in t or "今日" in t:
        return (
            "📊 **今日风控统计** (模拟数据)\n\n"
            "1. 总事件数: **156** 笔\n"
            "2. 通过: **128** 笔 (82.1%)\n"
            "3. 增强验证: **15** 笔 (9.6%)\n"
            "4. 人工复核: **8** 笔 (5.1%)\n"
            "5. 拒绝: **5** 笔 (3.2%)\n\n"
            "⚠️ AI 服务未连接, 以上为模拟数据。请配置 LLM API 后获取实时分析。"
        )
    if "高风险" in t or "风险事件" in t:
        return (
            "⚠️ **近期高风险事件概览** (模拟)\n\n"
            "1. 大额转账异常 — 用户 USR00005, ¥50,000, 评分 85\n"
            "2. 异地登录告警 — 用户 USR00012, IP 10.0.0.55, 评分 78\n"
            "3. 贷款申请异常 — 用户 USR00010, ¥200,000, 评分 72\n\n"
            "趋势: 近7天高风险事件呈上升趋势 ↑12%"
        )
    if "画像" in t or "风险画像" in t:
        return (
            "👤 **用户风险画像** (模拟)\n\n"
            "- 用户ID: USR00005\n"
            "- 风险等级: **高**\n"
            "- 近30天交易: 47 笔\n"
            "- 命中规则: R003(大额转账), R012(异地操作), R025(夜间交易)\n"
            "- 关联设备: 3 个\n"
            "- 关联IP: 5 个\n"
            "- 建议: 触发增强验证, 限制单日额度"
        )
    if "规则" in t or "命中率" in t:
        return (
            "📋 **规则命中率 TOP 5** (模拟)\n\n"
            "| 规则ID | 名称 | 命中次数 | 占比 |\n"
            "|--------|------|----------|------|\n"
            "| R003 | 大额转账检测 | 45 | 28.8% |\n"
            "| R010 | 异地登录告警 | 32 | 20.5% |\n"
            "| R025 | 夜间交易检测 | 28 | 17.9% |\n"
            "| R015 | 短时高频交易 | 22 | 14.1% |\n"
            "| R038 | 电信诈骗模式 | 18 | 11.5% |"
        )
    if "趋势" in t:
        return (
            "📈 **近7天风控趋势** (模拟)\n\n"
            "- 总事件: 1,092 笔 (日均 156)\n"
            "- 通过率: 82.1% → 79.5% (↓2.6%)\n"
            "- 拒绝率: 3.2% → 4.8% (↑1.6%)\n"
            "- 人工复核率: 5.1% → 6.3% (↑1.2%)\n\n"
            "建议: 关注拒绝率上升趋势, 检查是否存在规则过严或新型攻击模式。"
        )
    return (
        "您好! 我是银行风控 AI 助手。\n\n"
        "您可以尝试问我:\n"
        '- "查询今日风控数据统计"\n'
        '- "分析高风险事件"\n'
        '- "查看用户风险画像"\n'
        '- "风控规则命中率分析"\n'
        '- "近一周风控趋势"\n\n'
        "⚠️ 当前 AI 服务未连接, 以上为离线回复。请配置 LLM API Key 后使用完整功能。"
    )


@agent_router.post("/chat", response_model=AgentChatResponse)
async def api_agent_chat(
    data: AgentChatRequest,
    db: AsyncSession = Depends(get_db_async),
):
    """
    AI 风控助手对话.

    支持的功能:
      - 查询风控数据统计和趋势
      - 分析用户风险画像
      - 查看和解释风控规则
      - 提供风控策略建议
      - 解读风险事件详情
    """
    if _OPENAI_AVAILABLE and _AGENT_CHAT is not None:
        try:
            result = await _AGENT_CHAT(
                db=db,
                message=data.message,
                context=data.context,
            )
            return AgentChatResponse(
                reply=result["reply"],
                session_id=data.session_id,
                tool_calls_made=result.get("tool_calls_made", []),
            )
        except Exception as e:
            logger.exception("AI Agent 调用异常: %s", e)

    # 降级到模拟回复
    reply = _fallback_reply(data.message)
    return AgentChatResponse(
        reply=reply,
        session_id=data.session_id,
        timestamp=datetime.now(),
    )
