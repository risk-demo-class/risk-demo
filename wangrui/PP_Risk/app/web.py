from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models_business import (
    ConversationSegment,
    CashMovement,
    Chargeback,
    CrossBorderTransfer,
    EmailEnvelope,
    FxConversion,
    Interaction,
    LedgerEntry,
    MerchantInfo,
    MerchantPayment,
    Message,
    MessageAttachment,
    PaymentTransaction,
    Refund,
    TransactionParty,
    TransactionStatusHistory,
    UserInfo,
    UserTransfer,
)
from app.models_risk import RiskActionLog, RiskAssessment, RiskBlacklist, RiskCase, RiskEvent, RiskRule


router = APIRouter()
templates = Jinja2Templates(directory=str(Path("templates")))


class ReviewSubmission(BaseModel):
    reason: str = Field(min_length=2, max_length=200)
    note: str = Field(default="", max_length=2000)
    category: str = Field(default="MANUAL_REVIEW", max_length=50)
    priority: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    operator: str = Field(default="risk-operator", min_length=2, max_length=100)


class CaseReviewRequest(BaseModel):
    decision: str = Field(pattern="^(已通过|已拒绝)$")
    reviewer: str = Field(min_length=2, max_length=100)
    review_comment: str = Field(min_length=2, max_length=2000)
    add_to_blacklist: bool = False
    blacklist_reason: str | None = Field(default=None, max_length=1000)
    blacklist_expire_time: datetime | None = None

    @model_validator(mode="after")
    def validate_blacklist_action(self) -> "CaseReviewRequest":
        if self.add_to_blacklist and self.decision != "已拒绝":
            raise ValueError("only rejected cases may add a user to blacklist")
        return self


class BlacklistCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=2, max_length=1000)
    operator: str = Field(default="risk-operator", min_length=2, max_length=100)
    expire_time: datetime | None = None


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value


def _row_dict(row: Any) -> dict[str, Any]:
    return {column.name: _json_value(getattr(row, column.name)) for column in row.__table__.columns}


def _page(request: Request, template: str, *, title: str, active: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={"title": title, "active": active},
    )


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    return _page(request, "dashboard.html", title="全球风险总览", active="dashboard")


@router.get("/transactions", response_class=HTMLResponse)
async def transactions_page(request: Request) -> HTMLResponse:
    return _page(request, "transactions.html", title="跨境交易监控", active="transactions")


@router.get("/cases", response_class=HTMLResponse)
async def cases_page(request: Request) -> HTMLResponse:
    return _page(request, "cases.html", title="人工审核案件", active="cases")


@router.get("/blacklist", response_class=HTMLResponse)
async def blacklist_page(request: Request) -> HTMLResponse:
    return _page(request, "blacklist.html", title="用户黑名单", active="blacklist")


@router.get("/agent", response_class=HTMLResponse)
async def agent_page(request: Request) -> HTMLResponse:
    return _page(request, "agent.html", title="智能客服", active="agent")


@router.get("/risk-check", response_class=HTMLResponse)
async def risk_check_page(request: Request) -> HTMLResponse:
    return _page(request, "risk_check.html", title="实时风险检查", active="risk-check")


@router.get("/interactions", response_class=HTMLResponse)
async def interactions_page(request: Request) -> HTMLResponse:
    return _page(request, "interactions.html", title="客服交互监控", active="interactions")


