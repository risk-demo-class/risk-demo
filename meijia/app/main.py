from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.routers import ALL_ROUTERS
from app.service.errors import DomainError

ROOT = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 统一日志 (stdout + logs/app.log 轮转)
    from app.logging_config import setup_logging

    setup_logging()
    # 启动时尝试加载 XGBoost 模型; 缺失/失败不影响启动 (决策走纯规则兜底)
    from app.engine import ml_model

    ml_model.load_model()
    # 启动后台调度器 (超时关案 + 告警检查); 间隔=0 时不启动
    from app.scheduler import start_scheduler, stop_scheduler

    scheduler_task = start_scheduler()
    yield
    await stop_scheduler()
    if scheduler_task and not scheduler_task.done():
        scheduler_task.cancel()


app = FastAPI(
    title="教育风控系统",
    description="报名、学习、退费、学历认证与直播打赏风险管理（规则 + XGBoost 双轨融合）",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(DomainError)
def handle_domain_error(_request: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message, "code": exc.code})


app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
for router in ALL_ROUTERS:
    app.include_router(router)
