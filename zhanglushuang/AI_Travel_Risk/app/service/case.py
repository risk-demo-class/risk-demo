"""
案件管理 / 黑名单 / 用户画像服务.

包含:
- 黑名单增删查与前置拦截
- 案件状态机
- 超时自动关闭
- 用户风险画像查询
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    RiskAssessment,
    RiskBlacklist,
    RiskCase,
    RiskEvent,
    RiskUserProfile,
)
from app.schemas import (
    BlacklistCreate,
    BlacklistResponse,
    CaseDetailResponse,
    CaseItem,
    CaseReviewRequest,
    CaseStatistics,
    UserProfileResponse,
)
from app.service.action_log import record_action

logger = logging.getLogger(__name__)

_ALLOWED_CASE_TRANSITIONS = {
    "待审核": {"审核中", "已通过", "已拒绝", "已关闭"},
    "审核中": {"已通过", "已拒绝", "已关闭"},
    "已通过": set(),
    "已拒绝": set(),
    "已关闭": set(),
}


async def check_blacklist(
    db: AsyncSession,
    blacklist_type: str,
    value: str,
) -> bool:
    """检查 (type, value) 是否命中有效黑名单."""
    if not value:
        return False
    try:
        now = datetime.now()
        stmt = (
            select(func.count())
            .select_from(RiskBlacklist)
            .where(
                RiskBlacklist.blacklist_type == blacklist_type,
                RiskBlacklist.blacklist_value == value,
                RiskBlacklist.deleted_at.is_(None),
                or_(
                    RiskBlacklist.expire_time.is_(None),
                    RiskBlacklist.expire_time > now,
                ),
            )
            .limit(1)
        )
        return bool((await db.execute(stmt)).scalar())
    except Exception:
        logger.exception("黑名单检查失败: type=%s value=%s", blacklist_type, value)
        raise


async def add_blacklist(
    db: AsyncSession,
    request: BlacklistCreate,
    operator: str = "admin",
) -> BlacklistResponse:
    """新增黑名单, 重复有效记录直接返回已有记录."""
    try:
        existing = (
            await db.execute(
                select(RiskBlacklist)
                .where(
                    RiskBlacklist.blacklist_type == request.blacklist_type,
                    RiskBlacklist.blacklist_value == request.blacklist_value,
                    RiskBlacklist.deleted_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing:
            return BlacklistResponse(
                blacklist_id=existing.blacklist_id,
                blacklist_type=existing.blacklist_type,
                blacklist_value=existing.blacklist_value,
                reason=existing.reason,
                expire_time=existing.expire_time,
                create_time=existing.create_time,
            )

        expire_time = None
        if request.expire_hours:
            expire_time = datetime.now() + timedelta(hours=request.expire_hours)

        row = RiskBlacklist(
            blacklist_type=request.blacklist_type,
            blacklist_value=request.blacklist_value,
            reason=request.reason,
            expire_time=expire_time,
        )
        db.add(row)
        await db.flush()
        await record_action(
            db,
            operator=operator,
            action_type="ADD_BLACKLIST",
            target_type="blacklist",
            target_id=str(row.blacklist_id),
            after_value={
                "blacklist_type": row.blacklist_type,
                "blacklist_value": row.blacklist_value,
                "reason": row.reason,
            },
        )
        logger.info(
            "新增黑名单: type=%s value=%s expire=%s",
            row.blacklist_type,
            row.blacklist_value,
            expire_time,
        )
        return BlacklistResponse(
            blacklist_id=row.blacklist_id,
            blacklist_type=row.blacklist_type,
            blacklist_value=row.blacklist_value,
            reason=row.reason,
            expire_time=row.expire_time,
            create_time=row.create_time,
        )
    except Exception:
        logger.exception("新增黑名单失败: %s", request.model_dump())
        raise


async def remove_blacklist(
    db: AsyncSession,
    blacklist_id: int,
    operator: str = "admin",
) -> bool:
    """软删除黑名单."""
    try:
        row = (
            await db.execute(
                select(RiskBlacklist).where(RiskBlacklist.blacklist_id == blacklist_id).limit(1)
            )
        ).scalar_one_or_none()
        if not row or row.deleted_at is not None:
            return False
        row.deleted_at = datetime.now()
        await record_action(
            db,
            operator=operator,
            action_type="REMOVE_BLACKLIST",
            target_type="blacklist",
            target_id=str(blacklist_id),
            before_value={"blacklist_type": row.blacklist_type, "blacklist_value": row.blacklist_value},
        )
        logger.info("移除黑名单: id=%s type=%s value=%s", blacklist_id, row.blacklist_type, row.blacklist_value)
        return True
    except Exception:
        logger.exception("移除黑名单失败: id=%s", blacklist_id)
        raise


async def get_blacklist(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    blacklist_type: Optional[str] = None,
) -> tuple[int, list[BlacklistResponse]]:
    """分页查询黑名单."""
    try:
        filters = [RiskBlacklist.deleted_at.is_(None)]
        if blacklist_type:
            filters.append(RiskBlacklist.blacklist_type == blacklist_type)

        total_stmt = select(func.count()).select_from(RiskBlacklist).where(*filters)
        total = int((await db.execute(total_stmt)).scalar() or 0)

        stmt = (
            select(RiskBlacklist)
            .where(*filters)
            .order_by(RiskBlacklist.create_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await db.execute(stmt)).scalars().all())
        items = [
            BlacklistResponse(
                blacklist_id=r.blacklist_id,
                blacklist_type=r.blacklist_type,
                blacklist_value=r.blacklist_value,
                reason=r.reason,
                expire_time=r.expire_time,
                create_time=r.create_time,
            )
            for r in rows
        ]
        return total, items
    except Exception:
        logger.exception("查询黑名单失败")
        raise


async def list_cases(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    active_only: bool = False,
) -> tuple[int, list[CaseItem]]:
    """分页查询案件."""
    try:
        filters = []
        if status:
            filters.append(RiskCase.case_status == status)
        if active_only:
            filters.append(RiskCase.case_status.in_(["待审核", "审核中"]))

        total_stmt = select(func.count()).select_from(RiskCase).where(*filters)
        total = int((await db.execute(total_stmt)).scalar() or 0)

        stmt = (
            select(RiskCase)
            .where(*filters)
            .order_by(RiskCase.create_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await db.execute(stmt)).scalars().all())
        items = [
            CaseItem(
                case_id=r.case_id,
                assessment_id=r.assessment_id,
                user_id=r.user_id,
                case_status=r.case_status,
                case_category=r.case_category,
                source_id=r.source_id,
                event_type=r.event_type,
                create_time=r.create_time,
            )
            for r in rows
        ]
        return total, items
    except Exception:
        logger.exception("查询案件列表失败")
        raise


async def get_case_detail(
    db: AsyncSession,
    case_id: str,
) -> CaseDetailResponse:
    """查询案件详情."""
    try:
        row = (
            await db.execute(select(RiskCase).where(RiskCase.case_id == case_id).limit(1))
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail=f"案件不存在: {case_id}")
        return CaseDetailResponse(
            case_id=row.case_id,
            assessment_id=row.assessment_id,
            user_id=row.user_id,
            case_status=row.case_status,
            case_category=row.case_category,
            risk_detail=row.risk_detail,
            source_id=row.source_id,
            event_type=row.event_type,
            reviewer=row.reviewer,
            review_comment=row.review_comment,
            review_time=row.review_time,
            create_time=row.create_time,
            update_time=row.update_time,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询案件详情失败: case_id=%s", case_id)
        raise


async def review_case(
    db: AsyncSession,
    case_id: str,
    request: CaseReviewRequest,
) -> CaseDetailResponse:
    """案件审核, 使用状态机白名单."""
    try:
        row = (
            await db.execute(select(RiskCase).where(RiskCase.case_id == case_id).limit(1))
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail=f"案件不存在: {case_id}")

        target_status = "已通过" if request.decision == "通过" else "已拒绝"
        allowed = _ALLOWED_CASE_TRANSITIONS.get(row.case_status, set())
        if target_status not in allowed:
            logger.warning("非法状态流转: %s -> %s", row.case_status, target_status)
            raise HTTPException(
                status_code=400,
                detail=f"案件状态 {row.case_status} 不允许流转到 {target_status}",
            )

        before = {"case_status": row.case_status}
        row.case_status = target_status
        row.reviewer = request.reviewer or "admin"
        row.review_comment = request.comment
        row.review_time = datetime.now()
        await record_action(
            db,
            operator=row.reviewer,
            action_type="REVIEW_CASE",
            target_type="case",
            target_id=case_id,
            before_value=before,
            after_value={"case_status": row.case_status},
        )
        return await get_case_detail(db, case_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("案件审核失败: case_id=%s", case_id)
        raise


async def auto_close_timeout_cases(
    db: AsyncSession,
    hours: Optional[int] = None,
) -> list[str]:
    """待审核案件超过 N 小时自动关闭."""
    try:
        timeout_hours = hours if hours is not None else 24
        if timeout_hours <= 0:
            return []
        threshold = datetime.now() - timedelta(hours=timeout_hours)
        stmt = select(RiskCase).where(
            RiskCase.case_status == "待审核",
            RiskCase.create_time < threshold,
        )
        rows = list((await db.execute(stmt)).scalars().all())
        closed: list[str] = []
        for row in rows:
            before = {"case_status": row.case_status}
            row.case_status = "已关闭"
            row.reviewer = "system"
            row.review_comment = f"系统自动关闭: 超过 {timeout_hours} 小时未处理"
            row.review_time = datetime.now()
            await record_action(
                db,
                operator="system",
                action_type="AUTO_CLOSE_CASE",
                target_type="case",
                target_id=row.case_id,
                before_value=before,
                after_value={"case_status": "已关闭"},
            )
            closed.append(row.case_id)
        if closed:
            logger.info("自动关闭案件: %s", closed)
        return closed
    except Exception:
        logger.exception("自动关闭案件失败")
        raise


async def get_case_statistics(db: AsyncSession) -> CaseStatistics:
    """案件统计."""
    try:
        rows = (
            await db.execute(
                select(RiskCase.case_status, func.count()).group_by(RiskCase.case_status)
            )
        ).all()
        counts = {status: int(cnt) for status, cnt in rows}
        return CaseStatistics(
            total=sum(counts.values()),
            pending=counts.get("待审核", 0),
            reviewing=counts.get("审核中", 0),
            approved=counts.get("已通过", 0),
            rejected=counts.get("已拒绝", 0),
            closed=counts.get("已关闭", 0),
        )
    except Exception:
        logger.exception("查询案件统计失败")
        raise


async def get_user_profile(db: AsyncSession, user_id: str) -> UserProfileResponse:
    """查询用户风险画像."""
    try:
        row = (
            await db.execute(
                select(RiskUserProfile).where(RiskUserProfile.user_id == user_id).limit(1)
            )
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail=f"用户画像不存在: {user_id}")
        return UserProfileResponse(
            user_id=row.user_id,
            risk_score=row.risk_score,
            risk_level=row.risk_level,
            total_orders=row.total_orders,
            total_refunds=row.total_refunds,
            refund_rate=float(row.refund_rate or 0),
            avg_order_amount=float(row.avg_order_amount or 0),
            address_count=row.address_count,
            complaint_count=row.complaint_count,
            assessment_count=row.assessment_count,
            last_assessment_time=row.last_assessment_time,
            profile_data=row.profile_data,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询用户画像失败: user_id=%s", user_id)
        raise


async def list_assessments(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    decision: Optional[str] = None,
    risk_level: Optional[str] = None,
    event_type: Optional[str] = None,
) -> tuple[int, list[dict]]:
    """分页查询评估历史, JOIN risk_event 拿事件类型."""
    try:
        filters = []
        if decision:
            filters.append(RiskAssessment.decision == decision)
        if risk_level:
            filters.append(RiskAssessment.risk_level == risk_level)

        total_stmt = select(func.count()).select_from(RiskAssessment).where(*filters)
        total = int((await db.execute(total_stmt)).scalar() or 0)

        stmt = (
            select(RiskAssessment, RiskEvent.event_type)
            .outerjoin(RiskEvent, RiskAssessment.event_id == RiskEvent.event_id)
            .where(*filters)
            .order_by(RiskAssessment.create_time.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await db.execute(stmt)).all())
        items = []
        for r, ev_type in rows:
            if event_type and ev_type != event_type:
                continue
            items.append(
                {
                    "assessment_id": r.assessment_id,
                    "event_id": r.event_id,
                    "user_id": r.user_id,
                    "event_type": ev_type or "未知",
                    "final_score": r.final_score,
                    "risk_level": r.risk_level,
                    "decision": r.decision,
                    "rule_count": r.rule_count,
                    "ml_score": float(r.ml_score) if r.ml_score is not None else None,
                    "create_time": r.create_time,
                }
            )
        return total, items
    except Exception:
        logger.exception("查询评估历史失败")
        raise


async def get_assessment_detail(
    db: AsyncSession,
    assessment_id: str,
) -> dict:
    """查询评估详情."""
    try:
        row = (
            await db.execute(
                select(RiskAssessment).where(RiskAssessment.assessment_id == assessment_id).limit(1)
            )
        ).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail=f"评估不存在: {assessment_id}")
        ev_type = (
            await db.execute(
                select(RiskEvent.event_type).where(RiskEvent.event_id == row.event_id).limit(1)
            )
        ).scalar_one_or_none()
        return {
            "assessment_id": row.assessment_id,
            "event_id": row.event_id,
            "user_id": row.user_id,
            "event_type": ev_type or "未知",
            "final_score": row.final_score,
            "risk_level": row.risk_level,
            "decision": row.decision,
            "rule_count": row.rule_count,
            "rule_results": row.rule_results,
            "ml_score": float(row.ml_score) if row.ml_score is not None else None,
            "ml_decision": row.ml_decision,
            "create_time": row.create_time,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("查询评估详情失败: assessment_id=%s", assessment_id)
        raise
