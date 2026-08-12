"""管理端查询与案件、黑名单闭环服务。"""

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Decision, EventType, RiskLevel
from app.models_risk import (
    ActionTargetType,
    ActionType,
    BlacklistType,
    CaseStatus,
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskUserProfile,
)
from app.schemas import (
    AssessmentDetailResponse,
    AssessmentItem,
    AssessmentListResponse,
    BlacklistCreate,
    BlacklistListResponse,
    BlacklistResponse,
    CaseDetailResponse,
    CaseItem,
    CaseListResponse,
    CaseReviewRequest,
    CaseStatistics,
    DashboardOverview,
    UserProfileResponse,
)
from app.service.action_log import record_action, selected_fields


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def mask_sensitive_value(value: str) -> str:
    """管理列表只展示脱敏值，完整值仍保存在数据库供风控匹配。"""

    if len(value) <= 4:
        return "*" * len(value)
    if len(value) <= 10:
        return f"{value[:2]}****{value[-2:]}"
    return f"{value[:4]}{'*' * min(len(value) - 8, 12)}{value[-4:]}"


def _case_item(case: RiskCase, assessment: RiskAssessment) -> CaseItem:
    return CaseItem(
        case_id=case.case_id,
        assessment_id=case.assessment_id,
        user_id=case.user_id,
        case_status=case.case_status,
        case_category=case.case_category,
        source_id=case.source_id,
        event_type=case.event_type,
        final_score=assessment.final_score,
        risk_level=assessment.risk_level,
        decision=assessment.decision,
        rule_count=assessment.rule_count,
        reviewer=case.reviewer,
        create_time=case.create_time,
        update_time=case.update_time,
    )


