"""FastAPI application factory and default ASGI application."""

import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.bootstrap import initialize_database
from app.config import settings
from app.database import close_database
from app.logging_config import configure_logging
from app.engine.model_manager import model_manager
from app.observability import install_observability_middleware
from app.routers import (
    agent_router,
    appeal_router,
    graph_router,
    health_router,
    model_router,
    operations_router,
    page_router,
    risk_router,
)


configure_logging()
logger = logging.getLogger(__name__)
_root = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "service_starting",
        extra={
            "event_data": {
                "stage": "complete-three-layer",
                "log_retention_days": settings.LOG_RETENTION_DAYS,
                "alert_webhook_configured": bool(settings.ALERT_WEBHOOK_URL),
            }
        },
    )
    if settings.AUTO_INIT_DB:
        result = await initialize_database(seed_demo=settings.SEED_DEMO_DATA)
        logger.info("database_initialized", extra={"event_data": result})
    if settings.ENABLE_MODEL_ENGINE:
        models_ready = await asyncio.to_thread(model_manager.ensure_ready)
        logger.info("model_registry_ready", extra={"event_data": {"ready": models_ready}})
    yield
    await close_database()
    logger.info("service_stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.APP_NAME,
        description="银行信用卡、贷款、转账、登录四场景智能风控平台",
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )
    install_observability_middleware(application)
    application.mount("/static", StaticFiles(directory=str(_root / "static")), name="static")
    application.include_router(page_router)
    application.include_router(health_router)
    application.include_router(risk_router)
    application.include_router(appeal_router)
    application.include_router(model_router)
    application.include_router(graph_router)
    application.include_router(operations_router)
    application.include_router(agent_router)
    return application


app = create_app()
