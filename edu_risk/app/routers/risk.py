"""风险检查接口 — 核心入口"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.service.event import process_event

router = APIRouter(prefix="/api/risk", tags=["风控检查"])


class RiskCheckRequest(BaseModel):
    event_type: str = Field(..., description="事件类型: 报名/缴费/退费/考试/作业")
    source_id: str = Field(..., description="业务单据号: 报名单/缴费单/退费单/考试记录/作业记录")
    user_id: str = Field(..., description="学员 ID")
    extra: dict = Field(default_factory=dict, description="附加信息")


@router.post("/check")
async def risk_check(payload: RiskCheckRequest, db: AsyncSession = Depends(get_db)):
    """触发一次 7 步风控检查。"""
    return await process_event(db, payload.model_dump())


@router.get("/check/{event_id}")
async def get_event_result(event_id: str, db: AsyncSession = Depends(get_db)):
    """查询一次检查的完整结果(事件+特征+评估)。"""
    from sqlalchemy import select
    from app.models import RiskAssessment, RiskEvent, RiskFeature
    r = await db.execute(select(RiskEvent).where(RiskEvent.event_id == event_id))
    event = r.scalar_one_or_none()
    if not event:
        from fastapi import HTTPException
        raise HTTPException(404, f"事件不存在: {event_id}")
    feats = (await db.execute(
        select(RiskFeature).where(RiskFeature.event_id == event_id))).scalars().all()
    asm = (await db.execute(
        select(RiskAssessment).where(RiskAssessment.event_id == event_id))).scalar_one_or_none()
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "user_id": event.user_id,
        "source_id": event.source_id,
        "create_time": event.create_time.isoformat(),
        "features": {f.feature_name: float(f.feature_value) for f in feats},
        "assessment": {
            "rule_score": float(asm.rule_score) if asm else None,
            "ml_score": float(asm.ml_score) if asm else None,
            "final_score": float(asm.final_score) if asm else None,
            "risk_level": asm.risk_level if asm else None,
            "decision": asm.decision if asm else None,
        },
    }
