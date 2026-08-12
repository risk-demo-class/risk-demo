"""FastAPI 应用工厂。"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app import __version__
from app.config import settings
from app.database import async_engine
from app.routers import health_router


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
    application.include_router(health_router)
    return application


app = create_app()

