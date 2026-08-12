"""
AI Agent 入口 (双层架构).

  1. LLM 模式:    .env 配了 LLM_API_KEY 且 langchain/deepagents 已装 → DeepAgent
                  (工具: 8 个制造业工具, 模型: DeepSeek deepseek-v4-flash, 见 llm_agent.py)
  2. 内置规则模式: 没 key 或没装依赖时的兜底 — 关键词意图识别 + 直接查库回答
                  (零外部依赖, 开箱即用)

会话消息存储: 内存级别 (重启丢失, 不持久化).
"""
import asyncio
import logging
import re
from typing import Optional

import ulid

from app.agent.llm_agent import chat_llm, llm_available
from app.config import settings

logger = logging.getLogger(__name__)


async def chat(
    message: str,
    session_id: Optional[str] = None,
) -> tuple[str, str]:
    """与 AI 助手对话 (异步). 异常被捕获返错误串, 不 raise."""
    if not session_id:
        session_id = f"sess_{ulid.new().str.lower()}"

    # ---- LLM 模式 ----
    if llm_available():
        try:
            from langchain_core.messages import HumanMessage
        except ImportError:
            pass
        else:
            async with _sessions_lock:
                history = _sessions.get(session_id, [])
                history.append(HumanMessage(content=message))
            reply, new_history = await chat_llm(message, history)
            async with _sessions_lock:
                _sessions[session_id] = new_history
            return reply, session_id

    # ---- 内置规则模式 ----
    reply = await _rule_reply(message)
    return reply, session_id


def clear_session(session_id: str) -> bool:
    """清除指定会话的历史消息."""
    if session_id in _sessions:
        del _sessions[session_id]
        return True
    return False


# 会话消息存储 (内存级别)
_sessions: dict[str, list] = {}
_sessions_lock = asyncio.Lock()


# ============================================================
# 内置规则模式 (无 LLM 兜底)
# ============================================================

_ID_RE = re.compile(r"(?:ORD\d+|WAR\d+|REP\d+|D\d+|U\d+|SN[\w\-]+|T\d+)")
_EVENT_RE = {
    "经销商订货": ["订货", "下单", "采购", "订货单"],
    "保修申请": ["保修申请", "申请保修", "保修"],
    "售后维修": ["维修", "售后"],
    "串货举报": ["串货", "举报", "窜货"],
}
_BLACKLIST_TYPE_RE = {
    "经销商ID": ["经销商", "dealer"],
    "设备SN": ["sn", "设备"],
    "维修工": ["维修工", "技师", "technician"],
    "用户": ["用户"],
}
_BIZ_TYPE_RE = {
    "dealer_orders": ["订货", "订单", "下单"],
    "dealer_info": ["档案", "经销商信息", "资质"],
    "warranty_list": ["保修", "维修", "售后"],
    "report_list": ["举报", "串货", "窜货"],
    "recent_orders": ["最近", "最新"],
}


def _pick_id(message: str, prefixes: tuple[str, ...]) -> str:
    """从消息里按前缀挑第 1 个 ID."""
    for m in _ID_RE.findall(message):
        if m.startswith(prefixes):
            return m
    return ""


def _extract_days(message: str) -> int:
    """'近 N 天' → N; 默认 30."""
    m = re.search(r"近\s*(\d+)\s*天", message)
    return int(m.group(1)) if m else 30


