# -*- coding: utf-8 -*-
"""L5 AI 层 · chat.py —— 懒加载 Agent + 会话管理 + SSE 流式

对应教学宝典《第 11 章》，四个设计哲学**逐条落地**：

| 宝典 11.3 设计哲学 | 本文件实现 |
|-------------------|-----------|
| ① 懒加载 Agent（`_agent = None`，第一次 `get_agent()` 才创建）| `_AGENT = None` + `get_agent()`，import 时绝不建连接 |
| ② 温度 0.1（业务要稳定）| `settings.LLM_TEMPERATURE = 0.1` 传给 ChatOpenAI |
| ③ 内存级会话 + Lock（重启丢失，生产换 Redis）| `_SESSIONS: dict` + `_session_lock()`，同 session 串行 |
| ④ 超时 60s（防 LLM 卡死）| `settings.AI_AGENT_CHAT_TIMEOUT_SEC`，urllib timeout + 逐轮 deadline |

**双运行模式**（教学环境常常没有 API Key / 没有 LangChain）：

* `llm` 模式：配了 `LLM_API_KEY` → 走**硅基流动（SiliconFlow）**等 OpenAI 兼容协议，
  带 function calling，模型自己决定调哪个工具（标准库 urllib 直连，零依赖）。
  最终自然语言回答由大模型**真实流式输出**（SSE token 流，前端逐字渲染）。
* `local` 模式：没 Key → **本地意图路由**，按关键词命中 8 个工具之一并直接执行，
  用模板生成中文分析结论。功能可用、流程可看，只是没有 LLM 的自由表达。

两种模式对外接口完全一致（都产出 SSE 事件流），前端无需区分。
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from app.config import settings
from app.agent import tools as tool_module

logger = logging.getLogger("ai_risk.agent.chat")

# 供应商中文名（thinking 事件展示用）
_PROVIDER_LABEL = {"siliconflow": "硅基流动", "dashscope": "阿里云百炼", "openai": "OpenAI"}

# ====================================================================== 宝典 11.4 SYSTEM_PROMPT
SYSTEM_PROMPT = """你是教育风控系统的AI助手, 负责协助风控分析专家完成:
1. 风险检查（考试/作业/选课/成绩申诉）  2. 案件管理  3. 用户画像  4. 黑名单管理
5. 数据分析  6. 业务查询

