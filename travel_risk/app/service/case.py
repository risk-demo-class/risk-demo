"""
案件服务: 黑名单检查 / 案件状态机 / 自动关案 / 通用分页
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import RiskBlacklist, RiskCase

logger = logging.getLogger(__name__)


# ============================================================
# 黑名单
# ============================================================

async def check_blacklist(
    db: AsyncSession,
    blacklist_type: str,
    value: str,
) -> bool:
    """撞黑检查: 未软删 + 未过期 (expire_time IS NULL 或 > now)."""
    if not value:
        return False
    stmt = select(RiskBlacklist).where(
        RiskBlacklist.blacklist_type == blacklist_type,
        RiskBlacklist.blacklist_value == value,
        RiskBlacklist.deleted_at.is_(None),
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        return False
    if row.expire_time and row.expire_time <= datetime.now():
        return False
    return True


# ============================================================
# 案件状态机
# ============================================================

CASE_OPEN_STATUSES = ("待审核", "审核中")


def validate_case_transition(current: str, target: str) -> None:
    """案件状态机合法性校验:
      待审核 → 审核中/已通过/已拒绝/已关闭
      审核中 → 已通过/已拒绝/已关闭
      终态 (已通过/已拒绝/已关闭) 不可再变更
    """
    if current in ("已通过", "已拒绝", "已关闭"):
        raise ValueError(f"案件已处于终态 {current}, 不能变更为 {target}")
    if current == "待审核" and target in ("待审核",):
        raise ValueError("不能从 待审核 变更为 待审核")
    allowed = {
        "待审核": {"审核中", "已通过", "已拒绝", "已关闭"},
        "审核中": {"已通过", "已拒绝", "已关闭"},
    }
    if target not in allowed.get(current, set()):
        raise ValueError(f"非法状态流转: {current} → {target}")


async def auto_close_timeout_cases(db: AsyncSession) -> int:
    """自动关闭超时未处理的"待审核"案件 (配置 CASE_TIMEOUT_HOURS)."""
    if settings.CASE_TIMEOUT_HOURS <= 0:
        return 0
    deadline = datetime.now() - timedelta(hours=settings.CASE_TIMEOUT_HOURS)
    cases = (await db.execute(
        select(RiskCase).where(
            RiskCase.case_status == "待审核",
            RiskCase.create_time < deadline,
        ).limit(200)
    )).scalars().all()
    for case in cases:
        case.case_status = "已关闭"
        case.reviewer = "system"
        case.review_comment = f"超过 {settings.CASE_TIMEOUT_HOURS} 小时未审核, 系统自动关闭"
        case.review_time = datetime.now()
    await db.commit()
    if cases:
        logger.info("自动关闭超时案件 %d 个", len(cases))
    return len(cases)


# ============================================================
# 通用分页
# ============================================================

async def paginate(
    db: AsyncSession,
    stmt,
    count_stmt,
    page: int = 1,
    page_size: int = 10,
):
    """通用分页: 返回 (items, total)."""
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total = int((await db.execute(count_stmt)).scalar() or 0)
    rows = (await db.execute(
        stmt.offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return rows, total, page, page_size
