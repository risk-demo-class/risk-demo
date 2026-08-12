"""
FastAPI 启动入口.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import settings
from app.database import check_db_connection, close_database
from app.logging_config import setup_logging
from app.scheduler import start_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期."""
    setup_logging()
    logger.info("旅游出行风控系统启动中")
    db_ok = await check_db_connection()
    if not db_ok:
        logger.warning("数据库不可用, 请检查 MySQL 与 .env 配置")
    scheduler_task = await start_scheduler()
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        await close_database()
        logger.info("旅游出行风控系统已退出")


def create_app() -> FastAPI:
    """创建 FastAPI 应用."""
    app = FastAPI(
        title="旅游出行风控系统",
        description="规则引擎 + XGBoost 双轨融合 + DeepSeek 本地 LLM 辅助",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    app.mount(
        "/static",
        StaticFiles(directory="static"),
        name="static",
    )
    return app


app = create_app()
