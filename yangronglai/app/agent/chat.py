"""Local tool assistant with optional OpenAI-compatible LLM tool calling."""

from __future__ import annotations

import asyncio
import json
import re
from uuid import uuid4

import httpx

from app.agent.tools import TOOL_MANIFEST, execute_tool, openai_tool_definitions
from app.config import settings


SYSTEM_PROMPT = """你是银行风控分析助手。只根据工具返回的数据回答，不编造客户信息、分数或规则。
查询工具可直接调用；submit_review_request 必须获得人工 approval_token。用中文给出简洁结论和证据。"""


class AgentService:
    def __init__(self) -> None:
        self._sessions: dict[str, list[dict]] = {}
        self._lock = asyncio.Lock()

    def capabilities(self) -> dict:
        llm_ready = bool(settings.LLM_API_KEY)
        return {
            "enabled": settings.ENABLE_AGENT,
            "mode": settings.AGENT_MODE,
            "ready": settings.ENABLE_AGENT and (settings.AGENT_MODE == "local" or llm_ready),
            "model": settings.LLM_MODEL_NAME if settings.AGENT_MODE == "llm" else "local-tool-router",
            "llm_configured": llm_ready,
            "tools": TOOL_MANIFEST,
        }

    async def chat(self, message: str, session_id: str | None = None) -> tuple[str, str, list[str]]:
        session_id = session_id or f"sess_{uuid4().hex}"
        if not settings.ENABLE_AGENT:
            return "Agent 当前被配置关闭。", session_id, []
        if settings.AGENT_MODE == "llm":
            return await self._llm_chat(message, session_id)
        return await self._local_chat(message, session_id)

    async def _local_chat(self, message: str, session_id: str) -> tuple[str, str, list[str]]:
        tool_name: str | None = None
        arguments: dict = {}
        upper = message.upper()
        assessment_match = re.search(r"ASM_[A-Z0-9]+", upper)
        user_match = re.search(r"U_[A-Z0-9_]+", upper)
        if assessment_match:
            tool_name = "explain_decision"
            arguments = {"assessment_id": assessment_match.group(0)}
        elif "规则" in message and any(word in message for word in ("效果", "命中", "分析")):
            tool_name = "analyze_rule_effectiveness"
        elif any(word in message for word in ("仪表盘", "统计", "概览")):
            tool_name = "query_dashboard_stats"
        elif "案件" in message:
            tool_name = "query_cases"
        elif "图谱" in message and user_match:
            tool_name = "query_graph_relations"
            arguments = {"user_id": user_match.group(0)}
        elif user_match:
            tool_name = "query_customer_360"
            arguments = {"user_id": user_match.group(0)}

        used_tools: list[str] = []
        if tool_name:
            result = await execute_tool(tool_name, arguments)
            used_tools.append(tool_name)
            reply = f"已调用 {tool_name}：\n" + json.dumps(result, ensure_ascii=False, indent=2)
        else:
            reply = (
                "本地工具助手可处理：仪表盘统计、案件查询、规则效果、客户360、关系图谱和评估解释。"
                "请在问题中提供用户ID（如 U_R001）或评估ID（ASM_...）；实时风险检查也可在工具面板直接调用。"
            )
        async with self._lock:
            self._sessions.setdefault(session_id, []).extend(
                [{"role": "user", "content": message}, {"role": "assistant", "content": reply}]
            )
        return reply, session_id, used_tools

    async def _llm_chat(self, message: str, session_id: str) -> tuple[str, str, list[str]]:
        if not settings.LLM_API_KEY:
            return "AGENT_MODE=llm，但尚未配置 LLM_API_KEY。", session_id, []
        async with self._lock:
            history = list(self._sessions.get(session_id, []))
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history, {"role": "user", "content": message}]
        endpoint = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
        payload = {"model": settings.LLM_MODEL_NAME, "messages": messages, "tools": openai_tool_definitions(), "temperature": 0.1}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            assistant_message = response.json()["choices"][0]["message"]
            used_tools: list[str] = []
            messages.append(assistant_message)
            for call in assistant_message.get("tool_calls", []):
                name = call["function"]["name"]
                arguments = json.loads(call["function"].get("arguments") or "{}")
                result = await execute_tool(name, arguments)
                used_tools.append(name)
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)})
            if used_tools:
                second = await client.post(endpoint, headers=headers, json={"model": settings.LLM_MODEL_NAME, "messages": messages, "temperature": 0.1})
                second.raise_for_status()
                reply = second.json()["choices"][0]["message"].get("content") or "工具调用完成。"
            else:
                reply = assistant_message.get("content") or "未生成回复。"
        async with self._lock:
            self._sessions[session_id] = [*history, {"role": "user", "content": message}, {"role": "assistant", "content": reply}]
        return reply, session_id, used_tools

    async def clear_session(self, session_id: str) -> bool:
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None


agent_service = AgentService()
