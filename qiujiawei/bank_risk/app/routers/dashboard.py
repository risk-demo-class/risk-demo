"""仪表盘统计 API"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.database import get_db_async
from bank_risk.app.models import RiskAssessment, RiskCase, RiskRule, Transaction, UserInfo


dashboard_router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])


@dashboard_router.get("")
async def api_dashboard(db: AsyncSession = Depends(get_db_async)):
    """返回统计数据: 总用户数/总交易数/待审案件数/今日评估数/规则命中分布等."""
    today = datetime.now().date()

    # 基础计数
    total_users = int((await db.execute(
        select(func.count()).select_from(UserInfo)
    )).scalar() or 0)
    total_transactions = int((await db.execute(
        select(func.count()).select_from(Transaction)
    )).scalar() or 0)
    pending_cases = int((await db.execute(
        select(func.count()).select_from(RiskCase).where(RiskCase.case_status == "待审核")
    )).scalar() or 0)
    today_assessments = int((await db.execute(
        select(func.count()).select_from(RiskAssessment)
        .where(func.date(RiskAssessment.create_time) == today)
    )).scalar() or 0)

    # 风险等级分布
    risk_level_rows = (await db.execute(
        select(RiskAssessment.risk_level, func.count())
        .group_by(RiskAssessment.risk_level)
    )).all()
    risk_level_distribution = {level: int(cnt) for level, cnt in risk_level_rows if level}

    # 规则命中分布: 解析最近 500 条评估的 rule_results JSON, 按 rule_id 计数
    rule_hit_distribution = await _rule_hit_distribution(db)

    return {
        "total_users": total_users,
        "total_transactions": total_transactions,
        "pending_cases": pending_cases,
        "today_assessments": today_assessments,
        "risk_level_distribution": risk_level_distribution,
        "rule_hit_distribution": rule_hit_distribution,
    }


async def _rule_hit_distribution(db: AsyncSession, recent_limit: int = 500) -> list:
    """解析最近 N 条评估的 rule_results JSON, 统计各规则命中次数."""
    rows = (await db.execute(
        select(RiskAssessment.rule_results)
        .order_by(RiskAssessment.create_time.desc())
        .limit(recent_limit)
    )).all()
    counter: dict[str, int] = {}
    for r in rows:
        if not r.rule_results:
            continue
        try:
            hits = json.loads(r.rule_results)
        except (json.JSONDecodeError, TypeError):
            continue
        for hit in hits:
            rid = hit.get("rule_id") if isinstance(hit, dict) else None
            if rid:
                counter[rid] = counter.get(rid, 0) + 1

    # 批量补 rule_name (避免 N+1)
    name_map: dict[str, str] = {}
    if counter:
        names = (await db.execute(
            select(RiskRule.rule_id, RiskRule.rule_name)
            .where(RiskRule.rule_id.in_(list(counter.keys())))
        )).all()
        name_map = {n.rule_id: n.rule_name for n in names}

    return [
        {"rule_id": rid, "rule_name": name_map.get(rid, rid), "hit_count": cnt}
        for rid, cnt in sorted(counter.items(), key=lambda x: x[1], reverse=True)
    ]
