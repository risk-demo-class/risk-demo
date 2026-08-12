"""
银行风控系统 - 规则管理 API
==========================
GET  /api/rules          — 分页查询规则列表 (支持 scene/risk_level 筛选)
POST /api/rules          — 新建规则
GET  /api/rules/{id}     — 查看规则详情
PUT  /api/rules/{id}     — 更新规则
DELETE /api/rules/{id}   — 删除规则
POST /api/rules/{id}/toggle — 启停规则

规则统一通过 rule_config 配置化, 支持场景隔离、灰度发布与回滚 (PRD 第 6 节).
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RuleConfig
from app.schemas import (
    RuleConfigResponse,
    RuleCreateUpdateRequest,
    RuleListResponse,
    ToggleRuleRequest,
)

rule_router = APIRouter(prefix="/api/rules", tags=["规则管理"])


def _rule_to_response(r: RuleConfig) -> RuleConfigResponse:
    """将 ORM 对象转为响应模型."""
    conditions = r.conditions
    if isinstance(conditions, str):
        try:
            conditions = json.loads(conditions)
        except (json.JSONDecodeError, TypeError):
            conditions = {}
    # 根据 risk_level 推算 score
    score_map = {1: 20, 2: 45, 3: 70, 4: 95}
    score = score_map.get(r.risk_level, 20)
    return RuleConfigResponse(
        rule_id=r.rule_id,
        rule_name=r.rule_name,
        name=r.rule_name,
        scene=r.scene,
        category=r.scene,
        conditions=conditions,
        risk_level=r.risk_level,
        score=score,
        rule_score=score,
        decision=r.decision,
        action=r.action,
        priority=r.priority,
        status=r.status,
        is_enabled=r.status == 1,
        enabled=r.status == 1,
        description=getattr(r, "description", ""),
        desc=getattr(r, "description", ""),
        updated_at=r.updated_at,
    )


@rule_router.get("", response_model=RuleListResponse)
async def list_rules(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    scene: str | None = Query(None, description="场景筛选: LOGIN/TRANSFER/LOAN/CARD"),
    risk_level: int | None = Query(None, description="风险等级: 1-4"),
    db: AsyncSession = Depends(get_db_async),
):
    """分页查询规则列表, 支持场景和风险等级筛选."""
    # 构建查询条件
    where_clauses = []
    if scene:
        where_clauses.append(RuleConfig.scene == scene)
    if risk_level is not None:
        where_clauses.append(RuleConfig.risk_level == risk_level)

    # 总数
    count_stmt = select(func.count()).select_from(RuleConfig)
    if where_clauses:
        count_stmt = count_stmt.where(*where_clauses)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 分页查询
    stmt = select(RuleConfig)
    if where_clauses:
        stmt = stmt.where(*where_clauses)
    stmt = stmt.order_by(RuleConfig.priority.asc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    return RuleListResponse(
        items=[_rule_to_response(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@rule_router.post("", response_model=RuleConfigResponse, status_code=201)
async def create_rule(
    data: RuleCreateUpdateRequest,
    db: AsyncSession = Depends(get_db_async),
):
    """新建规则."""
    # 检查是否已存在
    existing = (await db.execute(
        select(RuleConfig).where(RuleConfig.rule_id == data.rule_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"规则 {data.rule_id} 已存在")

    # 解析 condition
    conditions = None
    if data.condition:
        try:
            conditions = json.loads(data.condition)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="条件表达式不是有效的 JSON")

    # 决策映射
    action = data.action or "PASS"

    rule = RuleConfig(
        rule_id=data.rule_id,
        rule_name=data.rule_name,
        scene=data.category or "TRANSFER",
        conditions=conditions or {},
        risk_level=data.risk_level,
        decision=action,
        action=action,
        priority=data.priority,
        status=1,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _rule_to_response(rule)


@rule_router.get("/{rule_id}", response_model=RuleConfigResponse)
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db_async),
):
    """查看单条规则详情."""
    rule = (await db.execute(
        select(RuleConfig).where(RuleConfig.rule_id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则不存在: {rule_id}")
    return _rule_to_response(rule)


@rule_router.put("/{rule_id}", response_model=RuleConfigResponse)
async def update_rule(
    rule_id: str,
    data: RuleCreateUpdateRequest,
    db: AsyncSession = Depends(get_db_async),
):
    """更新规则."""
    rule = (await db.execute(
        select(RuleConfig).where(RuleConfig.rule_id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则不存在: {rule_id}")

    # 更新字段
    if data.rule_name is not None:
        rule.rule_name = data.rule_name
    if data.category is not None:
        rule.scene = data.category
    if data.risk_level is not None:
        rule.risk_level = data.risk_level
    if data.action is not None:
        rule.decision = data.action
        rule.action = data.action
    if data.priority is not None:
        rule.priority = data.priority
    if data.condition is not None:
        try:
            rule.conditions = json.loads(data.condition)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="条件表达式不是有效的 JSON")

    await db.commit()
    await db.refresh(rule)
    return _rule_to_response(rule)


@rule_router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db_async),
):
    """删除规则."""
    rule = (await db.execute(
        select(RuleConfig).where(RuleConfig.rule_id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则不存在: {rule_id}")
    await db.delete(rule)
    await db.commit()
    return {"rule_id": rule_id, "message": "规则已删除"}


@rule_router.post("/{rule_id}/toggle")
async def toggle_rule(
    rule_id: str,
    data: ToggleRuleRequest | None = None,
    db: AsyncSession = Depends(get_db_async),
):
    """启停规则 (灰度发布/回滚). 支持请求体 {"enabled": true/false} 或直接切换."""
    rule = (await db.execute(
        select(RuleConfig).where(RuleConfig.rule_id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"规则不存在: {rule_id}")

    if data is not None:
        rule.status = 1 if data.enabled else 0
    else:
        rule.status = 1 if rule.status == 0 else 0

    await db.commit()
    return {
        "rule_id": rule_id,
        "status": rule.status,
        "message": f"规则 {'已启用' if rule.status == 1 else '已停用'}",
    }
