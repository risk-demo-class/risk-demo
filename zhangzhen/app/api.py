"""FastAPI 应用工厂。"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import settings
from app.database import async_engine
from app.routers import (
    agent_router,
    assessment_router,
    blacklist_router,
    case_router,
    dashboard_router,
    health_router,
    page_router,
    profile_router,
    risk_router,
    rule_router,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """统一管理应用资源；后续调度器也在这里启动和停止。"""

    yield
    await async_engine.dispose()


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        description="教学用银行智能风控原型，不用于真实银行生产决策",
        version=__version__,
        lifespan=lifespan,
    )
    application.mount("/static", StaticFiles(directory=PROJECT_ROOT / "static"), name="static")
    application.include_router(page_router)
    application.include_router(health_router)
    application.include_router(risk_router)
    application.include_router(rule_router)
    application.include_router(case_router)
    application.include_router(assessment_router)
    application.include_router(blacklist_router)
    application.include_router(profile_router)
    application.include_router(dashboard_router)
    application.include_router(agent_router)
    return application


app = create_app()