工作原则:
- 根据问题选合适工具
- 中文回答, 简洁清晰
- 给出专业分析解读（学术诚信/学习行为/账号安全/成绩异常/设备风险/身份风险）
- 可组合多个工具
- 数据不足时主动补充询问"""

# ====================================================================== ① 懒加载
_AGENT: Optional["RiskAgent"] = None
_AGENT_LOCK = threading.Lock()
_AGENT_ERROR = ""


# ====================================================================== ③ 内存级会话
_SESSIONS: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
_SESSION_LOCKS: Dict[str, threading.Lock] = {}
_GLOBAL_LOCK = threading.Lock()
MAX_SESSIONS = 200


def _session_lock(session_id: str) -> threading.Lock:
    """宝典 11.3③：`asyncio.Lock` 防并发写同 session。

    本框架是线程模型（ThreadingHTTPServer），等价物是 `threading.Lock`。
    """
    with _GLOBAL_LOCK:
        lock = _SESSION_LOCKS.get(session_id)
        if lock is None:
            lock = threading.Lock()
            _SESSION_LOCKS[session_id] = lock
        return lock


def get_history(session_id: str) -> List[Dict[str, Any]]:
    with _GLOBAL_LOCK:
        return list(_SESSIONS.get(session_id, []))


def _append_history(session_id: str, role: str, content: str) -> None:
    with _GLOBAL_LOCK:
        history = _SESSIONS.setdefault(session_id, [])
        history.append({"role": role, "content": content,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        # 只保留最近 N 轮（宝典 AI_AGENT_MAX_HISTORY）
        limit = max(settings.AI_AGENT_MAX_HISTORY * 2, 4)
        if len(history) > limit:
            del history[: len(history) - limit]
        _SESSIONS.move_to_end(session_id)
        while len(_SESSIONS) > MAX_SESSIONS:         # 内存保护：淘汰最久未用会话
            old, _ = _SESSIONS.popitem(last=False)
            _SESSION_LOCKS.pop(old, None)


def reset_session(session_id: str) -> bool:
    with _GLOBAL_LOCK:
        existed = session_id in _SESSIONS
        _SESSIONS.pop(session_id, None)
        _SESSION_LOCKS.pop(session_id, None)
    return existed


def session_stats() -> Dict[str, Any]:
    with _GLOBAL_LOCK:
        return {"sessions": len(_SESSIONS),
                "messages": sum(len(v) for v in _SESSIONS.values()),
                "max_sessions": MAX_SESSIONS,
                "max_history_turns": settings.AI_AGENT_MAX_HISTORY,
                "note": "内存级会话，服务重启即丢失；生产环境应换 Redis（宝典 11.3③）"}


# ====================================================================== Agent 本体
class RiskAgent:
    """DeepAgents 的零依赖等价物 —— 负责"选工具 → 调工具 → 解读结果"。"""

    def __init__(self) -> None:
        self.tools = tool_module.ALL_TOOLS
        self.specs = tool_module.tool_specs()
        self.impls = tool_module.TOOL_IMPLS
        self.temperature = settings.LLM_TEMPERATURE          # ② 0.1
        self.timeout = settings.AI_AGENT_CHAT_TIMEOUT_SEC    # ④ 60s
        self.model = settings.LLM_MODEL
        self.base_url = settings.LLM_BASE_URL.rstrip("/")
        self.api_key = settings.LLM_API_KEY.strip()
        self.provider = settings.LLM_PROVIDER
        self.mode = "llm" if self.api_key else "local"
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info("Agent 已创建：mode=%s model=%s temperature=%s timeout=%ss tools=%d",
                    self.mode, self.model, self.temperature, self.timeout, len(self.tools))

    # ------------------------------------------------------------------ 元信息
    def info(self) -> Dict[str, Any]:
        return {
            "mode": self.mode, "model": self.model if self.mode == "llm" else "本地意图路由",
            "provider": self.provider if self.mode == "llm" else "-",
            "temperature": self.temperature, "timeout_sec": self.timeout,
            "tool_count": len(self.tools), "created_at": self.created_at,
            "langchain": tool_module._HAS_LANGCHAIN,        # noqa: SLF001
            "system_prompt": SYSTEM_PROMPT,
        }

    # ------------------------------------------------------------------ OpenAI 兼容 function schema
    def _openai_tools(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for spec in self.specs:
            props: Dict[str, Any] = {}
            required: List[str] = []
            for pname, meta in (spec.get("args") or {}).items():
                props[pname] = {"type": meta.get("type", "string")}
                if meta.get("required"):
                    required.append(pname)
            out.append({"type": "function", "function": {
                "name": spec["name"],
                "description": (spec.get("description") or spec.get("purpose") or "")[:900],
                "parameters": {"type": "object", "properties": props, "required": required},
            }})
        return out

    # ------------------------------------------------------------------ HTTP 调 LLM
    def _call_llm(self, messages: List[Dict[str, Any]], deadline: float,
                  stream: bool = False, use_tools: bool = True) -> Any:
        """OpenAI 兼容聊天补全（零依赖 urllib 直连）。

        - ``stream=True``：返回未关闭的 ``HTTPResponse``，由调用方逐行解析 SSE。
        - ``use_tools=False``：关闭 function calling（合成最终回答时避免模型二次调工具）。
        - 硅基流动 Qwen3 默认带 ``<think>`` 思考链，显式关闭以返回干净正文。
        """
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": stream,
        }
        if use_tools:
            body["tools"] = self._openai_tools()
            body["tool_choice"] = "auto"
        else:
            body["tool_choice"] = "none"
        if self.provider == "siliconflow":
            body["chat_template_kwargs"] = {"enable_thinking": False}
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        remaining = max(1.0, deadline - time.time())
        resp = urllib.request.urlopen(req, timeout=remaining)  # noqa: S310
        if stream:
            return resp
        try:
            return json.loads(resp.read().decode("utf-8"))
        finally:
            resp.close()

    # ------------------------------------------------------------------ 执行工具
    def run_tool(self, name: str, args: Dict[str, Any]) -> Tuple[bool, Any]:
        impl = self.impls.get(name)
        if impl is None:
            return False, f"未知工具: {name}"
        try:
            return True, impl(**args)
        except Exception as exc:  # noqa: BLE001
            logger.warning("工具 %s 执行失败: %s", name, exc)
            return False, str(exc)


def get_agent() -> RiskAgent:
    """宝典 11.3①：**第一次调用才创建**，避免 import 时建 LLM 连接。"""
    global _AGENT                                    # noqa: PLW0603
    if _AGENT is None:
        with _AGENT_LOCK:
            if _AGENT is None:
                _AGENT = RiskAgent()
    return _AGENT


def is_agent_loaded() -> bool:
    return _AGENT is not None


def agent_status() -> Dict[str, Any]:
    """不触发创建的状态查询（给 /api/agent/tools 用）。"""
    status: Dict[str, Any] = {
        "enabled": settings.AI_AGENT_ENABLED,
        "loaded": _AGENT is not None,
        "lazy_load": "未加载（第一次对话时才创建，宝典 11.3①）" if _AGENT is None else "已加载",
        "mode": "llm" if settings.LLM_API_KEY.strip() else "local",
        "model": settings.LLM_MODEL,
        "temperature": settings.LLM_TEMPERATURE,
        "timeout_sec": settings.AI_AGENT_CHAT_TIMEOUT_SEC,
        "api_key_configured": bool(settings.LLM_API_KEY.strip()),
        "langchain_installed": tool_module._HAS_LANGCHAIN,    # noqa: SLF001
        "system_prompt": SYSTEM_PROMPT,
        "sessions": session_stats(),
        "error": _AGENT_ERROR,
    }
    if _AGENT is not None:
        status["agent"] = _AGENT.info()
    return status


# ====================================================================== 本地意图路由（无 Key 模式）
_INTENTS: List[Tuple[str, str]] = [
    (r"(风控检查|检查一下|跑一次|评估一下|风险检查)", "risk_check"),
    (r"(案件|工单|待审核|审核中|工作台)", "query_cases"),
    (r"(画像|用户档案|这个用户|用户.?U\d+|风险档案)", "query_user_profile"),
    (r"(黑名单|拉黑|解除|失信)", "manage_blacklist"),
    (r"(趋势|最近.*天|走势|上升|下降)", "analyze_risk_trend"),
    (r"(规则.*命中|命中率|僵尸规则|规则效果|规则有效)", "analyze_rule_effectiveness"),
    (r"(订单|售后|地址|退款|投诉|登录记录|业务数据)", "query_business_data"),
    (r"(大盘|统计|总览|概况|多少|分布|仪表盘)", "query_dashboard_stats"),
]

_DATA_TYPE_WORDS = {"订单": "订单", "售后": "售后", "地址": "地址",
                    "退款": "退款", "投诉": "投诉", "登录": "登录"}


def _detect_intent(message: str) -> str:
    for pattern, name in _INTENTS:
        if re.search(pattern, message):
            return name
    return "query_dashboard_stats"


def _extract_args(name: str, message: str) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    # 用户 ID：兼容两种写法——教学示例里的 "U0001"，以及库中真实的纯数字 "1001"
    user = re.search(r"((?:U\d{2,})|\b\d{4}\b)", message, re.IGNORECASE)
    # 订单 / 来源单号：库里是 "ORD10010001"，示例里是 "O20260101001"
    order = re.search(r"((?:ORD[A-Za-z0-9]+)|O\d{6,})", message, re.IGNORECASE)
    days = re.search(r"(\d+)\s*天", message)
    number = re.search(r"前\s*(\d+)", message)

    if name == "risk_check":
        args["event_type"] = next((t for t in ("考试", "作业", "选课", "成绩申诉")
                                   if t in message), "考试")
        args["user_id"] = user.group(1).upper() if user else ""
        args["source_id"] = order.group(1).upper() if order else ""
    elif name == "query_cases":
        for status in ("待审核", "审核中", "已通过", "已拒绝", "已关闭"):
            if status in message:
                args["case_status"] = status
                break
        if user:
            args["user_id"] = user.group(1).upper()
    elif name == "query_user_profile":
        args["user_id"] = user.group(1).upper() if user else ""
    elif name == "manage_blacklist":
        if any(w in message for w in ("拉黑", "加入黑名单", "新增")):
            args["action"] = "add"
            args["blacklist_type"] = next(
                (t for t in ("用户", "手机号", "地址", "设备", "IP") if t in message), "用户")
            args["value"] = user.group(1).upper() if user else ""
            args["reason"] = "AI 助手根据风控结论建议拉黑"
        elif any(w in message for w in ("解除", "移出", "删除")):
            args["action"] = "remove"
            args["value"] = user.group(1).upper() if user else ""
        elif any(w in message for w in ("是否", "命中", "查一下", "在不在")):
            args["action"] = "check"
            args["value"] = user.group(1).upper() if user else ""
        else:
            args["action"] = "list"
    elif name == "analyze_risk_trend":
        args["days"] = int(days.group(1)) if days else 7
    elif name == "analyze_rule_effectiveness":
        args["top_n"] = int(number.group(1)) if number else 10
    elif name == "query_business_data":
        args["data_type"] = next((v for k, v in _DATA_TYPE_WORDS.items() if k in message), "订单")
        if user:
            args["user_id"] = user.group(1).upper()
    return args


def _summarize(name: str, data: Any) -> str:
    """本地模式的"专业解读" —— 模板化但结论准确。"""
    if not isinstance(data, dict):
        return f"工具 {name} 返回：{data}"

    if name == "risk_check":
        veto = "（触发一票否决）" if data.get("is_veto") else ""
        rules = "、".join(r.get("rule_name") or "" for r in data.get("hit_rules") or []) or "无"
        return (f"风控检查完成。规则分 **{data.get('rule_score')}**，模型分 "
                f"**{data.get('ml_score')}**，融合分 **{data.get('final_score')}**{veto}，"
                f"风险等级 **{data.get('risk_level')}**，决策 **{data.get('decision')}**。\n\n"
                f"- 命中规则：{rules}\n- 评估 ID：`{data.get('assessment_id')}`\n"
                + (f"- 已自动生成案件：`{data.get('case_id')}`\n" if data.get("case_id") else "")
                + f"- 耗时：{data.get('cost_ms')} ms\n\n决策依据：{data.get('reason')}")

    if name == "query_cases":
        summary = data.get("status_summary") or {}
        lines = [f"当前共 **{data.get('total', 0)}** 个符合条件的案件。状态分布："
                 + "、".join(f"{k} {v}" for k, v in summary.items() if v)]
        for item in (data.get("items") or [])[:10]:
            lines.append(f"- `{item.get('case_id')}` {item.get('user_id')} / "
                         f"{item.get('event_type')} / {item.get('case_status')} / "
                         f"分数 {item.get('final_score')} / {item.get('risk_level')}")
        return "\n".join(lines)

    if name == "query_user_profile":
        profile = data.get("profile") or {}
        user = data.get("user") or {}
        black = data.get("blacklist_hits") or []
        return (f"用户 **{user.get('user_name') or user.get('user_id')}**"
                f"（{user.get('user_id')}，等级 {user.get('user_level') or '-'}）画像：\n\n"
                f"- 累计风控事件：{profile.get('total_events', 0)}，高危事件 "
                f"{profile.get('risk_event_count', 0)}\n"
                f"- 决策分布：通过 {profile.get('pass_count', 0)} / 标记 "
                f"{profile.get('mark_count', 0)} / 人工审核 {profile.get('review_count', 0)} / "
                f"拒绝 {profile.get('reject_count', 0)}\n"
                f"- 历史最高分 {profile.get('max_final_score', 0)}，平均 "
                f"{profile.get('avg_final_score', 0)}，画像等级 "
                f"**{profile.get('profile_level', '低')}**\n"
                f"- 关联案件 {data.get('case_count', 0)} 个"
                + (f"\n- ⚠️ 命中黑名单 {len(black)} 条" if black else "\n- 未命中黑名单"))

    if name == "manage_blacklist":
        action = data.get("action")
        if action == "list":
            lines = [f"黑名单共 **{data.get('total', 0)}** 条（最多展示 30 条）："]
            for item in (data.get("items") or [])[:10]:
                lines.append(f"- {item.get('blacklist_type')} `{item.get('blacklist_value')}`"
                             f"（{item.get('risk_level')}）— {item.get('reason')}")
            return "\n".join(lines)
        if action == "check":
            return (f"`{data.get('value')}` "
                    + ("**命中**黑名单，将触发一票否决。" if data.get("hit") else "未命中黑名单。"))
        if action == "add":
            return ("已加入黑名单，ID = " + str(data.get("blacklist_id"))
                    if data.get("created") else str(data.get("message")))
        if action == "remove":
            return f"已解除 {data.get('removed', 0)} 条黑名单记录。"

    if name == "query_dashboard_stats":
        dec = data.get("decision_histogram") or {}
        cases = (data.get("case_stats") or {}).get("summary") or {}
        return (f"风控大盘概况：累计评估 **{data.get('total_assessments', 0)}** 次，平均融合分 "
                f"**{data.get('avg_final_score', 0)}**，一票否决 "
                f"{data.get('veto_count', 0)} 次。\n\n"
                f"- 决策分布：" + "、".join(f"{k} {v}" for k, v in dec.items()) + "\n"
                f"- 案件状态：" + "、".join(f"{k} {v}" for k, v in cases.items() if v) + "\n"
                f"- 启用规则 {data.get('rules_enabled', 0)} 条，生效黑名单 "
                f"{data.get('blacklist_total', 0)} 条\n"
                f"- XGBoost 模型：{'已加载' if data.get('model_loaded') else '未加载（降级纯规则）'}")

    if name == "analyze_risk_trend":
        return (f"最近 {data.get('days')} 天共评估 **{data.get('total', 0)}** 次，拒绝 "
                f"{data.get('reject', 0)} 次（拒绝率 {data.get('reject_rate', 0)}%），"
                f"整体判断：**{data.get('trend')}**。")

    if name == "analyze_rule_effectiveness":
        top = data.get("top_rules") or []
        lines = [f"规则共 {data.get('total_rules', 0)} 条，累计命中 {data.get('total_hits', 0)} 次，"
                 f"整体命中率 {data.get('overall_hit_rate', 0)}%。"]
        if top:
            lines.append("命中 TOP：")
            for row in top[:8]:
                lines.append(f"- `{row.get('rule_id')}` {row.get('rule_name')}："
                             f"{row.get('hit_count')} 次（占比 {row.get('hit_share')}%）")
        if data.get("zombie_count"):
            lines.append(f"⚠️ 有 {data['zombie_count']} 条启用但从未命中的僵尸规则："
                         + "、".join(data.get("zombie_rules") or [])[:200])
        return "\n".join(lines)

    if name == "query_business_data":
        lines = [f"{data.get('data_type')}数据（表 `{data.get('table')}`）共 "
                 f"{data.get('total', 0)} 条，最近 {len(data.get('items') or [])} 条："]
        for item in (data.get("items") or [])[:8]:
            lines.append("- " + "，".join(f"{k}={v}" for k, v in list(item.items())[:6]))
        return "\n".join(lines)

    return json.dumps(data, ensure_ascii=False, default=str)[:1500]


# ====================================================================== 主入口
def chat_stream(session_id: str, message: str,
                operator: str = "运营") -> Iterator[Tuple[str, Any]]:
    """产出 SSE 事件流：`start` → `tool_call` → `tool_result` → `delta`* → `done`。

    ④ 超时保护：整轮对话共享一个 deadline（AI_AGENT_CHAT_TIMEOUT_SEC）。
    """
    if not settings.AI_AGENT_ENABLED:
        yield "error", {"message": "AI 助手已在配置中关闭（AI_AGENT_ENABLED=false）"}
        return
    message = (message or "").strip()
    if not message:
        yield "error", {"message": "消息内容不能为空"}
        return

    started = time.time()
    deadline = started + settings.AI_AGENT_CHAT_TIMEOUT_SEC
    agent = get_agent()                              # ① 懒加载：此刻才真正创建
    lock = _session_lock(session_id)                 # ③ 同 session 串行

    if not lock.acquire(timeout=max(1.0, settings.AI_AGENT_CHAT_TIMEOUT_SEC / 2)):
        yield "error", {"message": "该会话正在处理上一条消息，请稍候"}
        return

    try:
        _append_history(session_id, "user", message)
        yield "start", {"session_id": session_id, "mode": agent.mode,
                        "model": agent.info()["model"], "temperature": agent.temperature,
                        "timeout_sec": agent.timeout, "tools": len(agent.tools)}

        if agent.mode == "llm":
            yield from _stream_llm(agent, session_id, message, deadline)
        else:
            yield from _stream_local(agent, session_id, message, deadline)
    except Exception as exc:  # noqa: BLE001
        logger.exception("AI 对话失败")
        yield "error", {"message": f"AI 对话失败: {exc}"}
    finally:
        lock.release()


def _stream_local(agent: RiskAgent, session_id: str, message: str,
                  deadline: float) -> Iterator[Tuple[str, Any]]:
    """无 Key 模式：意图路由 → 执行工具 → 模板解读。"""
    name = _detect_intent(message)
    args = _extract_args(name, message)
    yield "thinking", {"text": f"识别意图 → 工具 `{name}`（本地意图路由模式）"}

    # 必填参数缺失 → 主动追问（宝典 11.4「数据不足时主动补充询问」）
    missing = [p for p, meta in (next(
        (s for s in agent.specs if s["name"] == name), {"args": {}})["args"] or {}).items()
        if meta.get("required") and not args.get(p)]
    if missing:
        reply = (f"要执行 **{name}** 还缺少参数：{'、'.join(missing)}。\n\n"
                 f"例如可以说：\n- 「给用户 1001 的考试记录 ORD10010001 做一次考试风控检查」\n"
                 f"- 「查一下 1001 的用户画像」\n- 「最近 7 天风险趋势怎么样」")
        _append_history(session_id, "assistant", reply)
        for chunk in _chunks(reply):
            yield "delta", {"text": chunk}
        yield "done", {"tool_calls": [], "cost_ms": int((time.time() - deadline
                                                        + settings.AI_AGENT_CHAT_TIMEOUT_SEC) * 1000)}
        return

    yield "tool_call", {"name": name, "args": args}
    ok, result = agent.run_tool(name, args)
    yield "tool_result", {"name": name, "success": ok,
                          "result": result if ok else {"error": result}}

    reply = _summarize(name, result) if ok else f"工具 `{name}` 执行失败：{result}"
    _append_history(session_id, "assistant", reply)
    for chunk in _chunks(reply):
        if time.time() > deadline:
            yield "error", {"message": "响应超时"}
            return
        yield "delta", {"text": chunk}
    yield "done", {"tool_calls": [name], "mode": "local"}


def _stream_llm(agent: RiskAgent, session_id: str, message: str,
                deadline: float) -> Iterator[Tuple[str, Any]]:
    """有 Key 模式：OpenAI 兼容 function calling 多轮循环 + **真实流式输出**。

    流程：
      1. 先发 ``thinking`` 事件，让用户看到"正在调用大模型"；
      2. 决策轮（非流式）检测 ``tool_calls``：
         - 命中工具 → 执行本地 8 工具 → **流式合成**最终自然语言回答；
         - 未命中 → 模型直接给出回答（已是真实大模型内容），本地切片模拟打字。
    全程受 ``deadline`` 超时约束；网络/密钥异常时产出 ``error`` 事件而非 500。
    """
    label = _PROVIDER_LABEL.get(agent.provider, agent.provider)
    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in get_history(session_id)[-settings.AI_AGENT_MAX_HISTORY:]:
        if item["role"] in ("user", "assistant"):
            messages.append({"role": item["role"], "content": item["content"]})

    called: List[str] = []
    yield "thinking", {"text": "正在思考…"}

    for turn in range(5):
        if time.time() > deadline:
            yield "error", {"message": f"LLM 响应超过 {agent.timeout}s，已中断"}
            return
        try:
            payload = agent._call_llm(messages, deadline, stream=False, use_tools=True)  # noqa: SLF001
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:400]
            yield "error", {"message": f"LLM 接口报错 {exc.code}: {detail}"}
            return
        except Exception as exc:  # noqa: BLE001
            yield "error", {"message": f"LLM 调用失败（请检查网络 / API Key / 额度）: {exc}"}
            return

        choice = (payload.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        tool_calls = msg.get("tool_calls") or []

        if tool_calls:
            messages.append({"role": "assistant", "content": msg.get("content") or "",
                             "tool_calls": tool_calls})
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name") or ""
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield "tool_call", {"name": name, "args": args, "turn": turn + 1}
                ok, result = agent.run_tool(name, args)
                called.append(name)
                yield "tool_result", {"name": name, "success": ok,
                                      "result": result if ok else {"error": result}}
                messages.append({"role": "tool", "tool_call_id": call.get("id"),
                                 "name": name,
                                 "content": json.dumps({"success": ok, "data": result},
                                                       ensure_ascii=False, default=str)[:6000]})
            # 工具已执行完 → 让模型基于结果流式合成最终回答（不再调工具）
            parts: List[str] = []
            for evt, data in _stream_tokens(agent, messages, deadline, use_tools=False):
                if evt == "delta":
                    parts.append(data["text"])
                yield evt, data
            full = _strip_think("".join(parts))
            _append_history(session_id, "assistant", full)
            usage = payload.get("usage") or {}
            yield "done", {"tool_calls": called, "mode": "llm", "turns": turn + 1, "usage": usage}
            return

        # 无工具调用 → 模型直接给出最终回答（已是真实大模型内容）
        full = (msg.get("content") or "").strip() or "（模型未返回内容）"
        full = _strip_think(full)
        _append_history(session_id, "assistant", full)
        for chunk in _chunks(full):
            if time.time() > deadline:
                yield "error", {"message": "响应超时"}
                return
            yield "delta", {"text": chunk}
        usage = payload.get("usage") or {}
        yield "done", {"tool_calls": called, "mode": "llm", "turns": turn + 1, "usage": usage}
        return

    yield "error", {"message": "工具调用轮数超过上限（5 轮），已中断"}


def _chunks(text: str, size: int = 28) -> Iterable[str]:
    """把回答切片，模拟打字机效果（前端 SSE 逐块渲染）。"""
    for i in range(0, len(text), size):
        yield text[i:i + size]


# Qwen 系列可能返回的推理链，干净展示给前端前剥离
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(text: str) -> str:
    """去掉 ``<think>...</think>`` 思考链（即使关闭了思考，做兜底）。"""
    return _THINK_RE.sub("", text or "").strip()


def _stream_tokens(agent: RiskAgent, messages: List[Dict[str, Any]], deadline: float,
                   use_tools: bool = False) -> Iterator[Tuple[str, Any]]:
    """向大模型发流式请求，逐 token 产出 ``("delta", {"text": ...})`` 事件。

    失败自动降级为非流式（仍产出 delta，保证前端不断流）。
    """
    try:
        resp = agent._call_llm(messages, deadline, stream=True, use_tools=use_tools)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        logger.warning("流式请求失败，降级为非流式: %s", exc)
        try:
            payload = agent._call_llm(messages, deadline, stream=False, use_tools=use_tools)  # noqa: SLF001
            full = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            for chunk in _chunks(_strip_think(full)):
                yield "delta", {"text": chunk}
            return
        except Exception as exc2:  # noqa: BLE001
            yield "delta", {"text": f"⚠️ 模型响应失败：{exc2}"}
            return

    buf = b""
    try:
        for raw in resp:
            buf += raw
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    obj = json.loads(data)
                except Exception:  # noqa: BLE001
                    continue
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                text = delta.get("content") or ""
                if text:
                    yield "delta", {"text": text}
    finally:
        try:
            resp.close()
        except Exception:  # noqa: BLE001
            pass


def chat_once(session_id: str, message: str, operator: str = "运营") -> Dict[str, Any]:
    """非流式版本（给不支持 SSE 的调用方 / 单测用）。"""
    reply_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    tool_results: List[Dict[str, Any]] = []
    error = ""
    meta: Dict[str, Any] = {}
    started = time.time()
    for event, data in chat_stream(session_id, message, operator):
        if event == "delta":
            reply_parts.append(data.get("text", ""))
        elif event == "tool_call":
            tool_calls.append(data)
        elif event == "tool_result":
            tool_results.append(data)
        elif event == "error":
            error = data.get("message", "未知错误")
        elif event in ("start", "done"):
            meta |= data
    return {"success": not error, "session_id": session_id,
            "reply": "".join(reply_parts), "error": error,
            "tool_calls": tool_calls, "tool_results": tool_results,
            "cost_ms": int((time.time() - started) * 1000), "meta": meta}
