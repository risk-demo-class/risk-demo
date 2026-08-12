"""
案件管理模块: 案件查询 / 详情 / 审核 / 统计, 黑名单管理, 经销商画像查询.

Commit 策略:
  *atomic 后缀: 内部 self-commit, 调用方不要再 commit
  *tx 后缀:    故意不 commit, 留给调用方合并事务
"""
import json
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BlacklistExtra,
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    RiskEvent,
    RiskUserProfile,
)
from app.schemas import (
    AssessmentDetailResponse,
    AssessmentItem,
    AssessmentListResponse,
    BlacklistCreate,
    BlacklistResponse,
    CaseDetailResponse,
    CaseItem,
    CaseListResponse,
    CaseReviewRequest,
    CaseStatistics,
    RuleHitInfo,
    UserProfileResponse,
)
from app.service.action_log import record_action

logger = logging.getLogger(__name__)


# ============================================================
# 黑名单
# ============================================================

async def check_blacklist(db: AsyncSession, blacklist_type: str, value: str) -> bool:
    """风控黑名单 risk_blacklist 撞黑检查 (未软删 + 未过期)."""
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


async def check_blacklist_extra(db: AsyncSession, blacklist_type: str, value: str) -> bool:
    """业务黑名单 blacklist_extra 撞黑检查 (未过期)."""
    row = (await db.execute(
        select(BlacklistExtra.expire_at).where(
            BlacklistExtra.type == blacklist_type,
            BlacklistExtra.value == value,
        ).limit(1)
    )).first()
    if not row:
        return False
    if row.expire_at and row.expire_at < datetime.now():
        return False
    return True


async def add_blacklist(db: AsyncSession, request: BlacklistCreate) -> BlacklistResponse:
    """添加风控黑名单.

    存在性判断放宽到"含软删": 软删过的 (type, value) 唯一键仍占用,
    直接 INSERT 会撞 idx_blacklist_type_value (1062). 所以:
      - 未删记录 → 更新 reason/expire_time
      - 已删记录 → 复活 (清 deleted_at) + 更新
    """
    existing = (await db.execute(
        select(RiskBlacklist).where(
            RiskBlacklist.blacklist_type == request.blacklist_type,
            RiskBlacklist.blacklist_value == request.blacklist_value,
        )
    )).scalar_one_or_none()

    if existing:
        before_value = {
            "reason": existing.reason,
            "expire_time": str(existing.expire_time) if existing.expire_time else None,
        }
        existing.reason = request.reason
        existing.expire_time = request.expire_time
        existing.deleted_at = None  # 复活软删记录
        await record_action(
            db, operator="admin", action_type="ADD_BLACKLIST",
            target_type="blacklist", target_id=existing.blacklist_id,
            before_value=before_value,
            after_value={"reason": request.reason, "expire_time": str(request.expire_time) if request.expire_time else None},
            remark=f"更新/复活黑名单 {request.blacklist_type}={request.blacklist_value}",
        )
        await db.commit()
        return BlacklistResponse(
            blacklist_id=existing.blacklist_id,
            blacklist_type=existing.blacklist_type,
            blacklist_value=existing.blacklist_value,
            reason=existing.reason,
            expire_time=existing.expire_time,
            create_time=existing.create_time,
        )

    bl = RiskBlacklist(
        blacklist_type=request.blacklist_type,
        blacklist_value=request.blacklist_value,
        reason=request.reason,
        expire_time=request.expire_time,
    )
    db.add(bl)
    await record_action(
        db, operator="admin", action_type="ADD_BLACKLIST",
        target_type="blacklist", target_id=bl.blacklist_value,
        after_value={"blacklist_type": request.blacklist_type,
                     "blacklist_value": request.blacklist_value,
                     "reason": request.reason},
        remark=f"新增黑名单 {request.blacklist_type}={request.blacklist_value}",
    )
    await db.commit()
    return BlacklistResponse(
        blacklist_id=bl.blacklist_id,
        blacklist_type=bl.blacklist_type,
        blacklist_value=bl.blacklist_value,
        reason=bl.reason,
        expire_time=bl.expire_time,
        create_time=bl.create_time,
    )


async def list_blacklists_tx(
    db: AsyncSession, page: int = 1, page_size: int = 20,
) -> list[RiskBlacklist]:
    """列出未软删黑名单 (不 commit)."""
    stmt = (
        select(RiskBlacklist)
        .where(RiskBlacklist.deleted_at.is_(None))
        .order_by(RiskBlacklist.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await db.execute(stmt)).scalars().all())


