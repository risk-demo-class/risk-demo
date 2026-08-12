"""
生成旅游业务数据.

默认生成 150 个用户和 500 笔订单, 覆盖机票/酒店/签证/跟团游/团票.
"""

import argparse
import asyncio
import logging
import random
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import delete

from app.database import AsyncSessionLocal, async_engine
from app.models import (
    BookingFlight,
    BookingHotel,
    DeviceFingerprint,
    GroupBooking,
    HotelPreauthorization,
    OrderInfo,
    PassengerInfo,
    TicketChangeApplication,
    UserInfo,
    VisaApplication,
)

logger = logging.getLogger(__name__)

ORDER_TYPES = ["机票", "酒店", "签证", "跟团游", "团票"]
COUNTRIES = ["中国", "日本", "泰国", "新加坡", "法国", "美国", "英国", "澳大利亚", "意大利"]
AIRPORTS = ["北京首都", "上海浦东", "广州白云", "深圳宝安", "成都天府", "香港国际"]
HOTEL_NAMES = ["希尔顿", "洲际", "万豪", "亚朵", "全季", "如家", "汉庭"]
REMARKS = [
    "",
    "正常家庭出行",
    "公司出差",
    "多订几张，一起走",
    "内部渠道，不用查",
    "帮忙拼个团",
    "订单备注勿扰",
]


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


