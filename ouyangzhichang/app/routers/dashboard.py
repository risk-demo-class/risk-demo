"""物流风控仪表盘统计接口。"""
import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import RiskAssessment, RiskCase

dashboard_router = APIRouter(prefix="/api/dashboard", tags=["仪表盘"])

@dashboard_router.get("/overview")
async def api_dashboard_overview(db: AsyncSession = Depends(get_db_async)):
    today=datetime.combine(date.today(),datetime.min.time())
    rows=(await db.execute(select(RiskAssessment).where(
        RiskAssessment.create_time>=today-timedelta(days=6)))).scalars().all()
    today_rows=[r for r in rows if r.create_time and r.create_time>=today]
    pending=await db.scalar(select(func.count()).select_from(RiskCase).where(
        RiskCase.case_status.in_(["待审核","审核中"]))) or 0
    trend=[]
    for offset in range(6,-1,-1):
        day=date.today()-timedelta(days=offset)
        daily=[r for r in rows if r.create_time and r.create_time.date()==day]
        trend.append({"date":day.isoformat(),"count":len(daily),
                      "high_risk_count":sum(r.decision in ("人工审核","拒绝") for r in daily)})
    counts={}
    for assessment in rows:
        try: hits=json.loads(assessment.rule_results or "[]")
        except (json.JSONDecodeError,TypeError): hits=[]
        for hit in hits:
            name=hit.get("rule_name") or hit.get("rule_id") or "未知规则"
            counts[name]=counts.get(name,0)+1
    top_rules=[{"rule_name":name,"hit_count":count} for name,count in
               sorted(counts.items(),key=lambda item:item[1],reverse=True)[:5]]
    passed=sum(r.decision=="通过" for r in today_rows)
    return {"today_assessments":len(today_rows),
            "today_high_risk":sum(r.decision in ("人工审核","拒绝") for r in today_rows),
            "pending_cases":int(pending),
            "pass_rate":round(passed/len(today_rows)*100,1) if today_rows else 0,
            "trend_7d":trend,"top_rules":top_rules}
