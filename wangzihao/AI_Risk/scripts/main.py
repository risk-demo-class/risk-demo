"""
制造业设备经销商智能风控平台 - 应用入口
启动 FastAPI 服务，注册所有路由和中间件
"""
# 将项目根目录加入 Python 路径
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import logging.config


from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

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

# 【P4-L4 2026-08-08】统一日志配置: 业务 logger + uvicorn 全走 console + logs/app.log
# 用 dictConfig 而不是 basicConfig, 这样能精细控制 handlers / formatters
from app.logging_config import LOGGING_CONFIG
logging.config.dictConfig(LOGGING_CONFIG)

# 【P4-L3 2026-08-08】lifespan: 启动/停止后台调度器
# 替代旧的 @app.on_event("startup") (FastAPI 0.93+ 已 deprecated)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Web 进程启动时显式加载 Step 6 标准制造业模型；否则在线决策会静默退化为纯规则。
    from app.engine.ml_model import FEATURE_COLUMNS, get_model, load_model
    # 启动: 启动案件超时关闭 + 告警检查调度
    from app.scheduler import start_scheduler, stop_scheduler, is_running
    app.state.xgb_model_loaded = load_model()
    model = get_model()
    app.state.xgb_model_feature_count = model.num_features() if model is not None else 0
    app.state.xgb_feature_contract_ok = bool(
        model is not None
        and model.num_features() == 25
        and model.feature_names == FEATURE_COLUMNS
    )
    if app.state.xgb_model_loaded and not app.state.xgb_feature_contract_ok:
        raise RuntimeError("XGBoost 模型与冻结的25维 FEATURE_COLUMNS 不一致")
    start_scheduler()
    app.state.scheduler_running = is_running()
    yield
    # 停止: 优雅关闭调度 (等当前轮跑完, 最多 10s)
    await stop_scheduler()
    # 释放 Agent、路由和调度器共享的连接池，避免进程退出后 aiomysql 跨事件循环析构。
    from app.database import async_engine
    await async_engine.dispose()
    app.state.scheduler_running = False

app = FastAPI(
    title="制造业设备经销商智能风控平台",
    description="基于 JSON 规则引擎、25维特征、XGBoost 与 Agent 的设备经销商风险系统",
    version="1.0.0",
    lifespan=lifespan,
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
app.include_router(agent_router)
app.include_router(alert_router)   # 【P4-L2】告警路由
app.include_router(assessment_router)   # 【P3-S9】评估历史路由

if __name__ == "__main__":
    import uvicorn
    # 【P4-L3】reload=True 跟 lifespan 有点冲突, 调度器会启 2 次. 生产用 gunicorn (无 reload)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
