"""医疗风控本地应用入口。"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import AsyncSessionLocal
from app.engine.ml_model import model_status
from app.routers.api import api_router
from app.routers.auth import auth_router
from app.routers.pages import pages_router
from app.service.alert import run_alert_checks
from app.service.auth import ensure_default_admin
from app.middleware.auth import AuthenticationMiddleware


logger = logging.getLogger(__name__)


async def _alert_loop() -> None:
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_alert_checks(db)
        except Exception:
            logger.exception("定时告警检查失败，不影响风控主链路")
        await asyncio.sleep(settings.ALERT_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with AsyncSessionLocal() as db:
        await ensure_default_admin(db)
    task = asyncio.create_task(_alert_loop()) if settings.ALERT_SCHEDULER_ENABLED else None
    yield
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="医疗智能风控系统",
    description="教学型医疗风险识别平台；不提供诊断或治疗建议",
    version="0.4.0",
    lifespan=lifespan,
)
app.include_router(api_router)
app.include_router(auth_router)
app.include_router(pages_router)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
app.add_middleware(AuthenticationMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.APP_SESSION_SECRET,
    max_age=settings.SESSION_MAX_AGE_SECONDS,
    same_site="lax",
    https_only=False,
)


@app.get("/health", tags=["系统"])
async def health() -> dict:
    return {"status": "ok", "phase": "P4", "ml_model": model_status()}


if __name__ == "__main__":
    uvicorn.run(app, host=settings.APP_HOST, port=int(os.getenv("APP_PORT", str(settings.APP_PORT))))
