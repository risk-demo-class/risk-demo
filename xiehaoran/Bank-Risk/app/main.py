"""银行风控系统 - FastAPI 入口 (全量移植自 AI_Risk, 银行语义).

职责:
  - 创建 FastAPI app, 挂载全部 /api 路由 (风控检查/规则/案件/黑名单/画像/仪表盘/Agent/告警/评估)
  - 托管前端静态资源 web/dist (Vite 构建产物)
  - 兼容 python -m app / uvicorn app.main:app 两种启动方式

启动:
  python -m app            # 内部用 uvicorn 拉起 (端口 8010)
  uvicorn app.main:app --reload --port 8010
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.routers import (  # noqa: E402
    agent_router, alert_router, assessment_router, blacklist_router,
    case_router, dashboard_router, decision_router, features_router,
    model_eval_router, profile_router, risk_router, rule_router,
)

app = FastAPI(
    title="Bank-Risk 银行风控控制台",
    description="银行风控决策与可视化接口层 (全量移植 AI_Risk, 银行语义)",
    version="2.0.0",
)

# API 路由
for r in (
    risk_router, rule_router, case_router, blacklist_router, profile_router,
    dashboard_router, agent_router, alert_router, assessment_router,
    decision_router, features_router, model_eval_router,
):
    app.include_router(r)


# ============================================================
# 前端静态资源托管 (Vite 构建产物 web/dist)
# ============================================================
WEB_DIST = ROOT / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")


@app.get("/api/health")
def health():
    return {"status": "ok", "frontend_built": WEB_DIST.exists()}


@app.get("/")
def serve_index():
    """返回前端 SPA 入口 (前端用内存路由接管页面切换)."""
    index = WEB_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"detail": "前端未构建, 请先 `npm run build` (web/)"}


if __name__ == "__main__":
    import uvicorn

    # 端口 8010: 避免与基线 AI_Risk 的 8000 冲突
    uvicorn.run("app.main:app", host="0.0.0.0", port=8010, reload=False)
