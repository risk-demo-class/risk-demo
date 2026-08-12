"""
旅游风控系统 - OTA 业务数据生成脚本。

生成 7 张旅游业务表的数据，并在每次运行前清空旧业务数据，保证脚本可重复执行。

用法:
    python scripts/gen_business_data.py
    python scripts/gen_business_data.py --count 120
    python scripts/gen_business_data.py --count 300 --users 30
"""
import argparse
import asyncio
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from faker import Faker
from sqlalchemy import delete

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import AsyncSessionLocal, async_engine
from app.models import (
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    OrderInfo,
    PassengerInfo,
    UserInfo,
    VisaApplication,
)


COUNTRIES = ["中国", "日本", "泰国", "新加坡", "法国", "英国", "澳大利亚", "美国"]
AIRPORTS = ["PEK", "PVG", "CAN", "SZX", "CTU", "HND", "BKK", "SIN", "CDG", "LHR"]
ORDER_TYPES = ["机票", "酒店", "签证", "跟团游"]
VISA_TYPES = ["旅游签", "商务签", "探亲签", "电子签"]
CABIN_CLASSES = ["经济舱", "超级经济舱", "公务舱", "头等舱"]
ID_TYPES = ["身份证", "护照", "港澳通行证"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 OTA 旅游业务测试数据")
    parser.add_argument("--count", type=int, default=120, help="订单数，默认 120")
    parser.add_argument("--users", type=int, default=10, help="用户数，默认 10")
    return parser.parse_args()


def _validate_args(order_count: int, user_count: int) -> None:
    if order_count <= 0:
        raise ValueError("--count 必须大于 0")
    if user_count <= 0:
        raise ValueError("--users 必须大于 0")


def _build_users(fake: Faker, user_count: int, now: datetime) -> list[UserInfo]:
    users: list[UserInfo] = []
    for index in range(1, user_count + 1):
        is_risk = index <= 5
        user_id = f"RISK{index:03d}" if is_risk else f"TRAVEL{index:04d}"
        account_age_days = random.randint(1, 1500)
        users.append(UserInfo(
            user_id=user_id,
            name=f"RISK_{fake.name()}" if is_risk else fake.name(),
            real_name_status="已认证" if is_risk else random.choice(["未实名", "已实名", "已认证"]),
            vip_level=random.randint(0, 5),
            account_age_days=account_age_days,
            phone=f"13{index:09d}"[-11:],
            register_time=now - timedelta(days=account_age_days),
        ))
    return users


def _build_id_number(user_id: str, order_index: int, passenger_index: int) -> str:
    """生成脱敏证件号；RISK005 的首位乘客使用固定黑名单护照号。"""
    if user_id == "RISK005" and order_index < 10 and passenger_index == 1:
        return "P-BLACK-RISK005"
    return f"ID-{user_id}-{order_index:05d}-{passenger_index:02d}"


def _build_orders_and_details(
    users: list[UserInfo],
    order_count: int,
    now: datetime,
) -> tuple[list[OrderInfo], list[PassengerInfo], list[VisaApplication], list[BookingHotel], list[BookingFlight]]:
    orders: list[OrderInfo] = []
    passengers: list[PassengerInfo] = []
    visas: list[VisaApplication] = []
    hotels: list[BookingHotel] = []
    flights: list[BookingFlight] = []

    for index in range(1, order_count + 1):
        user = users[(index - 1) % len(users)]
        order_id = f"TRV{index:06d}"
        order_type = ORDER_TYPES[(index - 1) % len(ORDER_TYPES)]
        destination = random.choice(COUNTRIES[1:])
        book_time = now - timedelta(days=random.randint(0, 89), hours=random.randint(0, 23))
        amount = Decimal(str(round(random.uniform(300, 18000), 2)))

        # 高风险场景 3: RISK003 单笔大额跨境游。
        if user.user_id == "RISK003" and not any(o.user_id == "RISK003" for o in orders):
            order_type = "跟团游"
            destination = "法国"
            amount = Decimal("68888.00")

        # 高风险场景 4: RISK004 凌晨突击下单。
        if user.user_id == "RISK004" and not any(o.user_id == "RISK004" for o in orders):
            book_time = now.replace(hour=2, minute=15, second=0, microsecond=0) - timedelta(days=1)

        depart_date = date.today() + timedelta(days=random.randint(1, 90))
        return_date = depart_date + timedelta(days=random.randint(1, 14))
        passenger_count = random.randint(1, 5)
        orders.append(OrderInfo(
            order_id=order_id,
            user_id=user.user_id,
            order_type=order_type,
            total_amount=amount,
            dest_country=destination,
            depart_date=depart_date,
            return_date=return_date,
            passenger_count=passenger_count,
            book_time=book_time,
        ))

        for passenger_index in range(1, passenger_count + 1):
            passengers.append(PassengerInfo(
                passenger_id=f"PSG{index:06d}{passenger_index:02d}",
                order_id=order_id,
                name=f"乘客{index:04d}_{passenger_index}",
                id_type="护照" if destination != "中国" else random.choice(ID_TYPES),
                id_number=_build_id_number(user.user_id, index, passenger_index),
                nationality="中国",
                age=random.randint(2, 75),
            ))

        if order_type == "签证":
            visas.append(VisaApplication(
                visa_id=f"VISA{index:06d}",
                user_id=user.user_id,
                dest_country=destination,
                visa_type=random.choice(VISA_TYPES),
                reject_history=random.randint(0, 1),
                submit_time=book_time,
            ))
        elif order_type == "酒店":
            hotels.append(BookingHotel(
                booking_id=f"HTL{index:06d}",
                order_id=order_id,
                hotel_id=f"HOTEL{random.randint(1, 40):04d}",
                check_in=depart_date,
                check_out=return_date,
                room_count=max(1, (passenger_count + 1) // 2),
                is_refundable=random.choice([True, False]),
            ))
        elif order_type == "机票":
            depart_airport, arrive_airport = random.sample(AIRPORTS, 2)
            flights.append(BookingFlight(
                booking_id=f"FLT{index:06d}",
                order_id=order_id,
                flight_no=f"CA{random.randint(100, 9999):04d}",
                depart_airport=depart_airport,
                arrive_airport=arrive_airport,
                cabin_class=random.choice(CABIN_CLASSES),
            ))

    return orders, passengers, visas, hotels, flights


def _inject_risk_visas(users: list[UserInfo], visas: list[VisaApplication], now: datetime) -> None:
    user_ids = {user.user_id for user in users}
    if "RISK001" in user_ids:
        visas.append(VisaApplication(
            visa_id="VISA_RISK001_REJECT",
            user_id="RISK001",
            dest_country="美国",
            visa_type="旅游签",
            reject_history=3,
            submit_time=now - timedelta(days=20),
        ))
    if "RISK002" in user_ids:
        for index, country in enumerate(["日本", "法国", "澳大利亚"], 1):
            visas.append(VisaApplication(
                visa_id=f"VISA_RISK002_{index}",
                user_id="RISK002",
                dest_country=country,
                visa_type="旅游签",
                reject_history=0,
                submit_time=now - timedelta(days=index * 5),
            ))


def _build_blacklist(users: list[UserInfo], now: datetime) -> list[BlacklistExtra]:
    user_ids = {user.user_id for user in users}
    entries = [
        BlacklistExtra(
            entry_id="BLX_DEVICE_001",
            type="设备指纹",
            value="DEVICE-RISK-GROUP-001",
            reason="同一设备短时间批量预订多个目的地",
            expire_at=now + timedelta(days=365),
        ),
        BlacklistExtra(
            entry_id="BLX_PHONE_001",
            type="手机号",
            value="13900009999",
            reason="关联多起黑卡支付投诉",
            expire_at=None,
        ),
    ]
    if "RISK005" in user_ids:
        entries.append(BlacklistExtra(
            entry_id="BLX_PASSPORT_RISK005",
            type="护照号",
            value="P-BLACK-RISK005",
            reason="证件关联历史欺诈订单",
            expire_at=None,
        ))
    return entries


async def _clear_business_tables(db) -> None:
    """按子表到父表的顺序删除，兼容未来增加外键约束。"""
    for model in (
        BookingFlight,
        BookingHotel,
        PassengerInfo,
        VisaApplication,
        BlacklistExtra,
        OrderInfo,
        UserInfo,
    ):
        await db.execute(delete(model))


async def generate_business_data(order_count: int, user_count: int) -> None:
    _validate_args(order_count, user_count)
    random.seed(20260811)
    Faker.seed(20260811)
    fake = Faker("zh_CN")
    now = datetime.now().replace(microsecond=0)

    users = _build_users(fake, user_count, now)
    orders, passengers, visas, hotels, flights = _build_orders_and_details(
        users, order_count, now,
    )
    _inject_risk_visas(users, visas, now)
    blacklist_entries = _build_blacklist(users, now)

    try:
        async with AsyncSessionLocal() as db:
            try:
                await _clear_business_tables(db)
                db.add_all(users)
                db.add_all(orders)
                db.add_all(passengers)
                db.add_all(visas)
                db.add_all(hotels)
                db.add_all(flights)
                db.add_all(blacklist_entries)
                await db.commit()
            except Exception:
                await db.rollback()
                raise
    finally:
        # Windows ProactorEventLoop 关闭前显式释放 aiomysql 连接池。
        await async_engine.dispose()

    print("旅游业务数据生成完成")
    print(f"  用户: {len(users)}")
    print(f"  订单: {len(orders)}")
    print(f"  乘客: {len(passengers)}")
    print(f"  签证申请: {len(visas)}")
    print(f"  酒店预订: {len(hotels)}")
    print(f"  航班预订: {len(flights)}")
    print(f"  扩展黑名单: {len(blacklist_entries)}")


def main() -> None:
    args = _parse_args()
    asyncio.run(generate_business_data(args.count, args.users))


if __name__ == "__main__":
    main()
