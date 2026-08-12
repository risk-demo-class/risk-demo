"""
黑名单服务: check / add / remove / list

参照 ai_risk/app/service/case.py 的黑名单部分, 适配电信类型 (号卡/客户/设备/渠道).
软删模式: remove 只置 deleted_at, 不物理删 (审计可追溯).
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_risk import TelecomRiskBlacklist
from app.schemas import BlacklistCreate, BlacklistListResponse, BlacklistResponse

logger = logging.getLogger(__name__)


async def check_blacklist(
    db: AsyncSession, blacklist_type: str, blacklist_value: str,
) -> bool:
    """检查是否在黑名单 (未软删 + 未过期). 反诈法第 21 条失信名单."""
    row = (await db.execute(
        select(TelecomRiskBlacklist.blacklist_id, TelecomRiskBlacklist.expire_time).where(
            TelecomRiskBlacklist.blacklist_type == blacklist_type,
            TelecomRiskBlacklist.blacklist_value == blacklist_value,
            TelecomRiskBlacklist.deleted_at.is_(None),
        ).limit(1)
    )).first()
    if not row:
        return False
    # 过期黑名单不算 (expire_time < now → 视为失效)
    if row.expire_time and row.expire_time < datetime.now():
        return False
    return True


async def add_blacklist(db: AsyncSession, data: BlacklistCreate) -> BlacklistResponse:
    """添加黑名单. 已存在且未删 → 更新 reason/expire; 否则插入."""
    existing = (await db.execute(
        select(TelecomRiskBlacklist).where(
            TelecomRiskBlacklist.blacklist_type == data.blacklist_type,
            TelecomRiskBlacklist.blacklist_value == data.blacklist_value,
            TelecomRiskBlacklist.deleted_at.is_(None),
        ).limit(1)
    )).scalar_one_or_none()

    if existing:
        existing.reason = data.reason
        existing.expire_time = data.expire_time
        existing.deleted_at = None  # 复活已软删的记录
        await db.flush()
        bl = existing
    else:
        bl = TelecomRiskBlacklist(
            blacklist_type=data.blacklist_type,
            blacklist_value=data.blacklist_value,
            reason=data.reason,
            expire_time=data.expire_time,
        )
        db.add(bl)
        await db.flush()
    return BlacklistResponse(
        blacklist_id=bl.blacklist_id,
        blacklist_type=bl.blacklist_type,
        blacklist_value=bl.blacklist_value,
        reason=bl.reason,
        expire_time=bl.expire_time,
        create_time=bl.create_time,
    )


async def remove_blacklist(db: AsyncSession, blacklist_id: int) -> bool:
    """软删黑名单. 返回 True=删成功, False=不存在."""
    bl = (await db.execute(
        select(TelecomRiskBlacklist).where(
            TelecomRiskBlacklist.blacklist_id == blacklist_id,
            TelecomRiskBlacklist.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not bl:
        return False
    bl.deleted_at = datetime.now()
    await db.flush()
    return True


async def get_blacklist(
    db: AsyncSession, page: int = 1, page_size: int = 20,
) -> BlacklistListResponse:
    """分页查询黑名单 (未软删)."""
    offset = (page - 1) * page_size
    total = int((await db.execute(
        select(func.count()).select_from(TelecomRiskBlacklist)
        .where(TelecomRiskBlacklist.deleted_at.is_(None))
    )).scalar() or 0)
    rows = (await db.execute(
        select(TelecomRiskBlacklist).where(TelecomRiskBlacklist.deleted_at.is_(None))
        .order_by(TelecomRiskBlacklist.create_time.desc())
        .offset(offset).limit(page_size)
    )).scalars().all()
    items = [
        BlacklistResponse(
            blacklist_id=r.blacklist_id, blacklist_type=r.blacklist_type,
            blacklist_value=r.blacklist_value, reason=r.reason,
            expire_time=r.expire_time, create_time=r.create_time,
        ) for r in rows
    ]
    return BlacklistListResponse(items=items, total=total, page=page, page_size=page_size)
