"""
FastAPI 应用入口 — scripts/main.py
import 本文件即创建 app;_run.py 负责真正启动 uvicorn。
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    agent_router, blacklist_router, case_router, course_router, dashboard_router,
    event_router, risk_router, rule_router, setting_router, user_router,
)
from app.config import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="教育行业 AI 风控系统 — 规则 + AI 双保险(报名/缴费/退费/考试/作业)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 10 个 router
app.include_router(risk_router)
app.include_router(rule_router)
app.include_router(case_router)
app.include_router(user_router)
app.include_router(dashboard_router)
app.include_router(agent_router)
app.include_router(blacklist_router)
app.include_router(event_router)
app.include_router(course_router)
app.include_router(setting_router)


@app.get("/")
async def root():
    return {"app": settings.APP_NAME, "version": "1.0.0", "docs": "/docs"}


@app.get("/api/health")
async def health():
    from app.engine import ml_model
    return {
        "status": "ok",
        "ml_model_loaded": ml_model.is_model_loaded(),
        "ml_load_error": ml_model._LOAD_ERROR or "",
    }
