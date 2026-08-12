# -*- coding: utf-8 -*-
"""应用装配层（宝典第 3 章「启动流程」、第 14 章 `main --> api` / `main --> ml_model`）

对齐 FastAPI 的 `main.py`：**只做装配，不写业务**。

启动时序（宝典 3.1）：
    _run.py → 配置路径/编码/日志
            → import scripts.main（触发 App 创建）
            → 挂载 10 个 router（30 个 API 端点）
            → ml_model._schedule_load 懒加载（import engine 时已自动触发）
            → 存在 xgb_model.json ? 加载 XGBoost : 降级到纯规则
            → 监听 0.0.0.0:8000

三个关键设计（宝典 3.2）：
    ① 路由 re-export —— 本文件只调 `api.include_all(app)` 一行，改 router 不用改 main
    ② XGBoost 懒加载 —— import 时只检查文件不阻塞，第一次 predict() 才真正推理
    ③ 日志到文件 —— `_run.py` 负责重定向到 logs/server.log
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# ---- 允许 `python scripts/main.py` 直接运行（FAQ 1：ModuleNotFoundError）----
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app import api                                     # noqa: E402  ← 10 router re-export 中心
from app.config import WEB_DIR, settings                 # noqa: E402
from app.database import init_database, pool            # noqa: E402
from app.engine import ml_model                         # noqa: E402  ← import 即触发 _schedule_load
from app.framework import HTTPError, Response, RiskApp, Router, serve  # noqa: E402
from app.template import TemplateEngine, TemplateError  # noqa: E402

logger = logging.getLogger("ai_risk.main")

# ================================================================ 应用对象
app = RiskApp(title=settings.APP_NAME, version=settings.APP_VERSION)

# ---------------------------------------------------------------- L1：API 层
_mounted = api.include_all(app)
logger.info("已挂载 %d 个 router / %d 个 API 端点", api.ROUTER_COUNT, _mounted)

# ---------------------------------------------------------------- 静态资源
app.mount_static("/static", WEB_DIR / "static")

# ---------------------------------------------------------------- 模板引擎
# DEBUG 模式关缓存：改 HTML 刷新即生效，方便课堂演示
templates = TemplateEngine(WEB_DIR / "templates", cache=not settings.DEBUG)

# ================================================================ 前端页面
# 12 个功能页 + 1 个 API 目录页。全部走 SPA（hash 路由），服务端只发骨架。
PAGES: List[Dict[str, str]] = [
    {"key": "dashboard",  "title": "风控大盘",   "icon": "gauge",   "group": "监控"},
    {"key": "check",      "title": "风控检查",   "icon": "shield",  "group": "监控"},
    {"key": "assessment", "title": "评估历史",   "icon": "history", "group": "监控"},
    {"key": "case",       "title": "案件工作台", "icon": "folder",  "group": "处置"},
    {"key": "rule",       "title": "规则管理",   "icon": "rules",   "group": "处置"},
    {"key": "blacklist",  "title": "黑名单",     "icon": "ban",     "group": "处置"},
    {"key": "profile",    "title": "用户画像",   "icon": "user",    "group": "洞察"},
    {"key": "business",   "title": "业务数据",   "icon": "table",   "group": "洞察"},
    {"key": "assistant",  "title": "AI 助手",    "icon": "robot",   "group": "洞察"},
    {"key": "model",      "title": "模型中心",   "icon": "brain",   "group": "系统"},
    {"key": "config",     "title": "系统配置",   "icon": "cog",     "group": "系统"},
    {"key": "audit",      "title": "审计日志",   "icon": "log",     "group": "系统"},
]

page_router = Router(prefix="", tags=["前端页面"], name="page_router")


def _render_shell() -> Response:
    try:
        html_text = templates.render(
            "index.html",
            app_name=settings.APP_NAME,
            app_version=settings.APP_VERSION,
            endpoint_count=str(api.ENDPOINT_COUNT),
            router_count=str(api.ROUTER_COUNT),
            # 导航单一数据源：PAGES 在此序列化下发，前端不再重复维护一份菜单
            pages_json=json.dumps(PAGES, ensure_ascii=False),
        )
    except TemplateError as exc:
        raise HTTPError(500, f"页面模板缺失: {exc}") from exc
    return Response.html(html_text)


@page_router.get("/", "SPA 首页（12 个功能页）")
def index(request: Any) -> Response:  # noqa: ARG001
    return _render_shell()


@page_router.get("/index.html", "SPA 首页别名")
def index_alias(request: Any) -> Response:  # noqa: ARG001
    return _render_shell()


@page_router.get("/favicon.ico", "站点图标")
def favicon(request: Any) -> Response:  # noqa: ARG001
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
           '<rect width="32" height="32" rx="7" fill="#2563eb"/>'
           '<path d="M16 6l8 3.2v6.2c0 5-3.4 8.9-8 10.4-4.6-1.5-8-5.4-8-10.4V9.2L16 6z" '
           'fill="none" stroke="#fff" stroke-width="2"/>'
           '<path d="M12 16.2l2.8 2.8L20.4 13" fill="none" stroke="#fff" '
           'stroke-width="2.2" stroke-linecap="round"/></svg>')
    return Response(svg.encode("utf-8"), 200, "image/svg+xml", {"Cache-Control": "max-age=86400"})


@page_router.get("/docs", "API 目录（Swagger 等价物）")
def docs(request: Any) -> Response:  # noqa: ARG001
    """自动生成的端点清单页 —— 对齐 FastAPI 的 /docs。"""
    rows: List[str] = []
    for group in api.router_manifest():
        rows.append(
            f'<tr class="grp"><td colspan="3">{group["name"]}'
            f'<span class="mut"> · {group["prefix"] or "/"} · '
            f'{group["endpoint_count"]} 个端点</span></td></tr>'
        )
        for ep in group["endpoints"]:
            rows.append(
                f'<tr><td><span class="m m-{ep["method"].lower()}">{ep["method"]}</span></td>'
                f'<td><code>{ep["path"]}</code></td><td>{ep["summary"]}</td></tr>'
            )
    html_text = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>API 目录 · {settings.APP_NAME}</title>
<style>
:root{{--bd:#e5e7eb;--mut:#64748b;--bg:#f8fafc}}
body{{font-family:"Segoe UI","Microsoft YaHei",sans-serif;margin:0;padding:32px;
background:var(--bg);color:#0f172a}}
h1{{font-size:20px;margin:0 0 4px}}p.sub{{color:var(--mut);margin:0 0 20px;font-size:13px}}
table{{width:100%;max-width:1080px;border-collapse:collapse;background:#fff;
border:1px solid var(--bd);border-radius:10px;overflow:hidden;font-size:13px}}
td{{padding:9px 14px;border-bottom:1px solid #f1f5f9}}
tr.grp td{{background:#f1f5f9;font-weight:600;font-size:13px}}
tr.grp .mut{{color:var(--mut);font-weight:400}}
code{{font-family:Consolas,monospace;color:#1d4ed8}}
.m{{display:inline-block;min-width:58px;text-align:center;padding:2px 8px;border-radius:5px;
font-size:11px;font-weight:700;color:#fff}}
.m-get{{background:#0891b2}}.m-post{{background:#16a34a}}
.m-put{{background:#d97706}}.m-delete{{background:#dc2626}}
a{{color:#2563eb;text-decoration:none}}
</style></head><body>
<h1>{settings.APP_NAME} · API 目录</h1>
<p class="sub">{settings.APP_VERSION} · {api.ROUTER_COUNT} 个 router · {api.ENDPOINT_COUNT} 个 API 端点
&nbsp;|&nbsp;<a href="/">← 返回控制台</a></p>
<table>{''.join(rows)}</table></body></html>"""
    return Response.html(html_text)


