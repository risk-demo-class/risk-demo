"""
银行风控系统 - 风控检查 API
==========================
POST /api/risk/check        — 风控事件检查入口
GET  /api/risk/health       — 健康检查
GET  /api/risk/events       — 风险事件列表 (分页+多维度筛选)
GET  /api/risk/events/{id}  — 风险事件详情

接收统一事件格式 (PRD 第 5 节), 返回风险决策结果.
覆盖登录/转账/贷款/信用卡四大场景.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskEvent
from app.schemas import (
    RiskCheckRequest,
    RiskCheckResponse,
    RiskEventItem,
    RiskEventListResponse,
)
from app.service.event import process_event

risk_router = APIRouter(prefix="/api/risk", tags=["风控检查"])

# 事件类型 → 中文名称
EVENT_TYPE_CN = {
    "LOGIN": "登录", "TRANSFER": "转账", "PAYMENT": "支付", "WITHDRAW": "取现",
    "LOAN_APPLY": "贷款申请", "CARD_APPLY": "信用卡申请", "DISBURSE": "放款",
    "OVERDUE": "逾期", "REPAY": "还款", "CHANGE_PWD": "修改密码",
    "CHANGE_PHONE": "修改手机号", "UPDATE_PROFILE": "更新资料", "REGISTER": "注册",
    "BIND_CARD": "绑卡", "LIMIT_ADJUST": "额度调整", "DISPUTE": "争议",
    "FROZEN": "冻结", "SAR": "可疑报告", "REVIEW": "复核",
}


def _event_to_item(e: RiskEvent) -> RiskEventItem:
    """将 ORM 对象转为 RiskEventItem."""
    risk_score = float(e.risk_score) if e.risk_score else None
    # 计算风险等级
    if risk_score is not None:
        if risk_score >= 80:
            risk_level = "极高"
        elif risk_score >= 60:
            risk_level = "高"
        elif risk_score >= 30:
            risk_level = "中"
        else:
            risk_level = "低"
    else:
        risk_level = None

    return RiskEventItem(
        event_id=e.event_id,
        event_type=EVENT_TYPE_CN.get(e.event_type, e.event_type),
        user_id=e.user_id,
        card_id=e.card_id,
        device_id=e.device_id,
        ip=e.ip,
        amount=float(e.amount) if e.amount else None,
        rule_ids=e.rule_ids,
        risk_score=risk_score,
        risk_level=risk_level,
        decision=e.decision,
        action=e.action,
        status=e.status,
        handler=e.handler,
        handled_at=e.handled_at,
        remark=e.remark,
        created_at=e.created_at,
    )


@risk_router.post("/check", response_model=RiskCheckResponse)
async def api_risk_check(
    request: RiskCheckRequest,
    db: AsyncSession = Depends(get_db_async),
):
    """
    风控事件检查 — 统一入口.

    支持的事件类型:
      - 登录: LOGIN
      - 转账: TRANSFER, PAYMENT, WITHDRAW
      - 贷款: LOAN_APPLY, DISBURSE, OVERDUE
      - 信用卡: CARD_APPLY, REPAY
      - 其他: CHANGE_PWD, CHANGE_PHONE, UPDATE_PROFILE, REGISTER, BIND_CARD

    返回:
      - decision: PASS(放行) / CHALLENGE(增强验证) / MANUAL(人工复核) / REJECT(拒绝)
      - final_score: 0-100 风险分值
      - risk_level: 低/中/高/极高
      - triggered_rules: 命中的规则列表
      - features: 30 维特征 (可脱敏)
    """
    try:
        return await process_event(db, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"风控检查异常: {str(e)}")


@risk_router.get("/health")
async def health_check():
    """健康检查."""
    return {"status": "ok", "service": "bank-risk-control"}


@risk_router.get("/events", response_model=RiskEventListResponse)
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    decision: str | None = Query(None, description="决策筛选: PASS/CHALLENGE/MANUAL/REJECT"),
    event_type: str | None = Query(None, description="事件类型筛选"),
    risk_level: str | None = Query(None, description="风险等级筛选: 低/中/高/极高"),
    user_id: str | None = Query(None, description="用户ID精确搜索"),
    db: AsyncSession = Depends(get_db_async),
):
    """分页查询风险事件列表, 支持多维度筛选."""
    where_clauses = []
    if decision:
        where_clauses.append(RiskEvent.decision == decision)
    if event_type:
        where_clauses.append(RiskEvent.event_type == event_type)
    if user_id:
        try:
            uid = int(user_id)
            where_clauses.append(RiskEvent.user_id == uid)
        except ValueError:
            pass

    # 风险等级筛选需要后处理
    base_stmt = select(RiskEvent)
    if where_clauses:
        base_stmt = base_stmt.where(*where_clauses)

    # 总数
    count_stmt = select(func.count()).select_from(RiskEvent)
    if where_clauses:
        count_stmt = count_stmt.where(*where_clauses)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 分页
    stmt = base_stmt.order_by(RiskEvent.created_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    # 转 items
    items = [_event_to_item(r) for r in rows]

    # 风险等级筛选 (后置)
    if risk_level:
        items = [it for it in items if it.risk_level == risk_level]
        # 重新计算 total (近似)
        total = len(items)

    return RiskEventListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@risk_router.get("/events/{event_id}", response_model=RiskEventItem)
async def get_event_detail(
    event_id: int,
    db: AsyncSession = Depends(get_db_async),
):
    """查看单个风险事件详情."""
    event = (await db.execute(
        select(RiskEvent).where(RiskEvent.event_id == event_id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail=f"风险事件不存在: {event_id}")
    return _event_to_item(event)
