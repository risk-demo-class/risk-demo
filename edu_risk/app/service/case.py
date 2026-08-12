"""
案件服务 — CRUD + 5 状态机 + 超时自动关闭
状态: 待审核 / 审核中 / 已通过 / 已拒绝 / 已关闭
"""
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import RiskCase, RiskUserProfile, gen_id
from app.service.action_log import record_action

logger = logging.getLogger(__name__)

# 状态机白名单: 状态外的转换一律拒绝,防脏数据把案件改飞
_ALLOWED_CASE_TRANSITIONS = {
    "待审核": {"审核中", "已通过", "已拒绝", "已关闭"},
    "审核中": {"已通过", "已拒绝", "已关闭"},
    "已通过": set(),   # 终态
    "已拒绝": set(),
    "已关闭": set(),
}


async def list_cases(db: AsyncSession, page: int = 1, page_size: int = 20,
                     status: str | None = None, user_id: str | None = None,
                     active_only: bool = True) -> dict:
    """案件列表。active_only=True(默认)只看待审核/审核中。"""
    from sqlalchemy import func
    conds = []
    if status:
        conds.append(RiskCase.case_status == status)
    elif active_only:
        conds.append(RiskCase.case_status.in_(["待审核", "审核中"]))
    if user_id:
        conds.append(RiskCase.user_id == user_id)
    # 真实总数(count),供前端分页
    total = (await db.execute(
        select(func.count()).select_from(RiskCase).where(*conds))).scalar() or 0
    stmt = (select(RiskCase).where(*conds)
            .order_by(RiskCase.create_time.desc())
            .offset((page - 1) * page_size).limit(page_size))
    r = await db.execute(stmt)
    cases = list(r.scalars().all())
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_case_dict(c) for c in cases]}


async def get_case(db: AsyncSession, case_id: str) -> RiskCase:
    r = await db.execute(select(RiskCase).where(RiskCase.case_id == case_id))
    case = r.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail=f"案件不存在: {case_id}")
    return case


async def claim_case(db: AsyncSession, case_id: str, operator: str) -> RiskCase:
    """领取案件: 待审核 → 审核中。"""
    case = await get_case(db, case_id)
    _assert_transition(case.case_status, "审核中")
    before = case.case_status
    case.case_status = "审核中"
    case.assignee = operator
    await record_action(db, operator, "case_claim", before={"status": before},
                        after={"status": "审核中", "assignee": operator})
    await db.commit()
    return case


async def review_case(db: AsyncSession, case_id: str, action: str,
                      operator: str, comment: str = "") -> RiskCase:
    """审核案件: 审核中 → 已通过 / 已拒绝。"""
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action 必须为 approve/reject")
    case = await get_case(db, case_id)
    target = "已通过" if action == "approve" else "已拒绝"
    _assert_transition(case.case_status, target)
    before = case.case_status
    case.case_status = target
    case.reviewer = operator
    case.review_comment = comment
    case.close_time = datetime.now()
    await record_action(db, operator, "case_review",
                        before={"status": before}, after={"status": target, "comment": comment})
    await db.commit()
    return case


async def close_case(db: AsyncSession, case_id: str, operator: str,
                     comment: str = "") -> RiskCase:
    """关闭案件: 待审核/审核中 → 已关闭。"""
    case = await get_case(db, case_id)
    _assert_transition(case.case_status, "已关闭")
    before = case.case_status
    case.case_status = "已关闭"
    case.reviewer = operator
    case.review_comment = comment or "手动关闭"
    case.close_time = datetime.now()
    await record_action(db, operator, "case_close", before={"status": before},
                        after={"status": "已关闭"})
    await db.commit()
    return case


async def auto_close_timeout_cases(db: AsyncSession, hours: int | None = None) -> int:
    """
    超时自动关闭: 待审核案件超过 N 小时未处理 → 系统自动关闭 + 审计。
    返回关闭数量。hours<=0 = 关闭此功能。
    """
    hours = hours if hours is not None else settings.CASE_TIMEOUT_HOURS
    if hours <= 0:
        return 0
    threshold = datetime.now() - timedelta(hours=hours)
    r = await db.execute(select(RiskCase).where(
        RiskCase.case_status == "待审核",
        RiskCase.create_time < threshold))
    cases = list(r.scalars().all())
    closed = 0
    for c in cases:
        before = c.case_status
        c.case_status = "已关闭"
        c.reviewer = "system"
        c.review_comment = f"系统自动关闭: 超过 {hours} 小时未处理"
        c.close_time = datetime.now()
        await record_action(db, "system", "case_auto_close",
                            before={"status": before}, after={"status": "已关闭"})
        closed += 1
    if closed:
        await db.commit()
    return closed


def _assert_transition(current: str, target: str):
    if target not in _ALLOWED_CASE_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=400,
            detail=f"非法状态转换: {current} → {target}")


def _case_dict(c: RiskCase) -> dict:
    return {
        "case_id": c.case_id,
        "user_id": c.user_id,
        "source_id": c.source_id,
        "event_type": c.event_type,
        "case_status": c.case_status,
        "assignee": c.assignee,
        "reviewer": c.reviewer,
        "review_comment": c.review_comment,
        "create_time": c.create_time.isoformat() if c.create_time else None,
        "update_time": c.update_time.isoformat() if c.update_time else None,
    }
