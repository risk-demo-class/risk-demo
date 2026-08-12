"""风控检查 API (核心入口: /api/risk/check)"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.models import (
    TelecomCdr,
    TelecomCard,
    TelecomIotCard,
    TelecomServiceOrder,
    TelecomSms,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.event import process_event


risk_router = APIRouter(prefix="/api/risk", tags=["风控检查"])


@risk_router.post("/check", response_model=RiskCheckResponse)
async def api_risk_check(request: RiskCheckRequest, db: AsyncSession = Depends(get_db_async)):
    """风控检查: 7 步流水线 (校验 → 黑名单 → 事件 → 特征 → 规则 → 决策 → 落库)."""
    return await process_event(db, request)


@risk_router.get("/suggest-source-id")
async def api_suggest_source_id(
    msisdn: str,
    event_type: str,
    db: AsyncSession = Depends(get_db_async),
):
    """根据 msisdn + event_type 自动推荐 source_id (供前端空白填充)."""
    if not msisdn or not event_type:
        raise HTTPException(status_code=400, detail="msisdn 和 event_type 必填")

    # 1) 先确保号卡存在
    card = (await db.execute(
        select(TelecomCard.msisdn).where(TelecomCard.msisdn == msisdn).limit(1)
    )).first()
    if not card:
        raise HTTPException(status_code=404, detail=f"号卡不存在: {msisdn}")

    # 2) 按事件类型查找业务记录
    if event_type in ("通话", "国际来电"):
        row = (await db.execute(
            select(TelecomCdr.cdr_id).where(TelecomCdr.calling_no == msisdn).limit(1)
        )).first()
        if row:
            return {"source_id": str(row[0]), "field_label": "通话记录ID"}
        row = (await db.execute(
            select(TelecomCdr.cdr_id).where(TelecomCdr.called_no == msisdn).limit(1)
        )).first()
        if row:
            return {"source_id": str(row[0]), "field_label": "通话记录ID"}
    elif event_type == "开户":
        row = (await db.execute(
            select(TelecomServiceOrder.order_id).where(TelecomServiceOrder.msisdn == msisdn).limit(1)
        )).first()
        if row:
            return {"source_id": str(row[0]), "field_label": "业务单号"}
    elif event_type == "短信发送":
        row = (await db.execute(
            select(TelecomSms.sms_id).where(TelecomSms.sending_no == msisdn).limit(1)
        )).first()
        if row:
            return {"source_id": str(row[0]), "field_label": "短信ID"}
    elif event_type == "物联网激活":
        row = (await db.execute(
            select(TelecomIotCard.msisdn).where(TelecomIotCard.msisdn == msisdn).limit(1)
        )).first()
        if row:
            return {"source_id": str(row[0]), "field_label": "物联网卡ID"}

    raise HTTPException(status_code=404, detail=f"未找到号卡 {msisdn} 的 {event_type} 业务记录")
