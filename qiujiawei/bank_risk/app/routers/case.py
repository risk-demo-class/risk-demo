"""案件管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.database import get_db_async
from bank_risk.app.models import RiskCase
from bank_risk.app.service.case import update_case_status


case_router = APIRouter(prefix="/api/cases", tags=["案件管理"])


class CaseStatusUpdate(BaseModel):
    """案件状态更新请求体"""
    status: str


# 注意路由顺序: "/stats" 必须在 "/{case_id}" 之前注册,
# 否则 FastAPI 会把 "stats" 误当成 case_id
@case_router.get("")
async def api_list_cases(
    status: str = Query(None, description="状态筛选: 待审核/审核中/已通过/已拒绝/已关闭"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    """分页列出案件 (支持 status 筛选)."""
    count_stmt = select(func.count()).select_from(RiskCase)
    if status:
        count_stmt = count_stmt.where(RiskCase.case_status == status)
    total = int((await db.execute(count_stmt)).scalar() or 0)

    stmt = select(RiskCase).order_by(RiskCase.create_time.desc())
    if status:
        stmt = stmt.where(RiskCase.case_status == status)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "items": [_case_to_dict(c) for c in items],
        "total": total, "page": page, "page_size": page_size,
    }


@case_router.get("/stats")
async def api_case_stats(db: AsyncSession = Depends(get_db_async)):
    """案件统计: 各状态案件数."""
    rows = (await db.execute(
        select(RiskCase.case_status, func.count()).group_by(RiskCase.case_status)
    )).all()
    return {state: int(cnt) for state, cnt in rows}


@case_router.get("/{case_id}")
async def api_get_case(case_id: str, db: AsyncSession = Depends(get_db_async)):
    case = (await db.execute(
        select(RiskCase).where(RiskCase.case_id == case_id)
    )).scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")
    return _case_to_dict(case)


@case_router.patch("/{case_id}/status")
async def api_update_status(
    case_id: str,
    data: CaseStatusUpdate,
    db: AsyncSession = Depends(get_db_async),
):
    """更新案件状态."""
    case = await update_case_status(db, case_id, data.status)
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")
    return _case_to_dict(case)


def _case_to_dict(case: RiskCase) -> dict:
    """ORM → dict."""
    return {c.name: getattr(case, c.name) for c in case.__table__.columns}
