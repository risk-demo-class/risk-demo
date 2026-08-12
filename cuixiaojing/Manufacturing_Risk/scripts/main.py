"""
制造业风控系统 - 应用入口
启动 FastAPI 服务，注册所有路由和中间件
"""
# 将项目根目录加入 Python 路径
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import logging.config

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import (
    agent_router,
    assessment_router,
    blacklist_router,
    case_router,
    dashboard_router,
    page_router,
    profile_router,
    risk_router,
    rule_router,
)

# 统一日志配置
from app.logging_config import LOGGING_CONFIG
logging.config.dictConfig(LOGGING_CONFIG)

app = FastAPI(
    title="制造业风控系统",
    description="经销商订货 / 设备保修 / 售后维修 / 串货举报 风险控制 (仿 AI_Risk 电商风控架构)",
    version="1.0.0",
)

# 挂载静态资源
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")), name="static")

# 注册路由
app.include_router(page_router)
app.include_router(risk_router)
app.include_router(rule_router)
app.include_router(case_router)
app.include_router(blacklist_router)
app.include_router(profile_router)
app.include_router(dashboard_router)
app.include_router(assessment_router)
app.include_router(agent_router)   # AI 助手

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("scripts.main:app", host="0.0.0.0", port=8000, reload=False)
