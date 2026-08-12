"""银行风控仪表盘聚合 API。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.schemas import DashboardOverview
from app.service.admin import dashboard_overview


router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@router.get("/overview", response_model=DashboardOverview)
async def overview(db: AsyncSession = Depends(get_db_async)) -> DashboardOverview:
    return await dashboard_overview(db)