async def _rule_reply(message: str) -> str:
    """内置规则问答: 关键词意图识别 → 调工具 → 返回可读结果."""
    from app.agent.tools import TOOL_REGISTRY, _safe_call

    # 0. 支持「第N项」/ 纯数字序号说法 (对齐 chat.html 欢迎语的 1-6 项)
    idx_map = {
        "1": "risk_check", "2": "query_cases", "3": "query_dealer_profile",
        "4": "query_dashboard_stats", "5": "manage_blacklist", "6": "analyze_rule_effectiveness",
    }
    m_idx = re.search(r"第\s*([1-6])\s*项", message)
    if not m_idx:
        stripped = message.strip()
        if re.fullmatch(r"[1-6]", stripped):
            m_idx = re.match(r"([1-6])", stripped)
    if m_idx:
        name = idx_map[m_idx.group(1)]
        if name == "risk_check":
            return ("第1项是风险检查。请提供完整参数, 例如: "
                    "对 ORD003 做经销商订货风险检查 user=D002")
        if name == "query_dealer_profile":
            return "第3项是经销商画像。请提供经销商ID, 例如: 分析 D002 的风险画像"
        if name == "query_dashboard_stats":
            return "第4项是统计和趋势。试试: 查看今天的风控统计 / 查看近7天的风控趋势"
        if name == "manage_blacklist":
            bl_tool = next(t for t in TOOL_REGISTRY if t["name"] == "manage_blacklist")
            result = await _safe_call("黑名单操作", bl_tool["handler"],
                                      action="list", blacklist_type="经销商ID", value="", reason="")
            return f"[manage_blacklist] {result}"
        best_tool = next(t for t in TOOL_REGISTRY if t["name"] == name)
        kwargs = {}
        if name == "query_cases":
            kwargs = {"status": "", "page": 1}
        elif name == "analyze_rule_effectiveness":
            kwargs = {}
        result = await _safe_call(name, best_tool["handler"], **kwargs)
        return f"[{name}] {result}"

    # 1. 意图匹配: 关键词命中数最多的工具
    best_tool, best_hits = None, 0
    for t in TOOL_REGISTRY:
        hits = sum(1 for kw in t["keywords"] if kw in message)
        if hits > best_hits:
            best_hits, best_tool = hits, t
    if best_tool is None or best_hits == 0:
        return ("我还没听明白你的问题。可以试试这些说法:\n"
                "- 查看今天的统计\n- 查待审核的案件\n- 分析 D002 的风险画像\n"
                "- 查黑名单\n- 对 ORD003 做风险检查 (经销商订货)\n- 分析规则命中效果")

    name = best_tool["name"]
    kwargs = {}

    # 2. 按工具抽取参数
    if name == "risk_check":
        event_type = next((ev for ev, kws in _EVENT_RE.items() if any(k in message for k in kws)), "")
        if not event_type:
            return "执行风险检查需要事件类型: 经销商订货 / 保修申请 / 售后维修 / 串货举报。\n例如: 对 ORD003 做经销商订货风险检查 (user=D002)"
        source_id = _pick_id(message, ("ORD", "WAR", "REP")) or ""
        user_id = _pick_id(message, ("D", "U")) or ""
        if not source_id or not user_id:
            return f"请提供完整的业务ID和经销商ID。例如: 对 ORD003 做{event_type}风险检查, user=D002"
        kwargs = {"user_id": user_id, "event_type": event_type, "source_id": source_id}

    elif name == "query_cases":
        status = next((s for s in ["待审核", "审核中", "已通过", "已拒绝", "已关闭"] if s in message), "")
        kwargs = {"status": status, "page": 1}

    elif name == "query_dealer_profile":
        user_id = _pick_id(message, ("D", "U")) or ""
        if not user_id:
            return "请提供经销商ID。例如: 分析 D002 的风险画像"
        kwargs = {"user_id": user_id}

    elif name == "manage_blacklist":
        action = "list"
        if any(k in message for k in ["添加", "加黑", "拉黑", "加入"]):
            action = "add"
        elif any(k in message for k in ["移除", "删除", "删掉", "解除"]):
            action = "remove"
        elif any(k in message for k in ["在不在", "是否在", "查一下", "检查"]):
            action = "check"
        bl_type = next((t for t, kws in _BLACKLIST_TYPE_RE.items() if any(k in message for k in kws)), "经销商ID")
        value = _pick_id(message, ("D", "U", "SN", "T")) or ""
        kwargs = {"action": action, "blacklist_type": bl_type, "value": value,
                  "reason": "AI助手添加" if action == "add" else ""}

    elif name == "query_dashboard_stats":
        kwargs = {}

    elif name == "analyze_risk_trend":
        kwargs = {"days": _extract_days(message)}

    elif name == "analyze_rule_effectiveness":
        kwargs = {}

    elif name == "query_business_data":
        query_type = next((q for q, kws in _BIZ_TYPE_RE.items() if any(k in message for k in kws)), "recent_orders")
        dealer_id = _pick_id(message, ("D",)) or ""
        order_id = _pick_id(message, ("ORD",)) or ""
        kwargs = {"query_type": query_type, "dealer_id": dealer_id,
                  "order_id": order_id, "limit": 10}

    # 3. 执行 (复用 _safe_call: 异常自动转字符串)
    result = await _safe_call(name, best_tool["handler"], **kwargs)
    return f"[{name}] {result}"


# ============================================================
# Demo: 展示内置规则模式的意图匹配 + 参数抽取 — 无需 DB
# 跑法: python -m app.agent.chat
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("AI 助手入口 — 双层架构")
    print("=" * 60)
    print(f"\n  LLM 可用 (有 key + 依赖) = {llm_available()}")
    print(f"  LLM 模型                = {settings.LLM_MODEL_NAME or '(未配置)'}")
    print(f"  LLM 模式: DeepAgent (langchain + deepagents)")
    print(f"  内置模式: 关键词意图识别 + 直接查库 (零依赖)")

    print("\n[1] 内置规则模式 — 意图识别示例 (参数抽取, 不连库):")
    samples = [
        "查看今天的统计",
        "查待审核的案件",
        "分析 D002 的风险画像",
        "查黑名单",
        "分析规则命中效果",
        "近7天趋势",
        "D002 的订货单",
        "对 ORD003 做经销商订货风险检查 user=D002",
    ]
    for s in samples:
        print(f"  「{s}」")
