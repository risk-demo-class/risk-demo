"""
AI Agent 入口 (基于 LangChain DeepAgents, 真实大模型 API).

模型: 阿里云百炼 qwen-plus (settings.LLM_* 配置). 工具: 8 个 @tool (银行语义).
"""
import asyncio
import json
import logging
import uuid
from typing import Any, List, Optional

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

try:
    from langchain.agents import create_agent
    from deepagents import create_deep_agent
    _HAS_DEEPAGENTS = True
except Exception:  # deepagents 未安装时降级为普通 agent
    from langchain.agents import create_agent  # type: ignore
    _HAS_DEEPAGENTS = False

from app.agent.tools import ALL_TOOLS
from app.config import settings

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是银行风控系统的AI助手，负责协助风控分析师完成以下工作:

1. **风险检查**: 对指定用户/交易执行实时风控评估 (转账/贷款/卡交易/还款/登录)
2. **案件管理**: 查询和分析待审核/已处理的风控案件
3. **用户画像**: 查看用户的风险评分、行为特征、历史记录
4. **黑名单管理**: 查询、添加、移除黑名单 (账户/设备/IP/手机号/证件/商户/受益人)
5. **数据分析**: 统计仪表盘、趋势分析、规则命中效果
6. **业务查询**: 查看风险检查与评估历史

工作原则:
- 根据用户问题，选择合适的工具获取数据
- 用中文回答，结果简洁清晰
- 对风险数据给出专业的分析解读
- 可以组合多个工具完成复杂分析任务
- 当数据不足时，主动补充查询相关信息
"""


_agent = None


def _create_agent():
    llm = ChatOpenAI(
        model=settings.LLM_MODEL_NAME,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=0.1,
    )
    if _HAS_DEEPAGENTS:
        return create_deep_agent(model=llm, tools=ALL_TOOLS, system_prompt=SYSTEM_PROMPT)
    return create_agent(llm, ALL_TOOLS, system_message=SYSTEM_PROMPT)


def get_agent():
    global _agent
    if _agent is None:
        _agent = _create_agent()
    return _agent


def _extract_text(content: Any) -> str:
    """统一解析 AIMessage.content 为纯文本, 兼容 str 与 list[dict]

    list 形态 (如 Anthropic/部分 OpenAI 兼容返回) 可能含 text / tool_use 块,
    仅拼接 text 块, 跳过 tool_use 占位, 避免把工具调用误当思考。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p)
    return str(content)


def _build_thinking(messages: list) -> Optional[str]:
    """遍历消息流, 提取思考过程: 中间 AIMessage 规划文本 + 所有 tool_calls 步骤。

    返回 None 表示无思考内容 (前端据此不渲染面板)。
    """
    try:
        ai_messages = [m for m in messages if getattr(m, "type", None) == "ai"]
        if not ai_messages:
            return None

        # 最后一条 AIMessage 视为最终回复, 其余为中间规划思考
        plan_ais = ai_messages[:-1]
        lines: List[str] = []

        for m in plan_ais:
            text = _extract_text(getattr(m, "content", "")).strip()
            if text:
                lines.append(f"💭 {text}")

        # 收集所有 AIMessage 的 tool_calls 作为工具调用步骤
        for m in ai_messages:
            tool_calls = getattr(m, "tool_calls", None) or []
            for tc in tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", None)
                try:
                    args_str = json.dumps(args, ensure_ascii=False)
                except Exception:
                    args_str = str(args)
                if name:
                    lines.append(f"→ 调用 {name}({args_str})")

        thinking = "\n".join(lines).strip()
        return thinking or None
    except Exception as e:
        logger.warning("思考过程提取失败, 已降级为空: %s", e)
        return None


_sessions: dict[str, list] = {}
_sessions_lock = asyncio.Lock()


async def chat(message: str, session_id: Optional[str] = None) -> tuple[str, str, Optional[str]]:
    if not session_id:
        session_id = f"sess_{uuid.uuid4().hex}"

    # 未配置 LLM API Key 时, 给出友好提示而非初始化失败
    if not settings.LLM_API_KEY:
        return (
            "⚠️ 当前未配置 LLM API Key, AI 助手不可用。\n"
            "请在项目根目录 .env 中设置 LLM_API_KEY=你的阿里云百炼/OpenAI 兼容密钥, "
            "并重启服务后重试。其他风控功能（决策/规则/案件/黑名单/评估）不受影响。",
            session_id,
            None,
        )

    async with _sessions_lock:
        history = _sessions.get(session_id, [])
        history.append(HumanMessage(content=message))

    agent = get_agent()
    try:
        result = await agent.ainvoke({"messages": history})
        messages = result.get("messages", [])
        if messages:
            reply = _extract_text(messages[-1].content)
            async with _sessions_lock:
                _sessions[session_id] = messages
        else:
            reply = "抱歉，未能生成回复。"
        # 提取思考过程 (中间规划 + 工具调用步骤), 失败不影响 reply
        thinking = _build_thinking(messages)
    except Exception as e:
        logger.exception("Agent 执行异常")
        reply = f"Agent 执行出错: {e}"
        thinking = None

    return reply, session_id, thinking


def clear_session(session_id: str) -> bool:
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False
