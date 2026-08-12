from __future__ import annotations

import re
import threading
import uuid
from collections import defaultdict
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.blacklist import list_blacklist
from app.services.dashboard import dashboard_stats
from app.services.risk_service import assess_business_id
from models import InboundPayment, Payout, RiskBlacklist, RiskCase, RiskRule


settings = get_settings()
_sessions: dict[str, list[dict[str, str]]] = defaultdict(list)
_session_lock = threading.Lock()


class EvidenceBoundaryError(ValueError):
    pass


def assistant_status() -> dict[str, Any]:
    configured = bool(settings.deepseek_api_key)
    return {
        "mode": "DEEPSEEK" if configured else "LOCAL_ANALYSIS",
        "provider": "DeepSeek" if configured else "Local",
        "model": settings.deepseek_model if configured else "local-risk-analyst",
        "configured": configured,
        "fallback_enabled": True,
        "capabilities": ["风险总览", "入账/出款检查", "规则解释", "案件统计", "黑名单查询"],
    }


def _rule_context(db: Session, message: str) -> str:
    match = re.search(r"PP-R\d{3}", message.upper())
    if match:
        row = db.scalar(select(RiskRule).where(RiskRule.rule_id == match.group(0)))
        if row:
            return (
                f"规则 {row.rule_id} {row.rule_name}：阶段 {row.stage}，场景 {row.category}，"
                f"风险分 {row.risk_score}，动作 {row.action}，一票否决 {row.is_veto}，"
                f"条件 {row.rule_condition}。"
            )
    rows = db.scalars(
        select(RiskRule)
        .where(RiskRule.is_enabled.is_(True))
        .order_by(RiskRule.is_veto.desc(), RiskRule.risk_score.desc())
        .limit(6)
    ).all()
    return "高优先级规则：" + "；".join(
        f"{row.rule_id} {row.rule_name}({row.risk_score}/{row.action})" for row in rows
    )


def _transaction_context(db: Session, message: str) -> str | None:
    inbound_match = re.search(r"IN_\d+", message.upper())
    payout_match = re.search(r"(?:PO|PAYOUT)_\d+", message.upper())
    if inbound_match:
        reference = inbound_match.group(0)
        exists = db.scalar(select(InboundPayment.id).where(InboundPayment.transaction_id == reference))
        if exists is None:
            return f"未找到入账 {reference}。"
        result = assess_business_id(db, "INBOUND", reference, persist=False)
        return (
            f"入账 {reference}：决策 {result['decision']}，最终分 {result['final_score']:.1f}，"
            f"规则分 {result['rule_score']}，模型概率 {result['ml_probability']:.2%}，"
            f"命中规则 {[item['id'] for item in result['rule_hits']] or '无'}，"
            f"黑名单命中 {[item['entity_type'] for item in result['blacklist_hits']] or '无'}。"
        )
    if payout_match:
        reference = payout_match.group(0)
        exists = db.scalar(select(Payout.id).where(Payout.payout_id == reference))
        if exists is None:
            return f"未找到出款 {reference}。"
        result = assess_business_id(db, "PAYOUT", reference, persist=False)
        return (
            f"出款 {reference}：决策 {result['decision']}，最终分 {result['final_score']:.1f}，"
            f"命中规则 {[item['id'] for item in result['rule_hits']] or '无'}，"
            f"黑名单命中 {[item['entity_type'] for item in result['blacklist_hits']] or '无'}。"
        )
    return None


def _collect_context(db: Session, message: str) -> str:
    transaction = _transaction_context(db, message)
    if transaction:
        return transaction
    lowered = message.lower()
    if "规则" in message or "rule" in lowered or re.search(r"PP-R\d{3}", message.upper()):
        return _rule_context(db, message)
    if "黑名单" in message or "blacklist" in lowered:
        active = list_blacklist(db, page=1, page_size=6, status="ACTIVE")
        type_counts = db.execute(
            select(RiskBlacklist.entity_type, func.count())
            .where(RiskBlacklist.is_active.is_(True))
            .group_by(RiskBlacklist.entity_type)
        ).all()
        recent = "；".join(
            f"{item['entity_type']}:{item['entity_value']}({item['reason_code']})"
            for item in active["items"]
        )
        return f"当前有效黑名单 {active['total']} 条。最近记录：{recent or '无'}。主体类型计数：{dict(type_counts)}。"
    if "案件" in message or "case" in lowered:
        total = int(db.scalar(select(func.count()).select_from(RiskCase)) or 0)
        open_count = int(
            db.scalar(select(func.count()).select_from(RiskCase).where(RiskCase.status != "CLOSED")) or 0
        )
        urgent = int(
            db.scalar(
                select(func.count()).select_from(RiskCase).where(
                    RiskCase.status != "CLOSED", RiskCase.priority.in_(["P0", "P1"])
                )
            )
            or 0
        )
        return f"案件总数 {total}，未结 {open_count}，其中 P0/P1 {urgent}。"
    stats = dashboard_stats(db)
    blacklist_total = list_blacklist(db, page=1, page_size=1, status="ACTIVE")["total"]
    return (
        f"入账 {stats['inbound_count']} 笔，总额 USD {float(stats['inbound_amount_usd']):,.2f}，"
        f"拒绝或退款 {stats['high_risk_count']} 笔，高风险率 {stats['high_risk_rate']}%；"
        f"待处理案件 {stats['open_cases']}，有效黑名单 {blacklist_total} 条；"
        f"模型验证 AUC {stats['model'].get('val_auc', 0):.3f}，F1 {stats['model'].get('val_f1', 0):.3f}。"
    )