async def count_blacklists_tx(db: AsyncSession) -> int:
    stmt = select(func.count()).select_from(RiskBlacklist).where(
        RiskBlacklist.deleted_at.is_(None)
    )
    return int((await db.execute(stmt)).scalar() or 0)


async def remove_blacklist_atomic(db: AsyncSession, blacklist_id: int) -> None:
    """软删黑名单 (P3-M9: 设 deleted_at)."""
    bl = (await db.execute(
        select(RiskBlacklist).where(RiskBlacklist.blacklist_id == blacklist_id)
    )).scalar_one_or_none()
    if not bl:
        raise HTTPException(status_code=404, detail="黑名单记录不存在")
    before_value = {"reason": bl.reason}
    bl.deleted_at = datetime.now()
    await record_action(
        db, operator="admin", action_type="REMOVE_BLACKLIST",
        target_type="blacklist", target_id=bl.blacklist_id,
        before_value=before_value, after_value=None,
        remark=f"删除黑名单 {bl.blacklist_type}={bl.blacklist_value}",
    )
    await db.commit()


# ============================================================
# 案件
# ============================================================

async def list_cases_tx(
    db: AsyncSession,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> list[RiskCase]:
    """案件分页查询 (不 commit)."""
    stmt = select(RiskCase)
    if status:
        stmt = stmt.where(RiskCase.case_status == status)
    stmt = (
        stmt.order_by(RiskCase.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await db.execute(stmt)).scalars().all())


async def count_cases_tx(db: AsyncSession, status: str | None = None) -> int:
    stmt = select(func.count()).select_from(RiskCase)
    if status:
        stmt = stmt.where(RiskCase.case_status == status)
    return int((await db.execute(stmt)).scalar() or 0)


async def get_case_detail_tx(db: AsyncSession, case_id: str) -> CaseDetailResponse:
    """案件详情 (含评估信息 + 命中规则 + 用户画像)."""
    case = (await db.execute(
        select(RiskCase).where(RiskCase.case_id == case_id)
    )).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    # 关联评估
    assessment = (await db.execute(
        select(RiskAssessment).where(RiskAssessment.assessment_id == case.assessment_id)
    )).scalar_one_or_none()

    # 用户画像
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == case.user_id)
    )).scalar_one_or_none()

    # 解析 risk_detail JSON
    try:
        risk_detail = json.loads(case.risk_detail) if case.risk_detail else None
    except (json.JSONDecodeError, TypeError):
        risk_detail = None

    triggered_rules = []
    final_score = None
    risk_level = None
    decision = None
    ml_score = None
    ml_decision = None
    if assessment:
        final_score = assessment.final_score
        risk_level = assessment.risk_level
        decision = assessment.decision
        ml_score = float(assessment.ml_score) if assessment.ml_score is not None else None
        ml_decision = assessment.ml_decision
        try:
            raw = json.loads(assessment.rule_results) if assessment.rule_results else []
            triggered_rules = [RuleHitInfo(**r) for r in raw]
        except (json.JSONDecodeError, TypeError):
            triggered_rules = []

    return CaseDetailResponse(
        case_id=case.case_id,
        assessment_id=case.assessment_id,
        user_id=case.user_id,
        case_status=case.case_status,
        case_category=case.case_category,
        risk_detail=risk_detail,
        reviewer=case.reviewer,
        review_comment=case.review_comment,
        review_time=case.review_time,
        create_time=case.create_time,
        final_score=final_score,
        risk_level=risk_level,
        decision=decision,
        triggered_rules=triggered_rules,
        user_profile=profile.model_dump() if profile else None,
        ml_score=ml_score,
        ml_decision=ml_decision,
        source_id=case.source_id,
        event_type=case.event_type,
    )


