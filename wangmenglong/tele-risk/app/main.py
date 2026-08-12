"""
电信风控系统 - 应用入口
启动 FastAPI 服务, 注册路由 + 静态资源 + XGBoost 模型预加载.

跑法:
  python app/main.py                 # 直接跑 (端口 8001)
  python run_app.py                  # 带自检脚本
"""
import logging
import os
import sys

# 项目根加入 sys.path (让 app.* 可 import)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import (
    agent_router, assessment_router, blacklist_router, case_router,
    dashboard_router, page_router, risk_router, rule_router,
)
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动: 预加载 XGBoost 模型 (后台线程, 不阻塞). 停止: 无特殊清理."""
    from app.engine.ml_model import load_model
    load_model()
    logger.info("电信风控系统启动 (DB=%s, XGB=%s)", settings.DB_NAME, settings.XGB_ENABLED)
    yield
    logger.info("电信风控系统停止")


app = FastAPI(
    title="电信风控系统",
    description="基于规则引擎 + XGBoost 双轨融合的电信行业风险控制系统 (反诈法合规)",
    version="1.0.0",
    lifespan=lifespan,
)

# 静态资源
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_static_dir = os.path.join(_BASE_DIR, "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# 注册路由
app.include_router(page_router)
app.include_router(dashboard_router)
app.include_router(risk_router)
app.include_router(rule_router)
app.include_router(blacklist_router)
app.include_router(assessment_router)
app.include_router(case_router)
app.include_router(agent_router)


@app.get("/health")
async def health():
    """健康检查."""
    from app.engine.ml_model import is_model_loaded
    return {
        "status": "ok",
        "service": "tele-risk",
        "db": settings.DB_NAME,
        "xgb_loaded": is_model_loaded(),
        "agent_enabled": settings.AI_AGENT_ENABLED,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", "8001"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