def _local_reply(message: str, context: str) -> str:
    if any(word in message for word in ["加入黑名单", "删除黑名单", "移除黑名单"]):
        guardrail = "\n\n为避免自然语言误操作，黑名单变更请在「黑名单」页提交结构化表单。"
    else:
        guardrail = ""
    return (
        f"**查询结果**\n\n{context}\n\n"
        "**分析建议**\n\n"
        "- 先确认黑名单和一票否决命中，再解读模型概率。\n"
        "- 人工审核时同时核对付款人、合同买方、贸易单据和资金去向。\n"
        "- 当前数据与标签为合成演示数据，不可作为生产客户结论。"
        f"{guardrail}"
    )


def _aggregate_summary_needs_rewrite(context: str, content: str) -> bool:
    is_aggregate = context.startswith("入账 ") and "模型验证 AUC" in context
    if not is_aggregate:
        return False
    if "合成" not in content:
        return True
    unsupported_patterns = [
        r"(风险|比例|比率|指标|AUC|F1|模型).{0,16}(偏高|偏低|较高|较低|中高|中低|可用区间|相对有限|不足)",
        r"案件.{0,12}积压",
        r"黑名单.{0,16}(覆盖不足|不足)",
    ]
    negation = re.compile(r"不能|无法|不应|不得|未提供|不评价|不推断|不判定|不解读")
    for pattern in unsupported_patterns:
        for match in re.finditer(pattern, content):
            if not negation.search(match.group(0)):
                return True
    return False


def _deepseek_reply(message: str, context: str, history: list[dict[str, str]]) -> str:
    endpoint = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
    system = (
        "你是 PingPong 跨境收款风控总结助手。只能依据提供的本地数据上下文回答，"
        "所有上下文都是合成演示数据，不是真实客户或生产表现。"
        "不得补造生产案件、客户事实、名单命中、监管判定、风险阈值、SLA 或模型目标。"
        "未提供比较基线或阈值时，不得把比率定性为高或低，不得把案件数说成积压，"
        "不得把黑名单数量解读为覆盖不足。建议只能是与已有证据直接相关的核验或分析步骤。"
        "这一限制同样适用于建议部分：除非上下文已给出业务结论，禁止用高、低、较高、较低、"
        "偏高、偏低、严重、良好、不足、积压等评价词修饰指标。"
        "回答使用简洁中文 Markdown，用二级标题按‘结论、关键证据、风险判断、建议动作’组织，不使用 Markdown 表格；"
        "若数据不足，明确说明缺少什么，不要用常识猜测。"
    )
    messages = [{"role": "system", "content": system}]
    messages.extend(history[-6:])
    messages.append(
        {
            "role": "user",
            "content": (
                f"用户问题：{message}\n\n"
                f"本地工具上下文（合成演示数据）：{context}"
            ),
        }
    )
    def request_summary(client: httpx.Client, request_messages: list[dict[str, str]]) -> str:
        response = client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.deepseek_model,
                "messages": request_messages,
                "temperature": 0.1,
                "max_tokens": 1200,
                "thinking": {"type": "disabled"},
                "stream": False,
            },
        )
        response.raise_for_status()
        response_content = response.json()["choices"][0]["message"].get("content")
        if not response_content or not response_content.strip():
            raise ValueError("DeepSeek returned an empty response")
        return response_content.strip()

    with httpx.Client(timeout=settings.deepseek_timeout_seconds) as client:
        content = request_summary(client, messages)
        if _aggregate_summary_needs_rewrite(context, content):
            correction = (
                "重写刚才的回答。第一部分必须明确这是合成演示数据；"
                "删除所有无基线的风险高低、模型优劣、案件积压或名单覆盖评价；"
                "不创造目标值或 SLA，只陈述数据事实与可核验的下一步。"
            )
            content = request_summary(
                client,
                messages
                + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": correction},
                ],
            )
        if _aggregate_summary_needs_rewrite(context, content):
            raise EvidenceBoundaryError("DeepSeek summary failed evidence-boundary validation")
        return content


def chat(db: Session, message: str, session_id: str | None = None) -> dict[str, Any]:
    session_id = session_id or f"sess_{uuid.uuid4().hex[:20]}"
    context = _collect_context(db, message)
    with _session_lock:
        history = list(_sessions.get(session_id, []))
    mode = "LOCAL_ANALYSIS"
    fallback_reason = None
    if settings.deepseek_api_key:
        try:
            reply = _deepseek_reply(message, context, history)
            mode = "DEEPSEEK"
        except Exception as exc:
            fallback_reason = exc.__class__.__name__
            fallback_title = (
                "DeepSeek 回答未通过证据边界校验，已切换为本地分析"
                if isinstance(exc, EvidenceBoundaryError)
                else "DeepSeek 暂时不可用，已切换为本地分析"
            )
            reply = (
                f"**{fallback_title}**\n\n"
                f"{_local_reply(message, context)}"
            )
    else:
        reply = _local_reply(message, context)
    with _session_lock:
        _sessions[session_id] = (history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": reply},
        ])[-8:]
    return {
        "reply": reply,
        "session_id": session_id,
        "mode": mode,
        "provider": "DeepSeek" if mode == "DEEPSEEK" else "Local",
        "model": settings.deepseek_model if mode == "DEEPSEEK" else "local-risk-analyst",
        "fallback_reason": fallback_reason,
    }


def clear_session(session_id: str) -> bool:
    with _session_lock:
        return _sessions.pop(session_id, None) is not None
