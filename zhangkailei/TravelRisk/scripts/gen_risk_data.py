"""从旅游业务表抽取事件，执行真实风控流水线并生成评估数据。"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import FlightBooking, HotelBooking, PaymentRecord, TravelOrder, VisaApplication
from app.schemas import RiskCheckRequest
from app.service.event import process_event


async def generate(limit: int = 100) -> dict:
    events: list[tuple[str, str, str]] = []
    async with AsyncSessionLocal() as db:
        for cls, field, event_type in (
            (FlightBooking, FlightBooking.booking_id, "机票预订"),
            (HotelBooking, HotelBooking.booking_id, "酒店预订"),
            (VisaApplication, VisaApplication.visa_id, "签证申请"),
            (PaymentRecord, PaymentRecord.payment_id, "订单支付"),
        ):
            rows = (await db.execute(select(cls).limit(limit))).scalars().all()
            for row in rows:
                if hasattr(row, "user_id"):
                    uid = row.user_id
                else:
                    uid = await db.scalar(select(TravelOrder.user_id).where(
                        TravelOrder.order_id == row.order_id))
                events.append((event_type, getattr(row, field.key), uid))

    ok = high = failed = 0
    for event_type, source_id, user_id in events[:limit]:
        async with AsyncSessionLocal() as db:
            try:
                result = await process_event(db, RiskCheckRequest(
                    event_type=event_type, source_id=source_id, user_id=user_id))
                ok += 1
                high += int(result.decision in ("人工审核", "拒绝"))
            except Exception as exc:
                failed += 1
                print(f"FAILED {event_type}/{source_id}: {exc}")
    return {"success": ok, "high_risk": high, "failed": failed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()
    print(asyncio.run(generate(args.count)))
