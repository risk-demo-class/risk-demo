"""
银行风控系统 - 仪表盘 API
========================
GET /api/dashboard/stats — 风控大盘统计数据

返回:
  - 用户/交易/风险事件总数
  - 高风险/阻断/人工审核数量
  - 规则命中分布
  - 最近 7 天风险趋势
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import UserInfo, Transaction, RiskEvent
from app.schemas import DashboardStatsResponse

# 事件类型 → 中文名称映射
EVENT_TYPE_CN = {
    "LOGIN": "登录",
    "TRANSFER": "转账",
    "PAYMENT": "支付",
    "WITHDRAW": "取现",
    "LOAN_APPLY": "贷款申请",
    "CARD_APPLY": "信用卡申请",
    "DISBURSE": "放款",
    "OVERDUE": "逾期",
    "REPAY": "还款",
    "CHANGE_PWD": "修改密码",
    "CHANGE_PHONE": "修改手机号",
    "UPDATE_PROFILE": "更新资料",
    "REGISTER": "注册",
    "BIND_CARD": "绑卡",
    "LIMIT_ADJUST": "额度调整",
    "DISPUTE": "争议",
    "FROZEN": "冻结",
    "SAR": "可疑报告",
    "REVIEW": "复核",
}

dashboard_router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@dashboard_router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db_async),
):
    """风控大盘统计"""

    # 用户总数
    total_users = (await db.execute(
        select(func.count()).select_from(UserInfo).where(UserInfo.status == 1)
    )).scalar() or 0

    # 交易总数
    total_txns = (await db.execute(
        select(func.count()).select_from(Transaction)
    )).scalar() or 0

    # 风险事件总数
    total_events = (await db.execute(
        select(func.count()).select_from(RiskEvent)
    )).scalar() or 0

    # 高风险事件 (decision=REJECT 或 risk_score >= 80)
    high_risk = (await db.execute(
        select(func.count()).select_from(RiskEvent).where(
            RiskEvent.risk_score >= 80
        )
    )).scalar() or 0

    # 阻断数量 (decision=REJECT)
    blocked = (await db.execute(
        select(func.count()).select_from(RiskEvent).where(
            RiskEvent.decision == "REJECT"
        )
    )).scalar() or 0

    # 人工审核数量 (decision=MANUAL)
    manual = (await db.execute(
        select(func.count()).select_from(RiskEvent).where(
            RiskEvent.decision == "MANUAL"
        )
    )).scalar() or 0

    # 规则命中分布 (按 event_type 分组 + 计数)
    rule_dist = (await db.execute(
        select(
            RiskEvent.event_type,
            func.count().label("cnt"),
        ).where(
            RiskEvent.rule_ids.isnot(None)
        ).group_by(RiskEvent.event_type).order_by(func.count().desc())
    )).all()

    # 最近 7 天趋势
    since = datetime.now() - timedelta(days=7)
    trend = (await db.execute(
        select(
            func.date(RiskEvent.created_at).label("day"),
            func.count().label("cnt"),
            func.sum(case((RiskEvent.decision == "REJECT", 1), else_=0)).label("blocked"),
        ).where(
            RiskEvent.created_at >= since
        ).group_by("day").order_by("day")
    )).all()

    # 最近事件 (供前端表格展示)
    recent_stmt = (
        select(RiskEvent)
        .order_by(RiskEvent.created_at.desc())
        .limit(10)
    )
    recent_rows = (await db.execute(recent_stmt)).scalars().all()
    recent_events = []
    for r in recent_rows:
        risk_score = float(r.risk_score) if r.risk_score else 0
        if risk_score >= 80:
            risk_level = "极高"
        elif risk_score >= 60:
            risk_level = "高"
        elif risk_score >= 30:
            risk_level = "中"
        else:
            risk_level = "低"
        recent_events.append({
            "event_id": r.event_id,
            "event_type": EVENT_TYPE_CN.get(r.event_type, r.event_type),
            "user_id": r.user_id,
            "card_id": r.card_id,
            "device_id": r.device_id,
            "ip": r.ip,
            "amount": float(r.amount) if r.amount else None,
            "rule_ids": r.rule_ids,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "decision": r.decision,
            "action": r.action,
            "created_at": str(r.created_at) if r.created_at else None,
        })

    return DashboardStatsResponse(
        total_users=total_users,
        total_transactions=total_txns,
        total_risk_events=total_events,
        high_risk_count=high_risk,
        blocked_count=blocked,
        manual_review_count=manual,
        rule_hit_distribution=[
            {"rule_name": EVENT_TYPE_CN.get(row[0], row[0] or "未知"), "count": row[1]}
            for row in rule_dist
        ],
        risk_event_trend=[
            {"date": str(row[0]), "total": row[1], "blocked": row[2] or 0, "high_risk": row[2] or 0}
            for row in trend
        ],
        recent_events=recent_events,
    )
