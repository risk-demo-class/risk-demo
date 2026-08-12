# -*- coding: utf-8 -*-
"""L1 路由 · business_router —— 业务数据浏览（24 张表数据字典 + 通用查询）

对应教学宝典第 16 章「数据模型」：17 张业务表 + 7 张风控表（+1 审计表）。
特征引擎的 25 维全部来自这些表，所以教学时必须能直接翻原始数据对账。

安全设计：表名走**白名单**（models.ALL_TABLES），绝不拼接用户输入的表名/列名，
排序列同样校验，防 SQL 注入。

端点（2 个）：
    GET    /api/business/dictionary       数据字典（24+1 张表全字段说明）
    GET    /api/business/table/{table}    表数据分页查询（白名单 + 关键字 + 排序）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app import models
from app.database import Session, pool
from app.framework import HTTPError, Request, Router

logger = logging.getLogger("ai_risk.routers.business")

router = Router(prefix="/api/business", tags=["业务数据"], name="business_router")


def _db() -> Session:
    return Session(pool.acquire())


# ====================================================================== 1
@router.get("/dictionary", "数据字典（24 张表 + 审计表全字段）")
def dictionary(request: Request) -> Dict[str, Any]:
    group = request.q("group", "") or ""
    tables = models.data_dictionary()
    if group:
        tables = [t for t in tables if t["group"] == group]

    db = _db()
    try:
        for table in tables:
            try:
                table["row_count"] = db.scalar(f'SELECT COUNT(*) FROM "{table["table"]}"')
            except Exception:  # noqa: BLE001  表还没建（未 init_db）
                table["row_count"] = -1
    finally:
        db.close()

    return {"success": True, "tables": tables, "stats": models.TABLE_STATS,
            "groups": ["业务", "风控", "审计"],
            "enums": {
                "event_types": list(models.EVENT_TYPES),
                "risk_levels": list(models.RISK_LEVELS),
                "decisions": list(models.DECISIONS),
                "case_statuses": list(models.CASE_STATUSES),
                "rule_categories": list(models.RULE_CATEGORIES),
                "blacklist_types": list(models.BLACKLIST_TYPES),
                "order_statuses": list(models.ORDER_STATUSES),
            }}


# ====================================================================== 2
@router.get("/table/{table}", "表数据分页查询（表名白名单）")
def table_rows(request: Request) -> Dict[str, Any]:
    name = request.path_params["table"]
    table = models.ALL_TABLES.get(name)
    if table is None:
        raise HTTPError(404, f"表不存在或不在白名单内: {name}。"
                             f"可用表见 GET /api/business/dictionary")

    columns = [c.name for c in table.columns]
    limit = min(max(request.q_int("limit", 20), 1), 200)
    offset = max(request.q_int("offset", 0), 0)
    keyword = request.q("keyword", "") or ""
    order_by = request.q("order_by", "") or columns[0]
    if order_by not in columns:                     # 防注入：排序列必须是真实列
        order_by = columns[0]
    direction = "ASC" if str(request.q("order", "desc")).lower() == "asc" else "DESC"

    where: List[str] = ["1=1"]
    params: List[Any] = []

    # 常用过滤：user_id / order_id 直接支持
    for key in ("user_id", "order_id", "event_id", "case_id"):
        value = request.q(key, "")
        if value and key in columns:
            where.append(f'"{key}" = ?')
            params.append(value)

    if keyword:
        text_cols = [c.name for c in table.columns
                     if c.type.upper().startswith(("VARCHAR", "TEXT", "CHAR"))]
        if text_cols:
            where.append("(" + " OR ".join(f'"{c}" LIKE ?' for c in text_cols) + ")")
            params.extend([f"%{keyword}%"] * len(text_cols))

    clause = " AND ".join(where)
    db = _db()
    try:
        total = db.scalar(f'SELECT COUNT(*) FROM "{name}" WHERE {clause}', params)
        rows = db.fetch_all(
            f'SELECT * FROM "{name}" WHERE {clause} ORDER BY "{order_by}" {direction} '
            f"LIMIT ? OFFSET ?", params + [limit, offset])
    except Exception as exc:  # noqa: BLE001
        db.close()
        raise HTTPError(500, f"查询表 {name} 失败（可能尚未初始化数据库）: {exc}") from exc
    finally:
        if not db.closed:
            db.close()

    return {"success": True, "table": name, "comment": table.comment, "group": table.group,
            "total": total, "items": rows, "limit": limit, "offset": offset,
            "order_by": order_by, "order": direction.lower(),
            "columns": [{"name": c.name, "type": c.type, "comment": c.comment,
                         "constraint": c.constraint} for c in table.columns]}
