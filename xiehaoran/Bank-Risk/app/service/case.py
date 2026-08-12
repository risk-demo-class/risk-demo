"""
案件管理 / 黑名单 / 用户画像 / 评估历史 (银行语义)

Commit 策略:
  *atomic 后缀: 内部 self-commit
  *tx 后缀:    保留事务给调用方
"""
import json
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BLACKLIST_TYPE_KEYS
from app.models_risk import RiskAssessment, RiskBlacklist, RiskCase, RiskEvent, RiskUserProfile
from app.schemas import (
    AssessmentDetailResponse, AssessmentItem, AssessmentListResponse, BlacklistCreate,
    BlacklistResponse, CaseDetailResponse, CaseItem, CaseListResponse, CaseReviewRequest,
    CaseStatistics, RuleHitInfo, UserProfileResponse,
)
from app.service.action_log import record_action

logger = logging.getLogger(__name__)


# ============================================================
# 黑名单
# ============================================================
async def check_blacklist(db: AsyncSession, blacklist_type: str, value: str) -> bool:
    """撞黑检查 (软删 + 过期过滤)."""
    if blacklist_type not in BLACKLIST_TYPE_KEYS:
        return False
    bl = (await db.execute(
        select(RiskBlacklist).where(
            RiskBlacklist.blacklist_type == blacklist_type,
            RiskBlacklist.blacklist_value == value,
            RiskBlacklist.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not bl:
        return False
    if bl.expire_time and bl.expire_time < datetime.now():
        return False
    return True


async def add_blacklist(db: AsyncSession, request: BlacklistCreate) -> BlacklistResponse:
    existing = (await db.execute(
        select(RiskBlacklist).where(
            RiskBlacklist.blacklist_type == request.blacklist_type,
            RiskBlacklist.blacklist_value == request.blacklist_value,
            RiskBlacklist.deleted_at.is_(None),
        )
    )).scalar_one_or_none()

    if existing:
        before_value = {"reason": existing.reason, "expire_time": str(existing.expire_time) if existing.expire_time else None}
        existing.reason = request.reason
        existing.expire_time = request.expire_time
        await record_action(db, operator="admin", action_type="ADD_BLACKLIST",
            target_type="blacklist", target_id=existing.blacklist_id,
            before_value=before_value,
            after_value={"reason": request.reason, "expire_time": str(request.expire_time) if request.expire_time else None},
            remark=f"更新黑名单 {request.blacklist_type}={request.blacklist_value}")
        return BlacklistResponse(
            blacklist_id=existing.blacklist_id, blacklist_type=existing.blacklist_type,
            blacklist_value=existing.blacklist_value, reason=existing.reason,
            expire_time=existing.expire_time, create_time=existing.create_time)

    bl = RiskBlacklist(
        blacklist_type=request.blacklist_type, blacklist_value=request.blacklist_value,
        reason=request.reason, expire_time=request.expire_time)
    db.add(bl)
    await db.flush()
    await record_action(db, operator="admin", action_type="ADD_BLACKLIST",
        target_type="blacklist", target_id=bl.blacklist_id,
        before_value=None,
        after_value={"blacklist_type": bl.blacklist_type, "blacklist_value": bl.blacklist_value,
                     "reason": bl.reason, "expire_time": str(bl.expire_time) if bl.expire_time else None},
        remark=f"新增黑名单 {bl.blacklist_type}={bl.blacklist_value}")
    return BlacklistResponse(
        blacklist_id=bl.blacklist_id, blacklist_type=bl.blacklist_type,
        blacklist_value=bl.blacklist_value, reason=bl.reason,
        expire_time=bl.expire_time, create_time=bl.create_time)


async def get_blacklist(db: AsyncSession, page: int = 1, page_size: int = 20,
                        blacklist_type: str | None = None) -> tuple[int, list[BlacklistResponse]]:
    where = [RiskBlacklist.deleted_at.is_(None)]
    if blacklist_type:
        where.append(RiskBlacklist.blacklist_type == blacklist_type)
    total = int((await db.execute(
        select(func.count()).select_from(RiskBlacklist).where(*where)
    )).scalar() or 0)
    items = (await db.execute(
        select(RiskBlacklist).where(*where)
        .order_by(RiskBlacklist.create_time.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return total, [
        BlacklistResponse(blacklist_id=b.blacklist_id, blacklist_type=b.blacklist_type,
            blacklist_value=b.blacklist_value, reason=b.reason,
            expire_time=b.expire_time, create_time=b.create_time)
        for b in items
    ]


async def get_blacklist_statistics(db: AsyncSession) -> dict:
    """按黑名单维度统计有效记录数, 返回卡片所需的 key + total."""
    rows = (await db.execute(
        select(RiskBlacklist.blacklist_type, func.count(RiskBlacklist.blacklist_id))
        .where(RiskBlacklist.deleted_at.is_(None))
        .group_by(RiskBlacklist.blacklist_type)
    )).all()
    counts = {r[0]: r[1] for r in rows}
    total = sum(counts.values())
    # 对齐截图: 用户(account)/地址(ip)/手机号(phone) 为核心卡片
    return {
        "total": total,
        "by_type": counts,
        "account": counts.get("account", 0),
        "ip": counts.get("ip", 0),
        "phone": counts.get("phone", 0),
    }


async def remove_blacklist(db: AsyncSession, blacklist_id: int) -> bool:
    bl = (await db.execute(
        select(RiskBlacklist).where(RiskBlacklist.blacklist_id == blacklist_id, RiskBlacklist.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not bl:
        return False
    await record_action(db, operator="admin", action_type="REMOVE_BLACKLIST",
        target_type="blacklist", target_id=bl.blacklist_id,
        before_value={"blacklist_type": bl.blacklist_type, "blacklist_value": bl.blacklist_value, "reason": bl.reason},
        after_value=None, remark=f"移除黑名单 {bl.blacklist_type}={bl.blacklist_value}")
    bl.deleted_at = datetime.now()
    await db.commit()
    return True


# ============================================================
# 案件
# ============================================================
_ALLOWED_CASE_TRANSITIONS: dict[str, set[str]] = {
    "待审核": {"审核中", "已通过", "已拒绝", "已关闭"},
    "审核中": {"已通过", "已拒绝", "已关闭"},
    "已通过": set(),
    "已拒绝": set(),
    "已关闭": set(),
}


async def get_case_list(db, status=None, category=None, page=1, page_size=20, active_only=False) -> CaseListResponse:
    filters = []
    if status:
        filters.append(RiskCase.case_status == status)
    elif active_only:
        filters.append(RiskCase.case_status.in_(("待审核", "审核中")))
    if category:
        filters.append(RiskCase.case_category == category)

    count_stmt = select(func.count()).select_from(RiskCase)
    for f in filters:
        count_stmt = count_stmt.where(f)
    total = int((await db.execute(count_stmt)).scalar() or 0)

    paged_stmt = (
        select(RiskCase, RiskAssessment.final_score, RiskAssessment.risk_level)
        .outerjoin(RiskAssessment, RiskCase.assessment_id == RiskAssessment.assessment_id)
        .where(*filters).order_by(RiskCase.create_time.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )
    rows = (await db.execute(paged_stmt)).all()
    items = [
        CaseItem(case_id=r[0].case_id, assessment_id=r[0].assessment_id, user_id=r[0].user_id,
            case_status=r[0].case_status, case_category=r[0].case_category,
            final_score=r.final_score, risk_level=r.risk_level, create_time=r[0].create_time,
            source_id=r[0].source_id, event_type=r[0].event_type)
        for r in rows
    ]
    return CaseListResponse(items=items, total=total, page=page, page_size=page_size)


async def get_case_detail(db, case_id: str):
    case = (await db.execute(select(RiskCase).where(RiskCase.case_id == case_id))).scalar_one_or_none()
    if not case:
        return None
    assessment = (await db.execute(
        select(RiskAssessment).where(RiskAssessment.assessment_id == case.assessment_id)
    )).scalar_one_or_none()
    triggered_rules = []
    if assessment and assessment.rule_results:
        try:
            triggered_rules = [RuleHitInfo(**r) for r in json.loads(assessment.rule_results)]
        except (json.JSONDecodeError, TypeError, ValidationError):
            logger.warning("case %s 的 rule_results 解析失败", case.case_id)
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == case.user_id)
    )).scalar_one_or_none()
    user_profile = None
    if profile:
        user_profile = {
            "risk_score": profile.risk_score, "risk_level": profile.risk_level,
            "total_orders": profile.total_orders, "total_refunds": profile.total_refunds,
            "refund_rate": float(profile.refund_rate), "avg_order_amount": float(profile.avg_order_amount),
            "address_count": profile.address_count, "complaint_count": profile.complaint_count,
            "assessment_count": profile.assessment_count,
        }
    return CaseDetailResponse(
        case_id=case.case_id, assessment_id=case.assessment_id, user_id=case.user_id,
        case_status=case.case_status, case_category=case.case_category,
        risk_detail=json.loads(case.risk_detail) if case.risk_detail else None,
        reviewer=case.reviewer, review_comment=case.review_comment, review_time=case.review_time,
        create_time=case.create_time,
        final_score=assessment.final_score if assessment else None,
        risk_level=assessment.risk_level if assessment else None,
        decision=assessment.decision if assessment else None,
        triggered_rules=triggered_rules, user_profile=user_profile,
        ml_score=float(assessment.ml_score) if assessment and assessment.ml_score is not None else None,
        ml_decision=assessment.ml_decision if assessment else None,
        source_id=case.source_id, event_type=case.event_type)


async def review_case(db, case_id: str, request: CaseReviewRequest):
    case = (await db.execute(select(RiskCase).where(RiskCase.case_id == case_id))).scalar_one_or_none()
    if not case:
        return None
    current_status = case.case_status
    allowed_targets = _ALLOWED_CASE_TRANSITIONS.get(current_status, set())
    if request.decision not in allowed_targets:
        raise HTTPException(status_code=400,
            detail=f"案件状态不能从 '{current_status}' 流转到 '{request.decision}', "
                   f"合法目标: {sorted(allowed_targets) or '(终态)'}")
    case.case_status = request.decision
    case.reviewer = request.reviewer
    case.review_comment = request.review_comment
    case.review_time = datetime.now()
    await record_action(db, operator=request.reviewer, action_type="REVIEW_CASE",
        target_type="case", target_id=case.case_id,
        before_value={"case_status": current_status},
        after_value={"case_status": request.decision, "review_comment": request.review_comment or ""},
        remark=f"审核 {request.decision}" + (" + 加黑名单" if request.decision == "已拒绝" and request.add_to_blacklist else ""))
    if request.decision == "已拒绝" and request.add_to_blacklist:
        expire_time = None
        if request.blacklist_expire_hours and request.blacklist_expire_hours > 0:
            expire_time = datetime.now() + timedelta(hours=request.blacklist_expire_hours)
        await add_blacklist(db, BlacklistCreate(
            blacklist_type="account", blacklist_value=case.user_id,
            reason=f"案件审核拒绝: {case.case_id}", expire_time=expire_time))
    await db.commit()
    return await get_case_detail(db, case_id)


async def get_case_statistics(db) -> CaseStatistics:
    total = (await db.execute(select(func.count(RiskCase.case_id)))).scalar() or 0
    status_rows = (await db.execute(
        select(RiskCase.case_status, func.count(RiskCase.case_id)).group_by(RiskCase.case_status)
    )).all()
    status_map = {row[0]: row[1] for row in status_rows}
    category_rows = (await db.execute(
        select(RiskCase.case_category, func.count(RiskCase.case_id)).group_by(RiskCase.case_category)
    )).all()
    by_category = {cat: cnt for cat, cnt in category_rows if cat}
    return CaseStatistics(
        total=int(total), pending=status_map.get("待审核", 0), reviewing=status_map.get("审核中", 0),
        approved=status_map.get("已通过", 0), rejected=status_map.get("已拒绝", 0),
        closed=status_map.get("已关闭", 0), by_category=by_category)


# ============================================================
# 用户画像
# ============================================================
async def get_user_profile(db, user_id: str):
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == user_id)
    )).scalar_one_or_none()
    if not profile:
        return None
    return UserProfileResponse(
        user_id=profile.user_id, risk_score=profile.risk_score, risk_level=profile.risk_level,
        total_orders=profile.total_orders, total_refunds=profile.total_refunds,
        refund_rate=float(profile.refund_rate), avg_order_amount=float(profile.avg_order_amount),
        address_count=profile.address_count, complaint_count=profile.complaint_count,
        assessment_count=profile.assessment_count, last_assessment_time=profile.last_assessment_time,
        profile_data=json.loads(profile.profile_data) if profile.profile_data else None)


# ============================================================
# 评估历史
# ============================================================
async def list_assessments(db, decision=None, risk_level=None, event_type=None, user_id=None, page=1, page_size=20) -> AssessmentListResponse:
    a_filters = []
    if decision:
        a_filters.append(RiskAssessment.decision == decision)
    if risk_level:
        a_filters.append(RiskAssessment.risk_level == risk_level)
    if user_id:
        a_filters.append(RiskAssessment.user_id == user_id)

    count_stmt = (select(func.count()).select_from(RiskAssessment)
        .outerjoin(RiskEvent, RiskAssessment.event_id == RiskEvent.event_id))
    if event_type:
        count_stmt = count_stmt.where(RiskEvent.event_type == event_type)
    for f in a_filters:
        count_stmt = count_stmt.where(f)
    total = int((await db.execute(count_stmt)).scalar() or 0)

    paged_stmt = (select(RiskAssessment, RiskEvent.event_type)
        .outerjoin(RiskEvent, RiskAssessment.event_id == RiskEvent.event_id).where(*a_filters))
    if event_type:
        paged_stmt = paged_stmt.where(RiskEvent.event_type == event_type)
    paged_stmt = paged_stmt.order_by(RiskAssessment.create_time.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(paged_stmt)).all()
    items = [
        AssessmentItem(assessment_id=r[0].assessment_id, event_id=r[0].event_id, user_id=r[0].user_id,
            event_type=r[1] or "未知", final_score=r[0].final_score, risk_level=r[0].risk_level,
            decision=r[0].decision, rule_count=r[0].rule_count,
            ml_score=float(r[0].ml_score) if r[0].ml_score is not None else None,
            ml_decision=r[0].ml_decision, create_time=r[0].create_time)
        for r in rows
    ]
    return AssessmentListResponse(items=items, total=total, page=page, page_size=page_size)


async def get_assessment_detail(db, assessment_id: str):
    a = (await db.execute(
        select(RiskAssessment).where(RiskAssessment.assessment_id == assessment_id)
    )).scalar_one_or_none()
    if not a:
        return None
    ev = (await db.execute(select(RiskEvent).where(RiskEvent.event_id == a.event_id))).scalar_one_or_none()
    try:
        triggered = json.loads(a.rule_results) if a.rule_results else []
        triggered_rules = [RuleHitInfo(**r) for r in triggered]
    except (json.JSONDecodeError, ValidationError, TypeError):
        triggered_rules = []
    return AssessmentDetailResponse(
        assessment_id=a.assessment_id, event_id=a.event_id, user_id=a.user_id,
        event_type=ev.event_type if ev else "未知", event_source_id=ev.event_source_id if ev else "",
        final_score=a.final_score, risk_level=a.risk_level, decision=a.decision,
        rule_count=a.rule_count, triggered_rules=triggered_rules,
        ml_score=float(a.ml_score) if a.ml_score is not None else None, ml_decision=a.ml_decision,
        create_time=a.create_time, event_data=ev.event_data if ev else None)
