"""
旅游风控系统 - 应用入口
启动 FastAPI 服务, 注册所有路由和中间件
"""
import logging
import logging.config
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.api import (
    agent_router,
    alert_router,
    assessment_router,
    blacklist_router,
    case_router,
    dashboard_router,
    page_router,
    profile_router,
    risk_router,
    rule_router,
)
from app.engine.ml_model import load_model
from app.logging_config import LOGGING_CONFIG

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/停止: XGBoost 模型加载 + 后台调度器."""
    load_model()  # 模型不存在时自动降级纯规则
    from app.scheduler import is_running, start_scheduler, stop_scheduler
    start_scheduler()
    app.state.scheduler_running = is_running()
    yield
    await stop_scheduler()
    app.state.scheduler_running = False


app = FastAPI(
    title="旅游风控系统",
    description="基于规则引擎 + XGBoost 双轨融合的旅游平台风险控制系统",
    version="1.0.0",
    lifespan=lifespan,
)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")), name="static")


@app.middleware("http")
async def no_cache_html(request, call_next):
    """HTML 页面禁用浏览器缓存, 保证规则/案件等管理页永远拉到最新模板."""
    response: Response = await call_next(request)
    if request.url.path.endswith((".html", "/")) or not request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response

app.include_router(page_router)
app.include_router(risk_router)
app.include_router(rule_router)
app.include_router(case_router)
app.include_router(blacklist_router)
app.include_router(profile_router)
app.include_router(dashboard_router)
app.include_router(agent_router)
app.include_router(alert_router)
app.include_router(assessment_router)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_config=LOGGING_CONFIG)