@router.get("/api/dashboard/overview")
async def dashboard_overview(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    transaction_count = await db.scalar(select(func.count()).select_from(PaymentTransaction)) or 0
    transaction_volume = await db.scalar(select(func.coalesce(func.sum(PaymentTransaction.amount), 0))) or 0
    user_count = await db.scalar(select(func.count()).select_from(UserInfo)) or 0
    merchant_count = await db.scalar(select(func.count()).select_from(MerchantInfo)) or 0
    pending_cases = await db.scalar(
        select(func.count()).select_from(RiskCase).where(RiskCase.case_status == "待审核")
    ) or 0
    high_risk = await db.scalar(
        select(func.count()).select_from(RiskAssessment).where(RiskAssessment.risk_level.in_(("高", "极高")))
    ) or 0
    type_rows = (
        await db.execute(
            select(PaymentTransaction.transaction_type, func.count())
            .group_by(PaymentTransaction.transaction_type)
            .order_by(desc(func.count()))
        )
    ).all()
    recent = (
        await db.execute(select(PaymentTransaction).order_by(desc(PaymentTransaction.create_time)).limit(6))
    ).scalars()
    return {
        "transaction_count": transaction_count,
        "transaction_volume": float(transaction_volume),
        "user_count": user_count,
        "merchant_count": merchant_count,
        "pending_cases": pending_cases,
        "high_risk_assessments": high_risk,
        "transaction_types": [{"name": row[0], "count": row[1]} for row in type_rows],
        "recent_transactions": [_row_dict(row) for row in recent],
    }


@router.get("/api/dashboard/risk-trend")
async def dashboard_risk_trend(
    window: str = Query("24h", pattern="^(1h|6h|24h|7d)$"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    config = {"1h": (timedelta(hours=1), timedelta(minutes=5)), "6h": (timedelta(hours=6), timedelta(minutes=30)), "24h": (timedelta(hours=24), timedelta(hours=1)), "7d": (timedelta(days=7), timedelta(hours=6))}
    duration, step = config[window]
    end = datetime.now(UTC).replace(second=0, microsecond=0)
    start = end - duration
    bucket_count = int(duration / step) + 1
    points = [{"time": (start + step * index).isoformat(), "transactions": 0, "high_risk": 0, "new_cases": 0} for index in range(bucket_count)]

    def fill(rows: list[datetime], key: str) -> None:
        for value in rows:
            moment = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
            index = int((moment - start) / step)
            if 0 <= index < len(points): points[index][key] += 1

    fill(list((await db.execute(select(PaymentTransaction.create_time).where(PaymentTransaction.create_time >= start))).scalars()), "transactions")
    fill(list((await db.execute(select(RiskAssessment.create_time).where(RiskAssessment.create_time >= start, RiskAssessment.risk_level.in_(("高", "极高"))))).scalars()), "high_risk")
    fill(list((await db.execute(select(RiskCase.create_time).where(RiskCase.create_time >= start))).scalars()), "new_cases")
    return {"window": window, "bucket_seconds": int(step.total_seconds()), "updated_at": end.isoformat(), "points": points}


@router.get("/api/transactions")
async def list_transactions(
    transaction_type: str | None = None,
    transaction_id: str | None = None,
    payer_account_id: str | None = None,
    payee_account_id: str | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    asset_code: str | None = None,
    transaction_status: str | None = None,
    channel: str | None = None,
    create_time_from: datetime | None = None,
    create_time_to: datetime | None = None,
    complete_time_from: datetime | None = None,
    complete_time_to: datetime | None = None,
    sort_by: str = Query("create_time"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    statement = select(PaymentTransaction)
    count_statement = select(func.count()).select_from(PaymentTransaction)
    conditions = []
    exact = {"transaction_type": transaction_type, "asset_code": asset_code, "transaction_status": transaction_status, "channel": channel}
    for name, value in exact.items():
        if value:
            conditions.append(getattr(PaymentTransaction, name) == value)
    for name, value in {"transaction_id": transaction_id, "payer_account_id": payer_account_id, "payee_account_id": payee_account_id}.items():
        if value:
            conditions.append(getattr(PaymentTransaction, name).contains(value))
    ranges = ((PaymentTransaction.amount, amount_min, amount_max), (PaymentTransaction.create_time, create_time_from, create_time_to), (PaymentTransaction.complete_time, complete_time_from, complete_time_to))
    for column, lower, upper in ranges:
        if lower is not None:
            conditions.append(column >= lower)
        if upper is not None:
            conditions.append(column <= upper)
    if conditions:
        statement = statement.where(*conditions)
        count_statement = count_statement.where(*conditions)
    total = await db.scalar(count_statement) or 0
    sortable = {name: getattr(PaymentTransaction, name) for name in ("transaction_id", "transaction_type", "amount", "asset_code", "transaction_status", "channel", "create_time", "complete_time")}
    if sort_by not in sortable:
        raise HTTPException(422, f"unsupported sort_by: {sort_by}")
    size = limit or page_size
    order = asc(sortable[sort_by]) if sort_order == "asc" else desc(sortable[sort_by])
    rows = (await db.execute(statement.order_by(order).offset((page - 1) * size).limit(size))).scalars()
    return {"items": [_row_dict(row) for row in rows], "total": total, "page": page, "page_size": size}


async def _rows(db: AsyncSession, model: Any, condition: Any) -> list[dict[str, Any]]:
    return [_row_dict(row) for row in (await db.execute(select(model).where(condition))).scalars()]


@router.get("/api/transactions/{transaction_id}")
async def transaction_detail(transaction_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    transaction = await db.get(PaymentTransaction, transaction_id)
    if transaction is None:
        raise HTTPException(404, "transaction not found")
    subtype_model = {"USER_TRANSFER": UserTransfer, "MERCHANT_PAYMENT": MerchantPayment, "CROSS_BORDER": CrossBorderTransfer, "TOP_UP": CashMovement, "WITHDRAWAL": CashMovement}.get(transaction.transaction_type)
    subtype = await _rows(db, subtype_model, subtype_model.transaction_id == transaction_id) if subtype_model else []
    event = (await db.execute(select(RiskEvent).where(RiskEvent.event_source_id == transaction_id).order_by(desc(RiskEvent.create_time)).limit(1))).scalar_one_or_none()
    assessment = None
    case = None
    if event:
        assessment = (await db.execute(select(RiskAssessment).where(RiskAssessment.event_id == event.event_id).limit(1))).scalar_one_or_none()
        if assessment:
            case = (await db.execute(select(RiskCase).where(RiskCase.assessment_id == assessment.assessment_id).limit(1))).scalar_one_or_none()
    return {
        "transaction": _row_dict(transaction), "subtype": subtype,
        "parties": await _rows(db, TransactionParty, TransactionParty.transaction_id == transaction_id),
        "status_history": await _rows(db, TransactionStatusHistory, TransactionStatusHistory.transaction_id == transaction_id),
        "ledger_entries": await _rows(db, LedgerEntry, LedgerEntry.transaction_id == transaction_id),
        "fx": await _rows(db, FxConversion, FxConversion.transaction_id == transaction_id),
        "refunds": await _rows(db, Refund, Refund.original_transaction_id == transaction_id),
        "chargebacks": await _rows(db, Chargeback, Chargeback.transaction_id == transaction_id),
        "risk": {"event": _row_dict(event) if event else None, "assessment": _row_dict(assessment) if assessment else None, "case": _row_dict(case) if case else None},
    }


@router.get("/api/cases")
async def list_cases(
    status: str | None = None, category: str | None = None, user_id: str | None = None,
    event_type: str | None = None, created_from: datetime | None = None, created_to: datetime | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=200), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    conditions = []
    for column, value in ((RiskCase.case_status, status), (RiskCase.case_category, category), (RiskCase.event_type, event_type)):
        if value: conditions.append(column == value)
    if user_id: conditions.append(RiskCase.user_id.contains(user_id))
    if created_from: conditions.append(RiskCase.create_time >= created_from)
    if created_to: conditions.append(RiskCase.create_time <= created_to)
    total = await db.scalar(select(func.count()).select_from(RiskCase).where(*conditions)) or 0
    size = limit or page_size
    rows = (await db.execute(select(RiskCase).where(*conditions).order_by(desc(RiskCase.create_time)).offset((page - 1) * size).limit(size))).scalars()
    return {"items": [_row_dict(row) for row in rows], "total": total, "page": page, "page_size": size}


@router.get("/api/cases/{case_id}")
async def case_detail(case_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await db.get(RiskCase, case_id)
    if case is None: raise HTTPException(404, "case not found")
    assessment = await db.get(RiskAssessment, case.assessment_id)
    event = await db.get(RiskEvent, assessment.event_id) if assessment else None
    return {"case": _row_dict(case), "assessment": _row_dict(assessment) if assessment else None, "event": _row_dict(event) if event else None}


@router.post("/api/cases/{case_id}/review")
async def review_case(case_id: str, payload: CaseReviewRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    case = await db.get(RiskCase, case_id)
    if case is None: raise HTTPException(404, "case not found")
    if case.case_status not in {"待审核", "审核中"}: raise HTTPException(409, "case has already been reviewed")
    blacklist_id = None
    case.case_status, case.reviewer, case.review_comment, case.review_time = payload.decision, payload.reviewer, payload.review_comment, datetime.now(UTC)
    if payload.add_to_blacklist:
        value = f"USER:{case.user_id}"
        entry = (await db.execute(select(RiskBlacklist).where(RiskBlacklist.blacklist_type == "用户", RiskBlacklist.blacklist_value == value).limit(1))).scalar_one_or_none()
        if entry is None:
            entry = RiskBlacklist(blacklist_type="用户", blacklist_value=value, reason=payload.blacklist_reason or payload.review_comment, expire_time=payload.blacklist_expire_time)
            db.add(entry)
            await db.flush()
        elif entry.deleted_at is not None:
            entry.deleted_at, entry.reason, entry.expire_time = None, payload.blacklist_reason or payload.review_comment, payload.blacklist_expire_time
        blacklist_id = entry.blacklist_id
    detail = {"decision": payload.decision, "comment": payload.review_comment, "blacklist_id": blacklist_id}
    db.add(RiskActionLog(operator=payload.reviewer, action_type="REVIEW_CASE", target_type="CASE", target_id=case_id, detail=json.dumps(detail, ensure_ascii=False)))
    await db.commit()
    return {"case_id": case_id, "status": case.case_status, "blacklist_id": blacklist_id}


@router.get("/api/blacklist")
async def list_blacklist(
    value: str | None = None, reason: str | None = None, active: bool | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    now = datetime.now(UTC)
    conditions = [RiskBlacklist.blacklist_type == "用户"]
    if value: conditions.append(RiskBlacklist.blacklist_value.contains(value))
    if reason: conditions.append(RiskBlacklist.reason.contains(reason))
    if active is True: conditions.extend((RiskBlacklist.deleted_at.is_(None), (RiskBlacklist.expire_time.is_(None) | (RiskBlacklist.expire_time > now))))
    if active is False: conditions.append((RiskBlacklist.deleted_at.is_not(None)) | ((RiskBlacklist.expire_time.is_not(None)) & (RiskBlacklist.expire_time <= now)))
    total = await db.scalar(select(func.count()).select_from(RiskBlacklist).where(*conditions)) or 0
    rows = (await db.execute(select(RiskBlacklist).where(*conditions).order_by(desc(RiskBlacklist.create_time)).offset((page - 1) * page_size).limit(page_size))).scalars()
    items = []
    for row in rows:
        item = _row_dict(row); expire = row.expire_time
        if expire and expire.tzinfo is None: expire = expire.replace(tzinfo=UTC)
        item["active"] = row.deleted_at is None and (expire is None or expire > now); items.append(item)
    active_count = await db.scalar(select(func.count()).select_from(RiskBlacklist).where(RiskBlacklist.blacklist_type == "用户", RiskBlacklist.deleted_at.is_(None), (RiskBlacklist.expire_time.is_(None) | (RiskBlacklist.expire_time > now)))) or 0
    return {"items": items, "total": total, "active_count": active_count, "inactive_count": max(0, total - active_count), "page": page, "page_size": page_size}


@router.post("/api/blacklist")
async def add_blacklist(payload: BlacklistCreateRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    value = payload.user_id if payload.user_id.startswith("USER:") else f"USER:{payload.user_id}"
    entry = (await db.execute(select(RiskBlacklist).where(RiskBlacklist.blacklist_type == "用户", RiskBlacklist.blacklist_value == value).limit(1))).scalar_one_or_none()
    created = entry is None
    if entry is None:
        entry = RiskBlacklist(blacklist_type="用户", blacklist_value=value, reason=payload.reason, expire_time=payload.expire_time); db.add(entry); await db.flush()
    else:
        entry.deleted_at, entry.reason, entry.expire_time = None, payload.reason, payload.expire_time
    db.add(RiskActionLog(operator=payload.operator, action_type="ADD_BLACKLIST", target_type="USER", target_id=value, detail=payload.reason))
    await db.commit()
    return {"blacklist_id": entry.blacklist_id, "value": value, "created": created}


@router.delete("/api/blacklist/{blacklist_id}")
async def remove_blacklist(blacklist_id: int, operator: str = "risk-operator", db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    entry = await db.get(RiskBlacklist, blacklist_id)
    if entry is None: raise HTTPException(404, "blacklist entry not found")
    entry.deleted_at = datetime.now(UTC)
    db.add(RiskActionLog(operator=operator, action_type="REMOVE_BLACKLIST", target_type="USER", target_id=entry.blacklist_value, detail="soft delete"))
    await db.commit()
    return {"blacklist_id": blacklist_id, "removed": True}


@router.get("/api/interactions")
async def list_interactions(
    interaction_id: str | None = None, customer_type: str | None = None,
    customer_id: str | None = None, agent_id: str | None = None,
    channel_family: str | None = None, interaction_status: str | None = None,
    relationship_start_from: datetime | None = None, relationship_start_to: datetime | None = None,
    last_contact_from: datetime | None = None, last_contact_to: datetime | None = None,
    segment_count_min: int | None = Query(None, ge=0), segment_count_max: int | None = Query(None, ge=0),
    message_count_min: int | None = Query(None, ge=0), message_count_max: int | None = Query(None, ge=0),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
    limit: int | None = Query(None, ge=1, le=200), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    segment_count = func.count(func.distinct(ConversationSegment.segment_id))
    message_count = func.count(Message.message_id)
    statement = (
        select(
            Interaction, segment_count.label("segment_count"), message_count.label("message_count"),
        )
        .outerjoin(ConversationSegment, ConversationSegment.interaction_id == Interaction.interaction_id)
        .outerjoin(Message, Message.segment_id == ConversationSegment.segment_id)
        .group_by(*Interaction.__table__.columns)
    )
    conditions = []
    for name, value in {"customer_type": customer_type, "channel_family": channel_family, "interaction_status": interaction_status}.items():
        if value: conditions.append(getattr(Interaction, name) == value)
    for name, value in {"interaction_id": interaction_id, "customer_id": customer_id, "agent_id": agent_id}.items():
        if value: conditions.append(getattr(Interaction, name).contains(value))
    for column, lower, upper in ((Interaction.relationship_start_time, relationship_start_from, relationship_start_to), (Interaction.last_contact_time, last_contact_from, last_contact_to)):
        if lower is not None: conditions.append(column >= lower)
        if upper is not None: conditions.append(column <= upper)
    if conditions: statement = statement.where(*conditions)
    having = []
    if segment_count_min is not None: having.append(segment_count >= segment_count_min)
    if segment_count_max is not None: having.append(segment_count <= segment_count_max)
    if message_count_min is not None: having.append(message_count >= message_count_min)
    if message_count_max is not None: having.append(message_count <= message_count_max)
    if having: statement = statement.having(*having)
    count_query = select(func.count()).select_from(statement.subquery())
    total = await db.scalar(count_query) or 0
    size = limit or page_size
    rows = (await db.execute(statement.order_by(desc(Interaction.last_contact_time)).offset((page - 1) * size).limit(size))).all()
    return {
        "items": [
            {**_row_dict(row[0]), "segment_count": row.segment_count, "message_count": row.message_count}
            for row in rows
        ], "total": total, "page": page, "page_size": size,
    }


@router.get("/api/interactions/{interaction_id}")
async def interaction_detail(interaction_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    interaction = await db.get(Interaction, interaction_id)
    if interaction is None: raise HTTPException(404, "interaction not found")
    segments = await _rows(db, ConversationSegment, ConversationSegment.interaction_id == interaction_id)
    return {"interaction": _row_dict(interaction), "segments": sorted(segments, key=lambda x: x.get("start_time") or "")}


@router.get("/api/segments/{segment_id}")
async def segment_detail(segment_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    segment = await db.get(ConversationSegment, segment_id)
    if segment is None: raise HTTPException(404, "segment not found")
    messages = (await db.execute(select(Message).where(Message.segment_id == segment_id).order_by(Message.sent_time))).scalars()
    items = []
    for message in messages:
        item = _row_dict(message)
        email = (await db.execute(select(EmailEnvelope).where(EmailEnvelope.message_id == message.message_id).limit(1))).scalar_one_or_none()
        item["email"] = _row_dict(email) if email else None
        item["attachments"] = await _rows(db, MessageAttachment, MessageAttachment.message_id == message.message_id)
        items.append(item)
    return {"segment": _row_dict(segment), "messages": items}


@router.get("/api/messages/{message_id}")
async def message_detail(message_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    message = await db.get(Message, message_id)
    if message is None: raise HTTPException(404, "message not found")
    email = (await db.execute(select(EmailEnvelope).where(EmailEnvelope.message_id == message_id).limit(1))).scalar_one_or_none()
    return {"message": _row_dict(message), "email": _row_dict(email) if email else None, "attachments": await _rows(db, MessageAttachment, MessageAttachment.message_id == message_id)}


async def _submit_review(db: AsyncSession, *, source_id: str, user_id: str, event_type: str, payload: ReviewSubmission) -> dict[str, Any]:
    existing = (await db.execute(select(RiskCase).where(RiskCase.source_id == source_id, RiskCase.event_type == event_type, RiskCase.case_status.in_(("待审核", "审核中"))).limit(1))).scalar_one_or_none()
    if existing: return {"case_id": existing.case_id, "created": False, "status": existing.case_status}
    event_id, assessment_id, case_id = (f"EVT-{uuid.uuid4().hex}", f"ASM-{uuid.uuid4().hex}", f"CASE-{uuid.uuid4().hex}")
    detail = {"reason": payload.reason, "note": payload.note, "priority": payload.priority, "manual_submission": True}
    db.add(RiskEvent(event_id=event_id, event_type=event_type, event_source_id=source_id, user_id=user_id, event_data=json.dumps(detail, ensure_ascii=False)))
    db.add(RiskAssessment(assessment_id=assessment_id, event_id=event_id, user_id=user_id, rule_results="[]", final_score=70, risk_level="高", decision="人工审核"))
    db.add(RiskCase(case_id=case_id, assessment_id=assessment_id, user_id=user_id, case_status="待审核", case_category=payload.category, risk_detail=json.dumps(detail, ensure_ascii=False), source_id=source_id, event_type=event_type))
    db.add(RiskActionLog(operator=payload.operator, action_type="SUBMIT_MANUAL_REVIEW", target_type=event_type, target_id=source_id, detail=json.dumps(detail, ensure_ascii=False)))
    await db.commit()
    return {"case_id": case_id, "created": True, "status": "待审核"}


@router.post("/api/transactions/{transaction_id}/submit-review")
async def submit_transaction_review(transaction_id: str, payload: ReviewSubmission, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    transaction = await db.get(PaymentTransaction, transaction_id)
    if transaction is None: raise HTTPException(404, "transaction not found")
    payer = (await db.execute(select(TransactionParty.party_reference).where(TransactionParty.transaction_id == transaction_id, TransactionParty.party_role == "PAYER").limit(1))).scalar_one_or_none()
    return await _submit_review(db, source_id=transaction_id, user_id=payer or transaction.payer_account_id, event_type="支付", payload=payload)


@router.post("/api/interactions/{interaction_id}/submit-review")
async def submit_interaction_review(interaction_id: str, payload: ReviewSubmission, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    interaction = await db.get(Interaction, interaction_id)
    if interaction is None: raise HTTPException(404, "interaction not found")
    return await _submit_review(db, source_id=interaction_id, user_id=interaction.customer_id, event_type="客服交互", payload=payload)


@router.post("/api/segments/{segment_id}/submit-review")
async def submit_segment_review(segment_id: str, payload: ReviewSubmission, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    segment = await db.get(ConversationSegment, segment_id)
    if segment is None: raise HTTPException(404, "segment not found")
    interaction = await db.get(Interaction, segment.interaction_id)
    return await _submit_review(db, source_id=segment_id, user_id=interaction.customer_id, event_type="客服会话", payload=payload)


@router.post("/api/messages/{message_id}/submit-review")
async def submit_message_review(message_id: str, payload: ReviewSubmission, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    message = await db.get(Message, message_id)
    if message is None: raise HTTPException(404, "message not found")
    segment = await db.get(ConversationSegment, message.segment_id)
    interaction = await db.get(Interaction, segment.interaction_id)
    return await _submit_review(db, source_id=message_id, user_id=interaction.customer_id, event_type="客服消息", payload=payload)


@router.get("/api/rules/summary")
async def rules_summary(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    total = await db.scalar(select(func.count()).select_from(RiskRule)) or 0
    enabled = await db.scalar(
        select(func.count()).select_from(RiskRule).where(RiskRule.is_enabled.is_(True))
    ) or 0
    return {"total": total, "enabled": enabled}
