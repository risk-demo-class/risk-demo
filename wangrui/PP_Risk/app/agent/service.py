from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from contextvars import ContextVar
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from sqlalchemy import desc, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models_business import ConversationSegment, Interaction, PaymentTransaction, TransactionParty, UserInfo
from app.models_risk import RiskActionLog, RiskAssessment, RiskCase, RiskEvent, RiskUserProfile


_user: ContextVar[str] = ContextVar("agent_user")
_session: ContextVar[str] = ContextVar("agent_session")
_sessions: dict[str, tuple[str, list[Any], float]] = {}
_confirmations: dict[str, dict[str, Any]] = {}
_lock = asyncio.Lock()
_agent: Any = None


def _safe(value: Any) -> Any:
    if hasattr(value, "isoformat"): return value.isoformat()
    return float(value) if value.__class__.__name__ == "Decimal" else value


def _row(row: Any) -> dict[str, Any]:
    return {column.name: _safe(getattr(row, column.name)) for column in row.__table__.columns}


@tool
async def get_my_profile() -> str:
    """Get the current customer's basic profile and public risk summary."""
    user_id = _user.get()
    async with AsyncSessionLocal() as db:
        user = await db.get(UserInfo, user_id)
        risk = await db.get(RiskUserProfile, user_id)
        if not user: return "Current customer does not exist."
        return json.dumps({"user": _row(user), "risk_summary": _row(risk) if risk else None}, ensure_ascii=False)


@tool
async def list_my_transactions(limit: int = 10) -> str:
    """List recent transactions belonging to the current customer. Limit must be 1-20."""
    user_id = _user.get(); limit = max(1, min(limit, 20))
    async with AsyncSessionLocal() as db:
        ids = select(TransactionParty.transaction_id).where(TransactionParty.party_type == "USER", TransactionParty.party_reference == user_id)
        rows = (await db.execute(select(PaymentTransaction).where(PaymentTransaction.transaction_id.in_(ids)).order_by(desc(PaymentTransaction.create_time)).limit(limit))).scalars()
        return json.dumps([_row(row) for row in rows], ensure_ascii=False)


@tool
async def get_transaction_detail(transaction_id: str) -> str:
    """Get one transaction only when the current customer is a party to it."""
    user_id = _user.get()
    async with AsyncSessionLocal() as db:
        owned = (await db.execute(select(TransactionParty.party_id).where(TransactionParty.transaction_id == transaction_id, TransactionParty.party_type == "USER", TransactionParty.party_reference == user_id).limit(1))).scalar_one_or_none()
        if not owned: return "Transaction not found or not owned by current customer."
        transaction = await db.get(PaymentTransaction, transaction_id)
        return json.dumps(_row(transaction), ensure_ascii=False)


@tool
async def get_my_cases() -> str:
    """List manual-review cases belonging to the current customer."""
    user_id = _user.get()
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(RiskCase).where(RiskCase.user_id == user_id).order_by(desc(RiskCase.create_time)).limit(20))).scalars()
        return json.dumps([{"case_id": row.case_id, "status": row.case_status, "category": row.case_category, "created": _safe(row.create_time)} for row in rows], ensure_ascii=False)


@tool
async def list_my_support_history() -> str:
    """List the current customer's support interactions and conversation counts."""
    user_id = _user.get()
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Interaction).where(Interaction.customer_id == user_id).order_by(desc(Interaction.last_contact_time)).limit(20))).scalars()
        result = []
        for row in rows:
            segments = list((await db.execute(select(ConversationSegment.segment_id).where(ConversationSegment.interaction_id == row.interaction_id))).scalars())
            result.append({"interaction_id": row.interaction_id, "status": row.interaction_status, "last_contact": _safe(row.last_contact_time), "segment_count": len(segments)})
        return json.dumps(result, ensure_ascii=False)


def _confirmation(tool_name: str, target_id: str, reason: str) -> str:
    token = secrets.token_urlsafe(24)
    _confirmations[token] = {"session_id": _session.get(), "user_id": _user.get(), "tool": tool_name, "target_id": target_id, "reason": reason, "expires": time.time() + 300}
    return json.dumps({"confirmation_required": True, "confirmation_token": token, "target_id": target_id, "reason": reason, "expires_in_seconds": 300}, ensure_ascii=False)


@tool
async def submit_transaction_review(transaction_id: str, reason: str) -> str:
    """Prepare, but do not execute, a manual review for the current customer's transaction."""
    user_id = _user.get()
    async with AsyncSessionLocal() as db:
        owned = (await db.execute(select(TransactionParty.party_id).where(TransactionParty.transaction_id == transaction_id, TransactionParty.party_type == "USER", TransactionParty.party_reference == user_id).limit(1))).scalar_one_or_none()
    return _confirmation("transaction", transaction_id, reason) if owned else "Transaction not found or not owned by current customer."