async def list_cases(
    db: AsyncSession,
    *,
    status: CaseStatus | None,
    user_id: str | None,
    active_only: bool,
    page: int,
    page_size: int,
) -> CaseListResponse:
    filters: list[Any] = []
    if status is not None:
        filters.append(RiskCase.case_status == status)
    elif active_only:
        filters.append(RiskCase.case_status.in_((CaseStatus.PENDING, CaseStatus.REVIEWING)))
    if user_id:
        filters.append(RiskCase.user_id == user_id)

    total = int(
        (await db.execute(select(func.count(RiskCase.case_id)).where(*filters))).scalar_one()
        or 0
    )
    rows = (
        await db.execute(
            select(RiskCase, RiskAssessment)
            .join(RiskAssessment, RiskAssessment.assessment_id == RiskCase.assessment_id)
            .where(*filters)
            .order_by(RiskCase.create_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return CaseListResponse(
        items=[_case_item(case, assessment) for case, assessment in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def case_statistics(db: AsyncSession) -> CaseStatistics:
    rows = (
        await db.execute(
            select(RiskCase.case_status, func.count(RiskCase.case_id)).group_by(
                RiskCase.case_status
            )
        )
    ).all()
    counts = {status: int(count) for status, count in rows}
    return CaseStatistics(
        total=sum(counts.values()),
        pending=counts.get(CaseStatus.PENDING, 0),
        reviewing=counts.get(CaseStatus.REVIEWING, 0),
        approved=counts.get(CaseStatus.APPROVED, 0),
        rejected=counts.get(CaseStatus.REJECTED, 0),
        closed=counts.get(CaseStatus.CLOSED, 0),
    )


async def case_detail(db: AsyncSession, case_id: str) -> CaseDetailResponse | None:
    row = (
        await db.execute(
            select(RiskCase, RiskAssessment, RiskEvent)
            .join(RiskAssessment, RiskAssessment.assessment_id == RiskCase.assessment_id)
            .join(RiskEvent, RiskEvent.event_id == RiskAssessment.event_id)
            .where(RiskCase.case_id == case_id)
        )
    ).one_or_none()
    if row is None:
        return None
    case, assessment, event = row
    features = (
        await db.execute(
            select(RiskFeature.feature_name, RiskFeature.feature_value).where(
                RiskFeature.event_id == assessment.event_id
            )
        )
    ).all()
    base = _case_item(case, assessment).model_dump()
    return CaseDetailResponse(
        **base,
        risk_detail=case.risk_detail,
        review_comment=case.review_comment,
        review_time=case.review_time,
        triggered_rules=assessment.rule_results or [],
        features={name: float(value) for name, value in features},
        ml_score=float(assessment.ml_score) if assessment.ml_score is not None else None,
        ml_decision=assessment.ml_decision,
        event_data=event.event_data,
    )


ALLOWED_CASE_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.PENDING: {
        CaseStatus.REVIEWING,
        CaseStatus.APPROVED,
        CaseStatus.REJECTED,
        CaseStatus.CLOSED,
    },
    CaseStatus.REVIEWING: {
        CaseStatus.APPROVED,
        CaseStatus.REJECTED,
        CaseStatus.CLOSED,
    },
    CaseStatus.APPROVED: set(),
    CaseStatus.REJECTED: set(),
    CaseStatus.CLOSED: set(),
}


async def _upsert_blacklist(
    db: AsyncSession,
    data: BlacklistCreate,
) -> RiskBlacklist:
    existing = (
        await db.execute(
            select(RiskBlacklist).where(
                RiskBlacklist.blacklist_type == data.blacklist_type,
                RiskBlacklist.blacklist_value == data.blacklist_value,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = RiskBlacklist(
            blacklist_type=data.blacklist_type,
            blacklist_value=data.blacklist_value,
            reason=data.reason,
            expire_time=data.expire_time,
        )
        db.add(existing)
        await db.flush()
        before = None
    else:
        before = selected_fields(existing, "reason", "expire_time", "deleted_at")
        existing.reason = data.reason
        existing.expire_time = data.expire_time
        existing.deleted_at = None
        await db.flush()

    await record_action(
        db,
        operator=data.operator,
        action_type=ActionType.ADD_BLACKLIST,
        target_type=ActionTargetType.BLACKLIST,
        target_id=str(existing.blacklist_id),
        before_value=before,
        after_value={
            "blacklist_type": existing.blacklist_type,
            "blacklist_value_masked": mask_sensitive_value(existing.blacklist_value),
            "reason": existing.reason,
            "expire_time": existing.expire_time,
        },
        remark="新增或恢复银行黑名单",
    )
    return existing


def _blacklist_response(row: RiskBlacklist) -> BlacklistResponse:
    return BlacklistResponse(
        blacklist_id=row.blacklist_id,
        blacklist_type=row.blacklist_type,
        blacklist_value_masked=mask_sensitive_value(row.blacklist_value),
        reason=row.reason,
        expire_time=row.expire_time,
        create_time=row.create_time,
    )


async def add_blacklist(db: AsyncSession, data: BlacklistCreate) -> BlacklistResponse:
    row = await _upsert_blacklist(db, data)
    await db.flush()
    return _blacklist_response(row)


async def list_blacklist(
    db: AsyncSession,
    *,
    blacklist_type: BlacklistType | None,
    page: int,
    page_size: int,
) -> BlacklistListResponse:
    filters: list[Any] = [RiskBlacklist.deleted_at.is_(None)]
    if blacklist_type is not None:
        filters.append(RiskBlacklist.blacklist_type == blacklist_type)
    total = int(
        (await db.execute(select(func.count(RiskBlacklist.blacklist_id)).where(*filters))).scalar_one()
        or 0
    )
    rows = (
        await db.execute(
            select(RiskBlacklist)
            .where(*filters)
            .order_by(RiskBlacklist.create_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return BlacklistListResponse(
        items=[_blacklist_response(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def remove_blacklist(
    db: AsyncSession,
    blacklist_id: int,
    *,
    operator: str,
) -> bool:
    row = await db.get(RiskBlacklist, blacklist_id)
    if row is None or row.deleted_at is not None:
        return False
    before = {
        "blacklist_type": row.blacklist_type,
        "blacklist_value_masked": mask_sensitive_value(row.blacklist_value),
        "reason": row.reason,
    }
    row.deleted_at = utc_now_naive()
    await record_action(
        db,
        operator=operator,
        action_type=ActionType.REMOVE_BLACKLIST,
        target_type=ActionTargetType.BLACKLIST,
        target_id=str(row.blacklist_id),
        before_value=before,
        after_value={"deleted_at": row.deleted_at},
        remark="软删除银行黑名单",
    )
    return True


async def review_case(
    db: AsyncSession,
    case_id: str,
    data: CaseReviewRequest,
) -> CaseDetailResponse:
    case = await db.get(RiskCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="案件不存在")
    allowed = ALLOWED_CASE_TRANSITIONS.get(case.case_status, set())
    if data.new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"案件不能从“{case.case_status.value}”变更为“{data.new_status.value}”",
        )
    if data.add_to_blacklist and data.new_status is not CaseStatus.REJECTED:
        raise HTTPException(status_code=400, detail="只有人工拒绝案件时才能同时加入黑名单")

    before = selected_fields(case, "case_status", "reviewer", "review_comment", "review_time")
    case.case_status = data.new_status
    case.reviewer = data.reviewer
    case.review_comment = data.review_comment
    case.review_time = utc_now_naive()
    case.update_time = case.review_time
    await record_action(
        db,
        operator=data.reviewer,
        action_type=ActionType.REVIEW_CASE,
        target_type=ActionTargetType.CASE,
        target_id=case.case_id,
        before_value=before,
        after_value=selected_fields(
            case, "case_status", "reviewer", "review_comment", "review_time"
        ),
        remark="人工审核银行风险案件",
    )

    if data.add_to_blacklist:
        value = data.blacklist_value
        if data.blacklist_type is BlacklistType.USER and not value:
            value = case.user_id
        if not value:
            raise HTTPException(status_code=400, detail="该黑名单类型必须填写黑名单值")
        await _upsert_blacklist(
            db,
            BlacklistCreate(
                blacklist_type=data.blacklist_type,
                blacklist_value=value,
                reason=f"案件 {case.case_id} 人工拒绝：{data.review_comment}",
                expire_time=data.blacklist_expire_time,
                operator=data.reviewer,
            ),
        )
    await db.flush()
    detail = await case_detail(db, case_id)
    if detail is None:  # pragma: no cover - 同一事务内不可能消失
        raise HTTPException(status_code=404, detail="案件不存在")
    return detail


def _assessment_item(assessment: RiskAssessment, event: RiskEvent) -> AssessmentItem:
    return AssessmentItem(
        assessment_id=assessment.assessment_id,
        event_id=assessment.event_id,
        user_id=assessment.user_id,
        event_type=event.event_type,
        event_source_id=event.event_source_id,
        final_score=assessment.final_score,
        risk_level=assessment.risk_level,
        decision=assessment.decision,
        rule_count=assessment.rule_count,
        ml_score=float(assessment.ml_score) if assessment.ml_score is not None else None,
        ml_decision=assessment.ml_decision,
        create_time=assessment.create_time,
    )


async def list_assessments(
    db: AsyncSession,
    *,
    decision: Decision | None,
    risk_level: RiskLevel | None,
    event_type: EventType | None,
    user_id: str | None,
    page: int,
    page_size: int,
) -> AssessmentListResponse:
    filters: list[Any] = []
    if decision is not None:
        filters.append(RiskAssessment.decision == decision)
    if risk_level is not None:
        filters.append(RiskAssessment.risk_level == risk_level)
    if event_type is not None:
        filters.append(RiskEvent.event_type == event_type)
    if user_id:
        filters.append(RiskAssessment.user_id == user_id)
    joined = RiskAssessment.__table__.join(
        RiskEvent.__table__, RiskAssessment.event_id == RiskEvent.event_id
    )
    total = int(
        (
            await db.execute(
                select(func.count(RiskAssessment.assessment_id))
                .select_from(joined)
                .where(*filters)
            )
        ).scalar_one()
        or 0
    )
    rows = (
        await db.execute(
            select(RiskAssessment, RiskEvent)
            .join(RiskEvent, RiskEvent.event_id == RiskAssessment.event_id)
            .where(*filters)
            .order_by(RiskAssessment.create_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return AssessmentListResponse(
        items=[_assessment_item(assessment, event) for assessment, event in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def assessment_detail(
    db: AsyncSession,
    assessment_id: str,
) -> AssessmentDetailResponse | None:
    row = (
        await db.execute(
            select(RiskAssessment, RiskEvent)
            .join(RiskEvent, RiskEvent.event_id == RiskAssessment.event_id)
            .where(RiskAssessment.assessment_id == assessment_id)
        )
    ).one_or_none()
    if row is None:
        return None
    assessment, event = row
    features = (
        await db.execute(
            select(RiskFeature.feature_name, RiskFeature.feature_value).where(
                RiskFeature.event_id == assessment.event_id
            )
        )
    ).all()
    return AssessmentDetailResponse(
        **_assessment_item(assessment, event).model_dump(),
        triggered_rules=assessment.rule_results or [],
        features={name: float(value) for name, value in features},
        event_data=event.event_data,
    )


async def user_profile(db: AsyncSession, user_id: str) -> UserProfileResponse | None:
    profile = await db.get(RiskUserProfile, user_id)
    if profile is None:
        return None
    return UserProfileResponse(
        user_id=profile.user_id,
        risk_score=profile.risk_score,
        risk_level=profile.risk_level,
        txn_count_30d=profile.txn_count_30d,
        txn_amount_30d=float(profile.txn_amount_30d),
        failed_login_count_30d=profile.failed_login_count_30d,
        device_count=profile.device_count,
        high_risk_ip_count_30d=profile.high_risk_ip_count_30d,
        loan_application_count_30d=profile.loan_application_count_30d,
        debt_ratio=float(profile.debt_ratio),
        assessment_count=profile.assessment_count,
        last_assessment_time=profile.last_assessment_time,
        profile_data=profile.profile_data,
        update_time=profile.update_time,
    )


async def dashboard_overview(db: AsyncSession) -> DashboardOverview:
    now = utc_now_naive()
    today_start = datetime.combine(now.date(), datetime.min.time())
    week_start = today_start - timedelta(days=6)

    today_assessments = int(
        (
            await db.execute(
                select(func.count(RiskAssessment.assessment_id)).where(
                    RiskAssessment.create_time >= today_start
                )
            )
        ).scalar_one()
        or 0
    )
    today_high_risk = int(
        (
            await db.execute(
                select(func.count(RiskAssessment.assessment_id)).where(
                    RiskAssessment.create_time >= today_start,
                    RiskAssessment.risk_level.in_((RiskLevel.HIGH, RiskLevel.EXTREME)),
                )
            )
        ).scalar_one()
        or 0
    )
    today_rejected = int(
        (
            await db.execute(
                select(func.count(RiskAssessment.assessment_id)).where(
                    RiskAssessment.create_time >= today_start,
                    RiskAssessment.decision == Decision.REJECT,
                )
            )
        ).scalar_one()
        or 0
    )
    pending_cases = int(
        (
            await db.execute(
                select(func.count(RiskCase.case_id)).where(
                    RiskCase.case_status.in_((CaseStatus.PENDING, CaseStatus.REVIEWING))
                )
            )
        ).scalar_one()
        or 0
    )
    today_passed = int(
        (
            await db.execute(
                select(func.count(RiskAssessment.assessment_id)).where(
                    RiskAssessment.create_time >= today_start,
                    RiskAssessment.decision == Decision.PASS,
                )
            )
        ).scalar_one()
        or 0
    )

    risk_rows = (
        await db.execute(
            select(RiskAssessment.risk_level, func.count(RiskAssessment.assessment_id)).group_by(
                RiskAssessment.risk_level
            )
        )
    ).all()
    decision_rows = (
        await db.execute(
            select(RiskAssessment.decision, func.count(RiskAssessment.assessment_id)).group_by(
                RiskAssessment.decision
            )
        )
    ).all()
    event_rows = (
        await db.execute(
            select(RiskEvent.event_type, func.count(RiskEvent.event_id)).group_by(
                RiskEvent.event_type
            )
        )
    ).all()

    recent = (
        await db.execute(
            select(RiskAssessment.create_time, RiskAssessment.risk_level, RiskAssessment.rule_results)
            .where(RiskAssessment.create_time >= week_start)
            .order_by(RiskAssessment.create_time.asc())
        )
    ).all()
    trend_map: dict[date, dict[str, int]] = {
        (today_start.date() - timedelta(days=offset)): {"total": 0, "high_risk": 0}
        for offset in range(6, -1, -1)
    }
    rule_counter: Counter[tuple[str, str]] = Counter()
    for created, level, rules in recent:
        point = trend_map.get(created.date())
        if point is not None:
            point["total"] += 1
            if level in (RiskLevel.HIGH, RiskLevel.EXTREME):
                point["high_risk"] += 1
        for rule in rules or []:
            rule_counter[(str(rule.get("rule_id", "未知")), str(rule.get("rule_name", "未知规则")))] += 1

    return DashboardOverview(
        today_assessments=today_assessments,
        today_high_risk=today_high_risk,
        today_rejected=today_rejected,
        pending_cases=pending_cases,
        pass_rate=round(today_passed * 100 / today_assessments, 1) if today_assessments else 0.0,
        risk_distribution={level.value: int(count) for level, count in risk_rows},
        event_distribution={event.value: int(count) for event, count in event_rows},
        decision_distribution={decision.value: int(count) for decision, count in decision_rows},
        trend_7d=[
            {"date": day.isoformat(), **counts} for day, counts in trend_map.items()
        ],
        top_rules=[
            {"rule_id": rule_id, "rule_name": name, "hit_count": count}
            for (rule_id, name), count in rule_counter.most_common(5)
        ],
    )
