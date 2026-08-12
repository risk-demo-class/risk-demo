"""
银行风控系统 - FastAPI 应用入口
==============================
启动 FastAPI 服务，注册所有路由和中间件。
覆盖登录/转账/贷款/信用卡四大风控场景。

启动方式:
  python run_app.py                  # 默认 0.0.0.0:8000
  python run_app.py --port 9000      # 指定端口
  python run_app.py --host 127.0.0.1 --port 8080

浏览器访问:
  http://localhost:8000/              → 仪表盘首页
  http://localhost:8000/docs          → Swagger API 文档
"""
import argparse
import os
import sys

# 把当前目录加入 Python 路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# 导入路由
from app.routers.pages import page_router
from app.routers.risk import risk_router
from app.routers.rule import rule_router
from app.routers.dashboard import dashboard_router
from app.routers.blacklist import blacklist_router
from app.routers.agent import agent_router

app = FastAPI(
    title="银行风控系统",
    description="基于规则引擎 + XGBoost 的银行智能风控平台，覆盖登录/转账/贷款/信用卡四大场景",
    version="1.0.0",
)

# 挂载静态资源 (JS/CSS)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# 注册路由
app.include_router(page_router)         # 页面路由 (优先级最高, 根路径 /)
app.include_router(risk_router)         # POST /api/risk/check, GET /api/risk/events
app.include_router(rule_router)         # GET/POST/PUT/DELETE /api/rules
app.include_router(dashboard_router)    # GET /api/dashboard/stats
app.include_router(blacklist_router)    # GET/POST/DELETE /api/blacklist
app.include_router(agent_router)        # POST /api/agent/chat


if __name__ == "__main__":
    import sys
    import uvicorn

    # 修复 Windows 控制台 GBK 编码问题
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="银行风控系统 - 启动服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式自动重载")
    args = parser.parse_args()

    print("=" * 60)
    print("[Bank Risk Shield] 银行风控系统 启动中...")
    print(f"   地址: http://{args.host}:{args.port}")
    print(f"   API文档: http://{args.host}:{args.port}/docs")
    print(f"   仪表盘: http://{args.host}:{args.port}/")
    print("=" * 60)

    uvicorn.run(
        "run_app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
