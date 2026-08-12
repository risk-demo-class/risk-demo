# -*- coding: utf-8 -*-
"""L1 路由 · agent_router —— AI 风控助手

对应教学宝典第 11 章：
    `User -->|HTTP /api/agent/chat| Router --> chat.chat --> get_agent 懒加载
     --> DeepAgent --(ChatOpenAI temp=0.1)--> Qwen-Plus --(tool call)--> 8 个 @tool`
    `DeepAgent -.SSE.-> User`

端点（2 个）：
    POST   /api/agent/chat     对话（`Accept: text/event-stream` → SSE 流式；否则 JSON）
    GET    /api/agent/tools    8 个工具清单 + Agent 状态（不触发懒加载）
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.agent import chat as chat_service
from app.agent import tools as tool_module
from app.framework import HTTPError, Request, Router, SSEResponse

logger = logging.getLogger("ai_risk.routers.agent")

router = Router(prefix="/api/agent", tags=["AI 助手"], name="agent_router")


# ====================================================================== 1
@router.post("/chat", "AI 对话（SSE 流式 / JSON 双模）")
def chat(request: Request) -> Any:
    payload = request.json()
    message = str(payload.get("message") or "").strip()
    session_id = str(payload.get("session_id") or "default").strip() or "default"
    operator = str(payload.get("operator") or "运营")

    # reset=true：清空该会话历史（内存级会话，宝典 11.3③）
    if payload.get("reset"):
        existed = chat_service.reset_session(session_id)
        if not message:
            return {"success": True, "reset": True, "existed": existed,
                    "message": f"会话 {session_id} 已清空"}

    if not message:
        raise HTTPError(400, "message 不能为空")

    stream = bool(payload.get("stream", True)) and request.wants_sse()
    if stream:
        logger.info("AI 对话（SSE） session=%s: %s", session_id, message[:60])
        return SSEResponse(chat_service.chat_stream(session_id, message, operator))

    logger.info("AI 对话（JSON） session=%s: %s", session_id, message[:60])
    result = chat_service.chat_once(session_id, message, operator)
    return result


# ====================================================================== 2
@router.get("/tools", "8 个 @tool 清单 + Agent 状态")
def list_tools(request: Request) -> Dict[str, Any]:
    session_id = request.q("session_id", "") or ""
    data: Dict[str, Any] = {
        "success": True,
        "tools": tool_module.tool_specs(),
        "tool_count": len(tool_module.ALL_TOOLS),
        "catalog": tool_module.TOOL_CATALOG,
        "agent": chat_service.agent_status(),
        "design_principles": [
            {"index": 1, "name": "懒加载 Agent",
             "detail": "_AGENT = None 全局，第一次 get_agent() 才创建，避免 import 时建 LLM 连接"},
            {"index": 2, "name": "温度 0.1",
             "detail": "业务场景要稳定，接近确定但保留一点灵活"},
            {"index": 3, "name": "内存级会话 + Lock",
             "detail": "_SESSIONS 存历史，同 session 串行；重启丢失，生产要换 Redis"},
            {"index": 4, "name": "超时 60s",
             "detail": "AI_AGENT_CHAT_TIMEOUT_SEC=60，防 LLM 卡死拖垮服务"},
        ],
        "examples": [
            "给用户 1001 的考试记录 ORD10010001 做一次考试风控检查",
            "查一下 1001 的用户画像",
            "现在有多少待审核案件",
            "最近 7 天风险趋势怎么样",
            "规则命中率分析，看看有没有僵尸规则",
            "把 1001 加入黑名单，原因是代考团伙",
            "查一下 1001 最近的学习记录",
            "风控大盘概况",
        ],
    }
    if session_id:
        data["history"] = chat_service.get_history(session_id)
    return data
