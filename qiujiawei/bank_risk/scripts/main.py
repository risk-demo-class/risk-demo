"""
银行风控系统 - 应用入口
启动 FastAPI 服务，注册所有路由和中间件
"""
import sys
import os

# 将项目根目录加入 Python 路径 (bank_risk/scripts/main.py → 上两级 = 项目根)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import logging
import logging.config

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from bank_risk.app.api import (
    page_router,
    risk_router,
    rule_router,
    case_router,
    blacklist_router,
    dashboard_router,
    agent_router,
    alert_router,
    assessment_router,
)
from bank_risk.app.database import async_engine
from bank_risk.app.scheduler import start_scheduler, stop_scheduler

# 统一日志配置: 业务 logger + uvicorn 全走 console + logs/app.log
from bank_risk.app.logging_config import LOGGING_CONFIG
logging.config.dictConfig(LOGGING_CONFIG)


# lifespan: 启动/停止后台调度器 (替代旧的 @app.on_event("startup"))
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动: 案件超时关闭 + 告警检查调度
    start_scheduler()
    yield
    # 停止: 释放连接池 + 优雅关闭调度
    await async_engine.dispose()
    stop_scheduler()


app = FastAPI(
    title="银行风控系统",
    description="基于规则引擎 + AI Agent 的银行风控系统 (信用卡/贷款/转账/登录)",
    version="1.0.0",
    lifespan=lifespan,
)

# 挂载静态资源 (bank_risk/scripts/main.py → 上两级 = bank_risk/, static = bank_risk/static)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")), name="static")

# 注册 9 个路由
app.include_router(page_router)
app.include_router(risk_router)
app.include_router(rule_router)
app.include_router(case_router)
app.include_router(blacklist_router)
app.include_router(dashboard_router)
app.include_router(agent_router)
app.include_router(alert_router)
app.include_router(assessment_router)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("APP_PORT", "8001"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
