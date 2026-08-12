"""存活与就绪检查接口。"""

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.database import ping_database
from app.models import Base
from app.schemas import HealthResponse, ReadinessResponse


router = APIRouter(tags=["系统健康"])


@router.get("/health", response_model=HealthResponse, summary="查看服务信息")
@router.get("/healthz", response_model=HealthResponse, include_in_schema=False)
async def health() -> HealthResponse:
    """存活检查不依赖数据库，供 Docker 判断进程是否正常。"""

    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        environment=settings.APP_ENV,
        business_table_count=8,
        risk_table_count=9,
        registered_table_count=len(Base.metadata.tables),
    )


@router.get("/readyz", response_model=ReadinessResponse, summary="检查数据库是否就绪")
async def readiness() -> ReadinessResponse:
    try:
        await ping_database()
    except Exception as exc:
        # 不把连接串、密码或底层堆栈暴露给客户端。
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "database": "unavailable"},
        ) from exc
    return ReadinessResponse(status="ready", database="available")