app.include_router(page_router)


# ================================================================ 启动钩子
@app.on_startup
def _startup_database() -> None:
    """确保 24 张表存在（幂等）。首次运行免手动执行 init_db.py。"""
    try:
        created = init_database(drop=False)
        logger.info("数据库就绪: %s (表 %d 张)", settings.DB_PATH, created.get("tables", 0))
    except Exception as exc:  # noqa: BLE001
        logger.error("数据库初始化失败: %s", exc)
        raise


@app.on_startup
def _startup_model() -> None:
    """XGBoost 懒加载结果播报（宝典 3.2 关键设计 ②）。"""
    status = ml_model.model_status()
    if status.get("loaded"):
        logger.info("XGBoost 已加载: %s (%s 棵树 / %d 维特征)",
                    status.get("implementation"), status.get("trees", "-"),
                    status.get("feature_count", 0))
    elif not settings.XGB_ENABLED:
        logger.info("XGBoost 开关关闭 → 降级到纯规则模式（宝典 FAQ 3）")
    else:
        logger.info("未找到模型文件 %s → 降级到纯规则模式（先跑 scripts/train_xgb_model.py）",
                    settings.XGB_MODEL_PATH)


@app.on_startup
def _startup_banner() -> None:
    logger.info("=" * 66)
    logger.info("  %s %s", settings.APP_NAME, settings.APP_VERSION)
    logger.info("  控制台   http://127.0.0.1:%d/", settings.PORT)
    logger.info("  API 目录 http://127.0.0.1:%d/docs", settings.PORT)
    logger.info("  健康自检 http://127.0.0.1:%d/api/system/health", settings.PORT)
    logger.info("  连接池   size=%d overflow=%d", settings.DB_POOL_SIZE, settings.DB_MAX_OVERFLOW)
    logger.info("=" * 66)


def run(host: str = "", port: int = 0) -> None:
    """启动 HTTP 服务（等价 `uvicorn.run(app, ...)`）。"""
    try:
        serve(app, host or settings.HOST, port or settings.PORT)
    finally:
        pool.dispose()
        logger.info("连接池已释放，服务退出")


if __name__ == "__main__":
    from _run import bootstrap

    bootstrap()
    run()