async def review_case_atomic(
    db: AsyncSession, case_id: str, request: CaseReviewRequest,
) -> CaseDetailResponse:
    """审核案件 (通过/拒绝/关闭), 可选加入黑名单."""
    case = (await db.execute(
        select(RiskCase).where(RiskCase.case_id == case_id)
    )).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")

    before_value = {"case_status": case.case_status}
    case.case_status = request.decision
    case.reviewer = request.reviewer
    case.review_comment = request.review_comment
    case.review_time = datetime.now()

    # 加入黑名单 (审核拒绝时常用)
    if request.add_to_blacklist:
        expire_time = None
        if request.blacklist_expire_hours:
            expire_time = datetime.now() + timedelta(hours=request.blacklist_expire_hours)
        bl = RiskBlacklist(
            blacklist_type="经销商ID",
            blacklist_value=case.user_id,
            reason=f"案件 {case_id} 审核后加入黑名单: {request.review_comment or ''}",
            expire_time=expire_time,
        )
        db.add(bl)
        # 也同步进业务黑名单 (业务系统也能看到)
        db.add(BlacklistExtra(
            entry_id=f"be_{case_id}",
            type="经销商ID",
            value=case.user_id,
            reason=f"案件 {case_id} 审核后加入黑名单",
            expire_at=expire_time,
        ))

    await record_action(
        db, operator=request.reviewer, action_type="REVIEW_CASE",
        target_type="case", target_id=case.case_id,
        before_value=before_value,
        after_value={"case_status": request.decision,
                     "review_comment": request.review_comment,
                     "add_to_blacklist": request.add_to_blacklist},
        remark=f"审核案件 {case_id} → {request.decision}",
    )
    await db.commit()

    return await get_case_detail_tx(db, case_id)


async def get_case_statistics_tx(db: AsyncSession) -> CaseStatistics:
    """案件统计: 总数 + 各状态数 + 分类分布."""
    stats = CaseStatistics()
    rows = (await db.execute(
        select(RiskCase.case_status, func.count()).group_by(RiskCase.case_status)
    )).all()
    for status, cnt in rows:
        cnt = int(cnt)
        stats.total += cnt
        if status == "待审核":
            stats.pending = cnt
        elif status == "审核中":
            stats.reviewing = cnt
        elif status == "已通过":
            stats.approved = cnt
        elif status == "已拒绝":
            stats.rejected = cnt
        elif status == "已关闭":
            stats.closed = cnt

    cat_rows = (await db.execute(
        select(RiskCase.case_category, func.count()).group_by(RiskCase.case_category)
    )).all()
    stats.by_category = {cat: int(cnt) for cat, cnt in cat_rows}
    return stats


# ============================================================
# 评估历史
# ============================================================

async def list_assessments_tx(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> list[RiskAssessment]:
    stmt = (
        select(RiskAssessment)
        .order_by(RiskAssessment.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await db.execute(stmt)).scalars().all())


async def count_assessments_tx(db: AsyncSession) -> int:
    return int((await db.execute(
        select(func.count()).select_from(RiskAssessment)
    )).scalar() or 0)


async def get_assessment_detail_tx(db: AsyncSession, assessment_id: str) -> AssessmentDetailResponse:
    """评估详情 (含命中的规则 + 关联事件信息)."""
    assessment = (await db.execute(
        select(RiskAssessment).where(RiskAssessment.assessment_id == assessment_id)
    )).scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")

    event = (await db.execute(
        select(RiskEvent).where(RiskEvent.event_id == assessment.event_id)
    )).scalar_one_or_none()

    try:
        raw = json.loads(assessment.rule_results) if assessment.rule_results else []
        triggered_rules = [RuleHitInfo(**r) for r in raw]
    except (json.JSONDecodeError, TypeError):
        triggered_rules = []

    return AssessmentDetailResponse(
        assessment_id=assessment.assessment_id,
        event_id=assessment.event_id,
        user_id=assessment.user_id,
        event_type=event.event_type if event else "",
        event_source_id=event.event_source_id if event else "",
        final_score=assessment.final_score,
        risk_level=assessment.risk_level,
        decision=assessment.decision,
        rule_count=assessment.rule_count,
        triggered_rules=triggered_rules,
        ml_score=float(assessment.ml_score) if assessment.ml_score is not None else None,
        ml_decision=assessment.ml_decision,
        create_time=assessment.create_time,
        event_data=event.event_data if event else None,
    )


# ============================================================
# 经销商风险画像
# ============================================================

async def get_profile_tx(db: AsyncSession, user_id: str) -> UserProfileResponse:
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == user_id)
    )).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="用户画像不存在 (该用户还没做过风控评估)")
    return UserProfileResponse(
        user_id=profile.user_id,
        risk_score=profile.risk_score,
        risk_level=profile.risk_level,
        total_orders=profile.total_orders,
        total_amount=float(profile.total_amount or 0),
        avg_order_amount=float(profile.avg_order_amount or 0),
        warranty_count=profile.warranty_count,
        repair_count=profile.repair_count,
        contract_expired=profile.contract_expired,
        assessment_count=profile.assessment_count,
        last_assessment_time=profile.last_assessment_time,
        profile_data=profile.profile_data,
    )