async def gen_business_data(
    user_count: int = 150,
    order_count: int = 500,
    reset: bool = False,
) -> None:
    """生成业务数据."""
    try:
        async with AsyncSessionLocal() as session:
            if reset:
                tables = [
                    GroupBooking,
                    HotelPreauthorization,
                    TicketChangeApplication,
                    VisaApplication,
                    BookingHotel,
                    BookingFlight,
                    PassengerInfo,
                    OrderInfo,
                    DeviceFingerprint,
                    UserInfo,
                ]
                for table in tables:
                    await session.execute(delete(table))

            now = datetime.now()
            users: list[UserInfo] = []
            for i in range(1, user_count + 1):
                user_id = f"U{i:05d}"
                register_at = now - timedelta(days=random.randint(1, 800))
                user = UserInfo(
                    user_id=user_id,
                    name=f"用户{i}",
                    real_name_status="已实名" if random.random() < 0.85 else "未实名",
                    vip_level=random.choice(["普通", "银卡", "金卡", "白金"]),
                    register_at=register_at,
                    account_age_days=(now - register_at).days,
                    phone=f"13{random.randint(100000000, 999999999)}",
                )
                session.add(user)
                users.append(user)

                device_id = f"DEV_{random.randint(1, 80):04d}"
                session.add(
                    DeviceFingerprint(
                        device_id=device_id,
                        user_id=user_id,
                        fingerprint_hash=f"FP_{uuid.uuid4().hex[:16]}",
                        first_seen=register_at,
                        last_seen=now,
                        os=random.choice(["iOS", "Android", "Windows", "macOS"]),
                        browser=random.choice(["Chrome", "Safari", "Edge"]),
                    )
                )

            await session.flush()

            orders: list[OrderInfo] = []
            for i in range(1, order_count + 1):
                user = random.choice(users)
                order_id = f"ORD_T{i:06d}"
                order_type = random.choice(ORDER_TYPES)
                depart = date.today() + timedelta(days=random.randint(1, 60))
                ret = depart + timedelta(days=random.randint(1, 14))
                amount = random.choice([1800, 3200, 6800, 12000, 26000, 58000])
                remark = random.choice(REMARKS)
                order = OrderInfo(
                    order_id=order_id,
                    user_id=user.user_id,
                    order_type=order_type,
                    total_amount=amount,
                    dest_country=random.choice(COUNTRIES),
                    depart_date=depart,
                    return_date=ret,
                    passenger_count=random.randint(1, 5),
                    pay_account=f"PAY_{random.randint(1, 100):03d}",
                    device_id=f"DEV_{random.randint(1, 80):04d}",
                    ip_address=f"10.20.{random.randint(0, 255)}.{random.randint(1, 254)}",
                    order_remark=remark,
                    order_status=random.choice(
                        ["待支付", "已支付", "已确认", "已完成", "已取消", "退改中"]
                    ),
                    create_time=now - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23)),
                    payment_time=now - timedelta(days=random.randint(0, 30)),
                )
                session.add(order)
                orders.append(order)
                await session.flush()

                for p in range(order.passenger_count):
                    session.add(
                        PassengerInfo(
                            passenger_id=f"PASS_{i}_{p + 1}",
                            order_id=order.order_id,
                            user_id=user.user_id,
                            name=f"乘客{i}_{p + 1}",
                            id_type=random.choice(["身份证", "护照", "其他"]),
                            id_number=f"ID{random.randint(100000000000000000, 999999999999999999)}",
                            passport_no=(
                                f"E{random.randint(10000000, 99999999)}"
                                if random.random() < 0.4
                                else None
                            ),
                            nationality=random.choice(["中国", "日本", "新加坡"]),
                            age=random.randint(18, 65),
                            phone=f"13{random.randint(100000000, 999999999)}",
                        )
                    )

                if order_type in ("机票", "团票", "跟团游"):
                    session.add(
                        BookingFlight(
                            booking_id=f"FLY_{i}",
                            order_id=order.order_id,
                            flight_no=f"CA{random.randint(1000, 9999)}",
                            depart_airport=random.choice(AIRPORTS),
                            arrive_airport=random.choice(AIRPORTS),
                            depart_time=datetime.combine(depart, datetime.min.time())
                            + timedelta(hours=random.randint(6, 22)),
                            cabin_class=random.choice(["经济舱", "超级经济舱", "公务舱"]),
                            amount=amount / max(order.passenger_count, 1),
                            refundable=1 if random.random() < 0.7 else 0,
                        )
                    )

                if order_type == "酒店":
                    session.add(
                        BookingHotel(
                            booking_id=f"HTL_{i}",
                            order_id=order.order_id,
                            hotel_id=f"HOTEL_{random.randint(1, 50):03d}",
                            hotel_name=random.choice(HOTEL_NAMES),
                            check_in=depart,
                            check_out=ret,
                            room_count=random.randint(1, 3),
                            is_refundable=1 if random.random() < 0.8 else 0,
                            amount=amount,
                        )
                    )
                    session.add(
                        HotelPreauthorization(
                            preauth_id=f"PAUTH_{i}",
                            order_id=order.order_id,
                            user_id=user.user_id,
                            hotel_id=f"HOTEL_{random.randint(1, 50):03d}",
                            preauth_amount=amount,
                            actual_amount=amount
                            if random.random() < 0.8
                            else amount * random.uniform(0.8, 1.2),
                            status=random.choice(["待确认", "已确认", "已释放", "异常"]),
                        )
                    )

                if order_type == "签证":
                    session.add(
                        VisaApplication(
                            visa_id=f"VISA_{i}",
                            user_id=user.user_id,
                            dest_country=order.dest_country or "日本",
                            visa_type=random.choice(["旅游签", "商务签", "学生签"]),
                            passport_no=f"E{random.randint(10000000, 99999999)}",
                            reject_history=1 if random.random() < 0.05 else 0,
                            submit_time=order.create_time,
                            status=random.choice(["审核中", "通过", "拒绝"]),
                        )
                    )

                if order_type == "团票":
                    session.add(
                        GroupBooking(
                            group_id=f"GROUP_{i}",
                            order_id=order.order_id,
                            leader_user_id=user.user_id,
                            member_count=random.randint(3, 20),
                            total_amount=amount,
                        )
                    )

                if order_type == "机票" and random.random() < 0.15:
                    session.add(
                        TicketChangeApplication(
                            change_id=f"CHG_{i}",
                            order_id=order.order_id,
                            user_id=user.user_id,
                            change_type=random.choice(["改签", "退票", "其他"]),
                            old_flight_no=f"CA{random.randint(1000, 9999)}",
                            new_flight_no=f"CA{random.randint(1000, 9999)}",
                            old_amount=amount,
                            new_amount=amount * random.uniform(0.5, 1.8),
                            apply_time=order.create_time + timedelta(hours=random.randint(1, 48)),
                            status=random.choice(["待审核", "已通过", "已拒绝"]),
                        )
                    )

            await session.commit()
            logger.info(
                "业务数据生成完成: users=%d orders=%d",
                len(users),
                len(orders),
            )
    except Exception:
        logger.exception("业务数据生成失败")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="生成旅游业务数据")
    parser.add_argument("--users", type=int, default=150)
    parser.add_argument("--orders", type=int, default=500)
    parser.add_argument("--reset", action="store_true", help="先清空业务表")
    args = parser.parse_args()

    async def _main() -> None:
        try:
            await gen_business_data(args.users, args.orders, args.reset)
        finally:
            await async_engine.dispose()

    asyncio.run(_main())


if __name__ == "__main__":
    main()
