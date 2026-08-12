"""生成可重复的旅游业务演示数据（默认 120 个用户）。"""
import argparse
import asyncio
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import (
    FlightBooking, HotelBooking, OrderPassenger, PassengerInfo, PaymentRecord,
    TravelOrder, TravelUser, VisaApplication,
)


async def generate(count: int = 120, reset: bool = False) -> dict:
    random.seed(20260811)
    stats = {"users": 0, "orders": 0, "payments": 0}
    async with AsyncSessionLocal() as db:
        if reset:
            for model in (PaymentRecord, VisaApplication, HotelBooking, FlightBooking,
                          OrderPassenger, PassengerInfo, TravelOrder, TravelUser):
                await db.execute(model.__table__.delete())
            await db.commit()

        for i in range(1, count + 1):
            uid = f"TU{i:06d}"
            if await db.scalar(select(TravelUser.user_id).where(TravelUser.user_id == uid)):
                continue
            risk_kind = "normal"
            if i % 20 == 0:
                risk_kind = "scalper"
            elif i % 15 == 0:
                risk_kind = "visa"
            elif i % 10 == 0:
                risk_kind = "new"

            register_days = 2 if risk_kind == "new" else random.randint(60, 1500)
            user = TravelUser(
                user_id=uid, name=f"游客{i}", phone_hash=f"phone_{i:06d}",
                real_name_status=0 if risk_kind == "scalper" else 1,
                vip_level=random.randint(0, 3),
                register_time=datetime.now() - timedelta(days=register_days),
            )
            db.add(user)
            # ORM 显式声明了外键；这里先刷新父记录，让脚本即使面对既有手工建表
            # 或不同 SQLAlchemy 版本，也始终按用户 → 订单 → 子表的顺序写入。
            await db.flush()
            stats["users"] += 1

            order_type = "签证" if risk_kind == "visa" else ("机票" if i % 2 else "酒店")
            amount = 60000 if risk_kind == "scalper" else (18000 if risk_kind == "new" else random.randint(800, 9000))
            country = random.choice(["中国", "日本", "泰国", "新加坡", "法国"])
            oid = f"TO{i:06d}"
            depart = date.today() + timedelta(days=3 if risk_kind == "scalper" else random.randint(10, 90))
            order = TravelOrder(
                order_id=oid, user_id=uid, order_type=order_type, total_amount=amount,
                dest_country=country, depart_date=depart,
                return_date=depart + timedelta(days=random.randint(3, 14)),
                passenger_count=5 if risk_kind == "scalper" else 1,
                order_status="已支付", create_time=datetime.now() - timedelta(days=random.randint(0, 25)),
            )
            db.add(order)
            await db.flush()
            pid = f"TP{i:06d}"
            db.add(PassengerInfo(passenger_id=pid, user_id=uid, name=f"乘客{i}",
                                 id_type="护照", id_number_hash=f"passport_{i:06d}", nationality="中国"))
            await db.flush()
            db.add(OrderPassenger(order_id=oid, passenger_id=pid))

            if order_type == "机票":
                db.add(FlightBooking(
                    booking_id=f"FB{i:06d}", order_id=oid,
                    flight_no="TG6001" if risk_kind == "scalper" else f"CA{1000+i%50}",
                    depart_airport="PVG", arrive_airport="BKK" if country != "中国" else "PEK",
                    depart_time=datetime.combine(depart, datetime.min.time()) + timedelta(hours=10),
                    ticket_count=5 if risk_kind == "scalper" else 1,
                ))
            elif order_type == "酒店":
                db.add(HotelBooking(
                    booking_id=f"HB{i:06d}", order_id=oid, hotel_id=f"HOTEL{i%20:03d}",
                    city="东京" if country == "日本" else "上海", check_in=depart,
                    check_out=depart + timedelta(days=4), room_count=1,
                    is_refundable=0 if risk_kind == "new" else 1,
                ))
            else:
                # 高风险签证用户准备两条历史拒签和一条当前申请。
                if risk_kind == "visa":
                    db.add_all([
                        VisaApplication(visa_id=f"VA{i:06d}A", order_id=oid, user_id=uid,
                                        dest_country="美国", visa_type="旅游", application_status="拒签",
                                        submit_time=datetime.now() - timedelta(days=50)),
                        VisaApplication(visa_id=f"VA{i:06d}B", order_id=oid, user_id=uid,
                                        dest_country="加拿大", visa_type="旅游", application_status="拒签",
                                        submit_time=datetime.now() - timedelta(days=15)),
                    ])
                db.add(VisaApplication(visa_id=f"VA{i:06d}", order_id=oid, user_id=uid,
                                       dest_country=country, visa_type="旅游", application_status="待审核"))

            db.add(PaymentRecord(
                payment_id=f"PAY{i:06d}", order_id=oid, user_id=uid,
                payment_account_hash="acct_scalper_shared" if risk_kind == "scalper" else f"acct_{i:06d}",
                amount=amount, device_id="DEV_SHARED" if risk_kind == "scalper" else f"DEV{i:06d}",
                ip="10.0.0.9" if risk_kind == "scalper" else f"10.0.{i//250}.{i%250+1}",
                payment_time=datetime.now() - timedelta(minutes=random.randint(0, 30)),
            ))
            stats["orders"] += 1
            stats["payments"] += 1
            if i % 50 == 0:
                await db.commit()
        await db.commit()
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=120)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    print(asyncio.run(generate(args.count, args.reset)))
