"""
生成高风险旅游用户画像.

覆盖: 拒签历史 / 连续退改 / 同设备多账号订酒店 / 黄牛囤票 / 黑护照 / 新用户大单.
"""

import argparse
import asyncio
import logging
import random
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal, async_engine
from app.models import (
    BookingFlight,
    DeviceFingerprint,
    OrderInfo,
    PassengerInfo,
    RiskBlacklist,
    TicketChangeApplication,
    UserInfo,
    VisaApplication,
)

logger = logging.getLogger(__name__)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


async def _ensure_user(db, user_id: str, name: str, register_at: datetime) -> None:
    existing = (
        await db.execute(select(UserInfo).where(UserInfo.user_id == user_id).limit(1))
    ).scalar_one_or_none()
    if existing:
        return
    db.add(
        UserInfo(
            user_id=user_id,
            name=name,
            real_name_status="已实名",
            vip_level="普通",
            register_at=register_at,
            account_age_days=(datetime.now() - register_at).days,
            phone=f"139{uuid.uuid4().hex[:8]}",
        )
    )
    await db.flush()


async def _add_order(
    db,
    order_id: str,
    user_id: str,
    order_type: str,
    amount: float,
    device_id: str,
    pay_account: str,
    remark: str = "",
    create_time: datetime | None = None,
) -> None:
    now = create_time or datetime.now()
    db.add(
        OrderInfo(
            order_id=order_id,
            user_id=user_id,
            order_type=order_type,
            total_amount=amount,
            dest_country="日本",
            depart_date=date.today() + timedelta(days=3),
            return_date=date.today() + timedelta(days=8),
            passenger_count=1,
            pay_account=pay_account,
            device_id=device_id,
            ip_address="10.88.0.1",
            order_remark=remark,
            order_status="已支付",
            create_time=now,
            payment_time=now,
        )
    )
    await db.flush()


async def gen_risky_users() -> None:
    """生成 6 个高风险用户."""
    try:
        async with AsyncSessionLocal() as db:
            now = datetime.now()

            # RISK001: 连续退改套利
            await _ensure_user(db, "RISK001", "退改套利用户", now - timedelta(days=120))
            for i in range(1, 6):
                order_id = f"RISK001_ORD_{i}"
                await _add_order(
                    db,
                    order_id,
                    "RISK001",
                    "机票",
                    8000,
                    "DEV_RISK001",
                    "PAY_RISK001",
                    create_time=now - timedelta(days=i * 2),
                )
                db.add(
                    TicketChangeApplication(
                        change_id=f"RISK001_CHG_{i}",
                        order_id=order_id,
                        user_id="RISK001",
                        change_type="改签",
                        old_flight_no="CA1001",
                        new_flight_no="CA1002",
                        old_amount=8000,
                        new_amount=12000,
                        apply_time=now - timedelta(days=i * 2, hours=2),
                        status="已通过",
                    )
                )

            # RISK002: 拒签历史
            await _ensure_user(db, "RISK002", "拒签高频用户", now - timedelta(days=200))
            for country in ["日本", "法国", "美国"]:
                db.add(
                    VisaApplication(
                        visa_id=f"RISK002_VISA_{country}",
                        user_id="RISK002",
                        dest_country=country,
                        visa_type="旅游签",
                        passport_no="E88888888",
                        reject_history=1,
                        submit_time=now - timedelta(days=random.randint(1, 60)),
                        status="拒绝",
                    )
                )

            # RISK003: 同设备多账号订酒店
            for i, uid in enumerate(["RISK003", "RISK003B", "RISK003C"]):
                await _ensure_user(db, uid, f"设备聚集用户{i}", now - timedelta(days=60))
                db.add(
                    DeviceFingerprint(
                        device_id="DEV_SHARED_HOTEL",
                        user_id=uid,
                        fingerprint_hash=f"FP_SHARED_{i}",
                        first_seen=now - timedelta(days=30),
                        last_seen=now,
                    )
                )
                await _add_order(
                    db,
                    f"RISK003_ORD_{uid}",
                    uid,
                    "酒店",
                    5000,
                    "DEV_SHARED_HOTEL",
                    f"PAY_{uid}",
                    create_time=now - timedelta(days=i),
                )

            # RISK004: 黄牛囤票, 同一支付账号 1 小时多单
            await _ensure_user(db, "RISK004", "黄牛囤票用户", now - timedelta(days=30))
            for i in range(1, 7):
                order_id = f"RISK004_ORD_{i}"
                await _add_order(
                    db,
                    order_id,
                    "RISK004",
                    "机票",
                    2600,
                    "DEV_RISK004",
                    "PAY_SCALPER",
                    remark="多订几张，一起走",
                    create_time=now - timedelta(minutes=i * 5),
                )
                db.add(
                    BookingFlight(
                        booking_id=f"RISK004_FLY_{i}",
                        order_id=order_id,
                        flight_no="CA6666",
                        depart_airport="北京首都",
                        arrive_airport="东京成田",
                        depart_time=now + timedelta(days=3),
                        cabin_class="经济舱",
                        amount=2600,
                        refundable=1,
                    )
                )

            # RISK005: 黑护照
            await _ensure_user(db, "RISK005", "黑护照用户", now - timedelta(days=90))
            await _add_order(
                db,
                "RISK005_ORD_1",
                "RISK005",
                "机票",
                12000,
                "DEV_RISK005",
                "PAY_RISK005",
            )
            db.add(
                PassengerInfo(
                    passenger_id="PASS_RISK005",
                    order_id="RISK005_ORD_1",
                    user_id="RISK005",
                    name="黑名单乘客",
                    id_type="护照",
                    id_number="ID_BLACK_PASSPORT",
                    passport_no="P_BLACK_001",
                    nationality="中国",
                    age=35,
                )
            )
            db.add(
                RiskBlacklist(
                    blacklist_type="护照号",
                    blacklist_value="P_BLACK_001",
                    reason="高风险护照",
                )
            )

            # RISK006: 新用户大单
            await _ensure_user(db, "RISK006", "新用户大单", now - timedelta(days=2))
            await _add_order(
                db,
                "RISK006_ORD_1",
                "RISK006",
                "跟团游",
                58000,
                "DEV_RISK006",
                "PAY_RISK006",
            )

            await db.commit()
            logger.info("高风险用户生成完成: 6 个")
    except Exception:
        logger.exception("高风险用户生成失败")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="生成高风险旅游用户")
    parser.parse_args()

    async def _main() -> None:
        try:
            await gen_risky_users()
        finally:
            await async_engine.dispose()

    asyncio.run(_main())


if __name__ == "__main__":
    main()
