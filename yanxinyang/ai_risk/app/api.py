# -*- coding: utf-8 -*-
"""路由 re-export 中心（宝典 3.2 关键设计 ①、14 章 `api --> routers`）

> **本文件不写任何路由**，只做两件事：
>   1. 从 `app.routers.*` 导入 10 个 router
>   2. 汇总成 `ALL_ROUTERS`，供 `scripts/main.py` 一次性挂载
>
> 好处（宝典 14 章「关键解读」）：**改 router 不用改 main**。
> 新增一个业务域时，只需在 `app/routers/` 下加文件 + 在本文件登记一行，
> `main.py` 完全不动 —— 这就是「注册中心」模式。

10 个 router 与 30 个 API 端点的对应关系（宝典 2.2 L1 路由层）：

| # | router          | prefix            | 端点数 | 职责                       |
|---|-----------------|-------------------|-------|----------------------------|
| 1 | risk_router     | /api/risk         | 3     | 风控检查（7 步流水线入口）    |
| 2 | rule_router     | /api/rules        | 5     | 规则 CRUD + 14 运算符测试     |
| 3 | case_router     | /api/cases        | 4     | 案件工作台（5 状态机）        |
| 4 | blacklist_router| /api/blacklist    | 3     | 黑名单管理                   |
| 5 | profile_router  | /api/profiles     | 2     | 用户画像                     |
| 6 | dashboard_router| /api/dashboard    | 3     | 风控大盘 + 趋势 + 规则效果     |
| 7 | business_router | /api/business     | 2     | 业务数据字典与表浏览          |
| 8 | agent_router    | /api/agent        | 2     | AI 助手（8 工具 + SSE）       |
| 9 | model_router    | /api/model        | 3     | 模型中心（XGBoost）           |
| 10| system_router   | /api/system       | 3     | 健康自检 + 配置 + 审计日志     |
|   | **合计**        |                   | **30**|                            |
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.framework import Router
from app.routers.agent import router as agent_router
from app.routers.blacklist import router as blacklist_router
from app.routers.business import router as business_router
from app.routers.case import router as case_router
from app.routers.dashboard import router as dashboard_router
from app.routers.model import router as model_router
from app.routers.profile import router as profile_router
from app.routers.risk import router as risk_router
from app.routers.rule import router as rule_router
from app.routers.system import router as system_router

# ---------------------------------------------------------------- 注册表
# 顺序即 /docs 页面的展示顺序，按「业务主干 → 支撑 → 系统」排列
ALL_ROUTERS: Tuple[Router, ...] = (
    risk_router,        # 1. 风控检查 —— 系统心脏
    rule_router,        # 2. 规则管理
    case_router,        # 3. 案件工作台
    blacklist_router,   # 4. 黑名单
    profile_router,     # 5. 用户画像
    dashboard_router,   # 6. 风控大盘
    business_router,    # 7. 业务数据
    agent_router,       # 8. AI 助手
    model_router,       # 9. 模型中心
    system_router,      # 10. 系统
)

ROUTER_COUNT = len(ALL_ROUTERS)
ENDPOINT_COUNT = sum(len(r.routes) for r in ALL_ROUTERS)

# 契约自检：宝典要求「10 个 router / 30 个 API 端点」，装配期就必须成立
assert ROUTER_COUNT == 10, f"router 数量应为 10，实际 {ROUTER_COUNT}"
assert ENDPOINT_COUNT == 30, f"API 端点数量应为 30，实际 {ENDPOINT_COUNT}"


def include_all(app: Any) -> int:
    """把 10 个 router 一次性挂到 app 上，返回挂载的端点数。

    `scripts/main.py` 只需 `api.include_all(app)` 一行即可完成 L1 层装配。
    """
    for router in ALL_ROUTERS:
        app.include_router(router)
    return ENDPOINT_COUNT


def router_manifest() -> List[Dict[str, Any]]:
    """路由清单（供 /api/system/health 与 /docs 页自检展示）。"""
    manifest: List[Dict[str, Any]] = []
    for router in ALL_ROUTERS:
        manifest.append({
            "name": router.name,
            "prefix": router.prefix,
            "tags": list(router.tags),
            "endpoint_count": len(router.routes),
            "endpoints": [
                {"method": r.method, "path": r.path, "summary": r.summary}
                for r in router.routes
            ],
        })
    return manifest


__all__ = [
    "ALL_ROUTERS", "ROUTER_COUNT", "ENDPOINT_COUNT",
    "include_all", "router_manifest",
    "risk_router", "rule_router", "case_router", "blacklist_router",
    "profile_router", "dashboard_router", "business_router",
    "agent_router", "model_router", "system_router",
]
