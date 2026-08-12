"""
银行风控系统 - 黑名单管理 API
============================
GET    /api/blacklist        — 分页查询黑名单 (支持类型筛选)
POST   /api/blacklist        — 添加黑名单条目
DELETE /api/blacklist/{id}   — 移除黑名单条目

黑名单类型: IDCARD(身份证)/BANKCARD(银行卡号)/DEVICE(设备ID)/IP(IP地址).
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import BlacklistExtra
from app.schemas import (
    BlacklistCreateRequest,
    BlacklistEntryResponse,
    BlacklistListResponse,
)

blacklist_router = APIRouter(prefix="/api/blacklist", tags=["黑名单"])

# 类型映射: 前端中文名 → DB 数字
TYPE_NAME_TO_CODE = {
    "IDCARD": 4,
    "身份证": 4,
    "BANKCARD": 3,
    "银行卡号": 3,
    "DEVICE": 1,
    "设备ID": 1,
    "IP": 2,
    "IP地址": 2,
}
CODE_TO_TYPE_NAME = {4: "IDCARD", 3: "BANKCARD", 1: "DEVICE", 2: "IP"}


def _bl_to_response(b: BlacklistExtra) -> BlacklistEntryResponse:
    """ORM → 响应模型."""
    return BlacklistEntryResponse(
        id=b.entry_id,
        type=CODE_TO_TYPE_NAME.get(b.type, str(b.type)),
        bl_type=CODE_TO_TYPE_NAME.get(b.type, str(b.type)),
        value=b.value,
        blacklist_value=b.value,
        reason=b.reason,
        expire_time=b.expire_at,
        created_at=b.created_at,
        create_time=b.created_at,
        status=b.status,
        risk_level=b.risk_level,
        source=b.source,
    )


@blacklist_router.get("", response_model=BlacklistListResponse)
async def list_blacklist(
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    type: str | None = Query(None, description="类型筛选: IDCARD/BANKCARD/DEVICE/IP"),
    value: str | None = Query(None, description="值模糊搜索"),
    db: AsyncSession = Depends(get_db_async),
):
    """分页查询黑名单, 支持类型筛选."""
    where_clauses = [BlacklistExtra.status == 1]  # 只看有效记录

    if type:
        type_code = TYPE_NAME_TO_CODE.get(type)
        if type_code is not None:
            where_clauses.append(BlacklistExtra.type == type_code)
    if value:
        where_clauses.append(BlacklistExtra.value.like(f"%{value}%"))

    # 总数
    count_stmt = select(func.count()).select_from(BlacklistExtra).where(*where_clauses)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 分页
    stmt = (
        select(BlacklistExtra)
        .where(*where_clauses)
        .order_by(BlacklistExtra.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    items = [_bl_to_response(r) for r in rows]

    # 统计 (当前筛选条件下)
    idcard_count = 0
    bankcard_count = 0
    device_count = 0
    ip_count = 0
    for r in rows:
        if r.type == 4:
            idcard_count += 1
        elif r.type == 3:
            bankcard_count += 1
        elif r.type == 1:
            device_count += 1
        elif r.type == 2:
            ip_count += 1

    # 全局统计 (不受分页影响)
    all_stmt = select(BlacklistExtra).where(BlacklistExtra.status == 1)
    all_rows = (await db.execute(all_stmt)).scalars().all()
    global_counts = {"IDCARD": 0, "BANKCARD": 0, "DEVICE": 0, "IP": 0}
    for r in all_rows:
        tn = CODE_TO_TYPE_NAME.get(r.type)
        if tn:
            global_counts[tn] += 1

    return BlacklistListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@blacklist_router.post("", response_model=BlacklistEntryResponse, status_code=201)
async def add_blacklist(
    data: BlacklistCreateRequest,
    db: AsyncSession = Depends(get_db_async),
):
    """添加黑名单条目."""
    # 解析类型
    type_code = None
    if data.type:
        type_code = TYPE_NAME_TO_CODE.get(data.type)
    if type_code is None and data.type_name:
        type_code = TYPE_NAME_TO_CODE.get(data.type_name)
    if type_code is None:
        raise HTTPException(
            status_code=400,
            detail="缺少有效黑名单类型, 支持: IDCARD/BANKCARD/DEVICE/IP",
        )

    # 解析过期时间
    expire_at = None
    if data.expire_time:
        try:
            expire_at = datetime.fromisoformat(data.expire_time)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="过期时间格式无效, 请使用 ISO 格式")

    entry = BlacklistExtra(
        type=type_code,
        value=data.value,
        reason=data.reason or "手动添加",
        source="内部",
        risk_level=3,
        expire_at=expire_at,
        status=1,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _bl_to_response(entry)


@blacklist_router.delete("/{entry_id}")
async def remove_blacklist(
    entry_id: int,
    db: AsyncSession = Depends(get_db_async),
):
    """移除黑名单条目 (软删除: status=0)."""
    entry = (await db.execute(
        select(BlacklistExtra).where(BlacklistExtra.entry_id == entry_id)
    )).scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail=f"黑名单记录不存在: {entry_id}")
    entry.status = 0
    await db.commit()
    return {"entry_id": entry_id, "message": "已移出黑名单"}
