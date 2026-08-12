"""补全设备、IP 等后续特征计算需要的上下文。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_business import DeviceFingerprint, IpGeoLocation
from app.service.context import RiskContext


async def enrich_request_context(db: AsyncSession, context: RiskContext) -> RiskContext:
    if context.device_id:
        result = await db.execute(
            select(DeviceFingerprint)
            .where(
                DeviceFingerprint.device_id == context.device_id,
                DeviceFingerprint.user_id == context.request.user_id,
            )
            .order_by(DeviceFingerprint.first_seen.asc())
            .limit(1)
        )
        context.device = result.scalar_one_or_none()

    if context.ip:
        context.ip_info = await db.get(IpGeoLocation, context.ip)

    return context

