"""应用装配层：创建表、准备演示数据并注册 Router 与演示页面。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401  注册所有 ORM 模型，供 Base.metadata 建表。
from app.api import assessment_router, blacklist_router, case_router, dashboard_router, page_router, risk_router, rule_router
from app.database import Base, engine
from app.seed import seed_demo_data


Base.metadata.create_all(bind=engine)
seed_demo_data()

app = FastAPI(title="教育行业 AI 风控", version="0.1.0")
app.include_router(page_router)
app.include_router(risk_router)
app.include_router(rule_router)
app.include_router(case_router)
app.include_router(assessment_router)
app.include_router(blacklist_router)
app.include_router(dashboard_router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
