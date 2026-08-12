"""Signed client-appeal workflow with immutable original decisions."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models_risk import (
    RiskActionLog,
    RiskAppeal,
    RiskAppealEvidence,
    RiskAssessment,
    RiskEvent,
    RiskLabel,
)
from app.observability import pseudonymize
from app.schemas import AppealEvidenceRequest, AppealReviewDecision, AppealReviewRequest, AppealSubmissionRequest


appeal_logger = logging.getLogger("bankrisk.decision")
TERMINAL_APPEAL_STATUSES = {"DECISION_UPHELD", "DECISION_OVERTURNED", "CLOSED"}


class AppealServiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_appeal_token(assessment_id: str) -> tuple[str, datetime]:
    """Issue a signed token without embedding the customer identifier."""
    deadline = _utc_now() + timedelta(days=settings.APPEAL_WINDOW_DAYS)
    payload = json.dumps(
        {"assessment_id": assessment_id, "expires_at": int(deadline.replace(tzinfo=UTC).timestamp())},
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_payload = _encode(payload)
    signature = hmac.new(
        settings.APPEAL_SIGNING_KEY.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_encode(signature)}", deadline


def verify_appeal_token(token: str, assessment_id: str) -> datetime:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            settings.APPEAL_SIGNING_KEY.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_decode(encoded_signature), expected_signature):
            raise ValueError("signature mismatch")
        payload = json.loads(_decode(encoded_payload))
        if payload.get("assessment_id") != assessment_id:
            raise ValueError("assessment mismatch")
        deadline = datetime.fromtimestamp(int(payload["expires_at"]), UTC).replace(tzinfo=None)
    except (ValueError, KeyError, TypeError, binascii.Error, UnicodeDecodeError) as exc:
        raise AppealServiceError(401, "申诉凭证无效") from exc
    if deadline < _utc_now():
        raise AppealServiceError(410, "申诉凭证已过期")
    return deadline


def verify_internal_review_token(token: str) -> None:
    configured = settings.APPEAL_REVIEW_TOKEN
    if not configured:
        raise AppealServiceError(503, "内部复议令牌未配置")
    if not hmac.compare_digest(token, configured):
        raise AppealServiceError(403, "内部复议令牌无效")


async def _appeal_response(session: AsyncSession, appeal: RiskAppeal) -> dict:
    assessment = await session.get(RiskAssessment, appeal.assessment_id)
    evidence = (
        await session.scalars(
            select(RiskAppealEvidence)
            .where(RiskAppealEvidence.appeal_id == appeal.appeal_id)
            .order_by(RiskAppealEvidence.created_at)
        )
    ).all()
    return {
        "appeal_id": appeal.appeal_id,
        "assessment_id": appeal.assessment_id,
        "scenario": appeal.scenario,
        "status": appeal.status,
        "reason": appeal.reason,
        "requested_resolution": appeal.requested_resolution,
        "appeal_deadline": appeal.appeal_deadline,
        "review_due_at": appeal.review_due_at,
        "review_decision": appeal.review_decision,
        "review_comment": appeal.review_comment,
        "submitted_at": appeal.submitted_at,
        "reviewed_at": appeal.reviewed_at,
        "original_assessment": {
            "final_score": assessment.final_score if assessment else None,
            "risk_level": assessment.risk_level if assessment else None,
            "decision": assessment.decision if assessment else None,
            "created_at": assessment.created_at if assessment else None,
        },
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "evidence_type": item.evidence_type,
                "statement": item.statement,
                "file_name": item.file_name,
                "file_sha256": item.file_sha256,
                "status": item.status,
                "created_at": item.created_at,
            }
            for item in evidence
        ],
    }


async def submit_client_appeal(
    session: AsyncSession,
    data: AppealSubmissionRequest,
) -> tuple[dict, bool]:
    deadline = verify_appeal_token(data.appeal_token, data.assessment_id)
    assessment = await session.get(RiskAssessment, data.assessment_id)
    if assessment is None:
        raise AppealServiceError(404, "原始风险评估不存在")
    if assessment.decision != "拒绝":
        raise AppealServiceError(409, "只有拒绝决策可以发起客户申诉")
    existing = await session.scalar(
        select(RiskAppeal).where(RiskAppeal.assessment_id == data.assessment_id)
    )
    if existing is not None:
        return await _appeal_response(session, existing), False

    event = await session.get(RiskEvent, assessment.event_id)
    if event is None:
        raise AppealServiceError(409, "原始风险事件审计链不完整")
    now = _utc_now()
    appeal = RiskAppeal(
        appeal_id=f"APL_{uuid4().hex}",
        assessment_id=assessment.assessment_id,
        user_id=assessment.user_id,
        scenario=assessment.scenario,
        source_id=event.source_id,
        status="SUBMITTED",
        reason=data.reason,
        requested_resolution=data.requested_resolution,
        appeal_deadline=deadline,
        review_due_at=now + timedelta(days=settings.APPEAL_REVIEW_SLA_DAYS),
    )
    session.add(appeal)
    session.add(
        RiskActionLog(
            operator="client",
            action_type="SUBMIT_APPEAL",
            target_type="appeal",
            target_id=appeal.appeal_id,
            after_value={"status": appeal.status, "assessment_id": assessment.assessment_id},
            remark="客户使用签名凭证提交申诉",
        )
    )
    await session.commit()
    await session.refresh(appeal)
    appeal_logger.info(
        "client_appeal_submitted",
        extra={
            "event_data": {
                "outcome": "APPEAL_SUBMITTED",
                "appeal_id": appeal.appeal_id,
                "assessment_id": assessment.assessment_id,
                "user_ref": pseudonymize(assessment.user_id),
                "source_ref": pseudonymize(event.source_id),
                "status": appeal.status,
                "review_due_at": appeal.review_due_at,
            }
        },
    )
    return await _appeal_response(session, appeal), True


async def get_client_appeal(
    session: AsyncSession,
    appeal_id: str,
    appeal_token: str,
) -> dict:
    appeal = await session.get(RiskAppeal, appeal_id)
    if appeal is None:
        raise AppealServiceError(404, "申诉不存在")
    verify_appeal_token(appeal_token, appeal.assessment_id)
    return await _appeal_response(session, appeal)


async def add_client_evidence(
    session: AsyncSession,
    appeal_id: str,
    appeal_token: str,
    data: AppealEvidenceRequest,
) -> dict:
    appeal = await session.get(RiskAppeal, appeal_id)
    if appeal is None:
        raise AppealServiceError(404, "申诉不存在")
    verify_appeal_token(appeal_token, appeal.assessment_id)
    if appeal.status in TERMINAL_APPEAL_STATUSES:
        raise AppealServiceError(409, "申诉已终结，不能继续补充材料")

    if data.file_sha256:
        existing = await session.scalar(
            select(RiskAppealEvidence).where(
                RiskAppealEvidence.appeal_id == appeal_id,
                RiskAppealEvidence.file_sha256 == data.file_sha256.lower(),
            )
        )
        if existing is not None:
            return await _appeal_response(session, appeal)
    file_name = Path(data.file_name.replace("\\", "/")).name if data.file_name else None
    evidence = RiskAppealEvidence(
        evidence_id=f"EVD_{uuid4().hex}",
        appeal_id=appeal_id,
        evidence_type=data.evidence_type.value,
        statement=data.statement,
        file_name=file_name,
        file_sha256=data.file_sha256.lower() if data.file_sha256 else None,
        storage_reference=None,
        status="RECEIVED",
    )
    session.add(evidence)
    if appeal.status == "NEEDS_INFO":
        appeal.status = "SUBMITTED"
    session.add(
        RiskActionLog(
            operator="client",
            action_type="ADD_APPEAL_EVIDENCE",
            target_type="appeal",
            target_id=appeal_id,
            after_value={"evidence_id": evidence.evidence_id, "evidence_type": evidence.evidence_type},
            remark="客户补充申诉材料元数据",
        )
    )
    await session.commit()
    await session.refresh(evidence)
    appeal_logger.info(
        "client_appeal_evidence_added",
        extra={
            "event_data": {
                "outcome": "APPEAL_EVIDENCE_RECEIVED",
                "appeal_id": appeal_id,
                "assessment_id": appeal.assessment_id,
                "evidence_id": evidence.evidence_id,
                "evidence_type": evidence.evidence_type,
                "has_file": bool(evidence.file_sha256),
            }
        },
    )
    return await _appeal_response(session, appeal)


async def list_internal_appeals(
    session: AsyncSession,
    internal_token: str,
    status: str | None,
    page: int,
    page_size: int,
) -> dict:
    verify_internal_review_token(internal_token)
    filters = [RiskAppeal.status == status] if status else []
    total = int(
        await session.scalar(select(func.count()).select_from(RiskAppeal).where(*filters)) or 0
    )
    rows = (
        await session.scalars(
            select(RiskAppeal)
            .where(*filters)
            .order_by(RiskAppeal.submitted_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [
            {
                "appeal_id": item.appeal_id,
                "assessment_id": item.assessment_id,
                "user_ref": pseudonymize(item.user_id),
                "source_ref": pseudonymize(item.source_id),
                "scenario": item.scenario,
                "status": item.status,
                "reason": item.reason,
                "requested_resolution": item.requested_resolution,
                "review_due_at": item.review_due_at,
                "submitted_at": item.submitted_at,
            }
            for item in rows
        ],
    }


async def review_internal_appeal(
    session: AsyncSession,
    appeal_id: str,
    internal_token: str,
    data: AppealReviewRequest,
) -> dict:
    verify_internal_review_token(internal_token)
    appeal = await session.get(RiskAppeal, appeal_id)
    if appeal is None:
        raise AppealServiceError(404, "申诉不存在")
    if appeal.status in TERMINAL_APPEAL_STATUSES:
        raise AppealServiceError(409, "申诉已处于终态，不能重复复议")

    before_status = appeal.status
    now = _utc_now()
    appeal.reviewer = data.reviewer
    appeal.review_comment = data.comment
    appeal.review_decision = data.decision.value
    if data.decision is AppealReviewDecision.MORE_INFO_REQUIRED:
        appeal.status = "NEEDS_INFO"
        appeal.reviewed_at = None
    elif data.decision is AppealReviewDecision.UPHOLD:
        appeal.status = "DECISION_UPHELD"
        appeal.reviewed_at = now
    else:
        appeal.status = "DECISION_OVERTURNED"
        appeal.reviewed_at = now
        session.add(
            RiskLabel(
                scenario=appeal.scenario,
                source_id=appeal.source_id,
                user_id=appeal.user_id,
                label="LEGIT",
                label_source="APPEAL",
                confidence=Decimal("1.0000"),
                notes=f"申诉 {appeal.appeal_id} 经授权复议后推翻原拒绝决策",
            )
        )
    session.add(
        RiskActionLog(
            operator=data.reviewer,
            action_type="REVIEW_APPEAL",
            target_type="appeal",
            target_id=appeal_id,
            before_value={"status": before_status},
            after_value={"status": appeal.status, "review_decision": appeal.review_decision},
            remark="内部授权复议；原始风险评估保持不变",
        )
    )
    await session.commit()
    appeal_logger.info(
        "internal_appeal_reviewed",
        extra={
            "event_data": {
                "outcome": appeal.status,
                "appeal_id": appeal_id,
                "assessment_id": appeal.assessment_id,
                "review_decision": appeal.review_decision,
                "reviewer_ref": pseudonymize(data.reviewer),
                "original_decision_preserved": True,
            }
        },
    )
    return await _appeal_response(session, appeal)