@tool
async def submit_support_review(interaction_id: str, reason: str) -> str:
    """Prepare, but do not execute, a manual review for the current customer's support interaction."""
    user_id = _user.get()
    async with AsyncSessionLocal() as db:
        owned = (await db.execute(select(Interaction.interaction_id).where(Interaction.interaction_id == interaction_id, Interaction.customer_id == user_id).limit(1))).scalar_one_or_none()
    return _confirmation("support", interaction_id, reason) if owned else "Support interaction not found or not owned by current customer."


TOOLS = [get_my_profile, list_my_transactions, get_transaction_detail, get_my_cases, list_my_support_history, submit_transaction_review, submit_support_review]
SYSTEM_PROMPT = """You are PP Risk customer support for global payments. Answer in Chinese. Use tools for factual account data. You may only access the current customer's data. Never approve cases, modify balances, or manage blacklists. Write tools only prepare a confirmation; clearly ask the customer to click confirm when a confirmation token is returned. Do not reveal internal rule conditions or private data of other users."""


def enabled() -> bool:
    return settings.LLM_ENABLED and bool(settings.LLM_API_KEY)


def get_agent() -> Any:
    global _agent
    if _agent is None:
        llm = ChatOpenAI(model=settings.LLM_MODEL_NAME, api_key=settings.LLM_API_KEY, base_url=settings.LLM_BASE_URL, temperature=settings.LLM_TEMPERATURE, timeout=settings.LLM_TIMEOUT_SECONDS, max_retries=1)
        _agent = create_agent(model=llm, tools=TOOLS, system_prompt=SYSTEM_PROMPT)
    return _agent


async def chat(message: str, user_id: str, session_id: str | None) -> tuple[str, str, str | None]:
    if not enabled(): raise RuntimeError("LLM Agent is not configured")
    session_id = session_id or f"sess_{uuid.uuid4().hex}"
    async with _lock:
        existing = _sessions.get(session_id)
        if existing and existing[0] != user_id: raise PermissionError("session belongs to another user")
        history = list(existing[1]) if existing and existing[2] > time.time() else []
    user_token, session_token = _user.set(user_id), _session.set(session_id)
    try:
        result = await get_agent().ainvoke({"messages": [*history, HumanMessage(content=message)]}, {"recursion_limit": settings.LLM_MAX_TOOL_ROUNDS * 2 + 4})
        messages = result["messages"]
        reply = messages[-1].content if messages else "未能生成回复"
        async with _lock: _sessions[session_id] = (user_id, messages, time.time() + settings.AGENT_SESSION_TTL_MINUTES * 60)
        confirmation_token = None
        for item in reversed(messages):
            content = getattr(item, "content", "")
            if isinstance(content, str) and "confirmation_token" in content:
                try:
                    parsed = json.loads(content)
                    confirmation_token = parsed.get("confirmation_token")
                    if confirmation_token: break
                except (json.JSONDecodeError, AttributeError):
                    continue
        return str(reply), session_id, confirmation_token
    finally:
        _user.reset(user_token); _session.reset(session_token)


async def confirm(token: str, user_id: str, session_id: str) -> dict[str, Any]:
    data = _confirmations.pop(token, None)
    if not data or data["expires"] < time.time(): raise ValueError("confirmation token is invalid or expired")
    if data["user_id"] != user_id or data["session_id"] != session_id: raise PermissionError("confirmation token ownership mismatch")
    source_id, event_type = data["target_id"], "支付" if data["tool"] == "transaction" else "客服交互"
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(RiskCase).where(RiskCase.source_id == source_id, RiskCase.case_status.in_(("待审核", "审核中"))).limit(1))).scalar_one_or_none()
        if existing: return {"case_id": existing.case_id, "created": False}
        event_id, assessment_id, case_id = f"EVT-{uuid.uuid4().hex}", f"ASM-{uuid.uuid4().hex}", f"CASE-{uuid.uuid4().hex}"
        detail = json.dumps({"reason": data["reason"], "agent_session": session_id}, ensure_ascii=False)
        db.add(RiskEvent(event_id=event_id, event_type=event_type, event_source_id=source_id, user_id=user_id, event_data=detail))
        db.add(RiskAssessment(assessment_id=assessment_id, event_id=event_id, user_id=user_id, rule_results="[]", final_score=70, risk_level="高", decision="人工审核"))
        db.add(RiskCase(case_id=case_id, assessment_id=assessment_id, user_id=user_id, case_status="待审核", case_category="CUSTOMER_REQUEST", risk_detail=detail, source_id=source_id, event_type=event_type))
        db.add(RiskActionLog(operator=f"customer:{user_id}", action_type="AGENT_CONFIRMED_REVIEW", target_type=event_type, target_id=source_id, detail=detail))
        await db.commit(); return {"case_id": case_id, "created": True}


async def clear(session_id: str, user_id: str) -> bool:
    async with _lock:
        existing = _sessions.get(session_id)
        if existing and existing[0] == user_id: del _sessions[session_id]; return True
    return False
