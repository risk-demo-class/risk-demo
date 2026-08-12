"""
旅游风控系统 - 业务数据生成脚本 (可重复运行)
生成 用户/订单/乘客/签证/酒店/机票/退改 数据, 供特征工程与演示使用
默认 40 用户 × 1-4 订单 = ~100 订单 (满足任务书"至少 100 条业务数据"验收)

用法:
  python scripts/gen_business_data.py              # 默认 40 用户
  python scripts/gen_business_data.py --users 100  # 100 用户
  python scripts/gen_business_data.py --reset      # 先清 U% 用户及其关联数据

黑名单: 本脚本同时写入 risk_blacklist (权威) + blacklist_extra (台账镜像)
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402

COUNTRIES = ["日本", "泰国", "法国", "新加坡", "马来西亚", "韩国", "美国", "冰岛", "瑞士", "中国"]
ORDER_TYPES = ["机票", "酒店", "签证", "跟团游"]
AIRPORTS = [("PEK", "NRT"), ("PVG", "ICN"), ("PEK", "LAX"), ("PVG", "CDG"), ("PVG", "BKK"), ("SHA", "SIN")]
HOTELS = ["H1001", "H1002", "H1003", "H1004", "H1005", "H1006", "H1007", "H1008", "H1009", "H1010"]
FLIGHT_NOS = ["CA123", "KE856", "UA888", "AF125", "TG665", "SQ831", "LX189", "CZ357", "MU541", "FI787"]
NAMES = ["张三", "李四", "王五", "赵六", "孙七", "周八", "吴九", "郑十", "钱十一", "冯十二",
         "陈十三", "褚十四", "卫十五", "蒋十六", "沈十七", "韩十八", "杨十九", "朱二十"]


def _gen_passport(i: int) -> str:
    return f"E{10000000 + i}"


async def gen_business_data(users_count: int = 40, reset: bool = False):
    """生成旅游业务数据."""
    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        if reset:
            print("[reset] 清理 U% 用户及其关联业务数据...")
            # 先删从表 (子表), 再删主表, 避免外键约束
            # 注: 只有 user_id 的按用户删; 只有 order_id 的按订单子查询删
            await conn.execute(text(
                "DELETE FROM order_refund WHERE user_id LIKE 'U%'"))
            await conn.execute(text(
                "DELETE FROM passenger_info WHERE order_id IN (SELECT order_id FROM order_info WHERE user_id LIKE 'U%')"))
            await conn.execute(text(
                "DELETE FROM booking_flight WHERE order_id IN (SELECT order_id FROM order_info WHERE user_id LIKE 'U%')"))
            await conn.execute(text(
                "DELETE FROM booking_hotel WHERE order_id IN (SELECT order_id FROM order_info WHERE user_id LIKE 'U%')"))
            await conn.execute(text(
                "DELETE FROM visa_application WHERE user_id LIKE 'U%'"))
            await conn.execute(text("DELETE FROM order_info WHERE user_id LIKE 'U%'"))
            await conn.execute(text("DELETE FROM user_info WHERE user_id LIKE 'U%'"))
            # 清本脚本写入的黑名单 (按造数原因标记)
            await conn.execute(text("DELETE FROM blacklist_extra WHERE reason LIKE '%批量造数%'"))
            await conn.execute(text("DELETE FROM risk_blacklist WHERE reason LIKE '%批量造数%'"))
            print("  清理完成")

        # ---- 1. 用户 ----
        user_ids = [f"U{i:04d}" for i in range(1, users_count + 1)]
        for idx, uid in enumerate(user_ids):
            age_days = random.randint(3, 800)
            reg = datetime.now() - timedelta(days=age_days)
            await conn.execute(text("""
                INSERT INTO user_info (user_id, name, real_name_status, vip_level, account_age_days, register_time)
                VALUES (:uid, :name, :real, :vip, :days, :reg)
            """), {
                "uid": uid, "name": NAMES[idx % len(NAMES)],
                "real": 1 if random.random() < 0.9 else 0,
                "vip": random.randint(0, 4),
                "days": age_days, "reg": reg,
            })

        # ---- 2. 订单 + 3. 乘客 ----
        order_count = 0
        for uid in user_ids:
            n_orders = random.randint(1, 4)
            for j in range(n_orders):
                order_count += 1
                oid = f"ORD_B{order_count:05d}"
                otype = random.choice(ORDER_TYPES)
                country = random.choice(COUNTRIES)
                amount = random.choice([1500, 3200, 5000, 8800, 12000, 18000, 28000, 50000, 60000])
                n_pass = random.randint(1, 3)
                depart = datetime.now() + timedelta(days=random.randint(3, 80))
                ret = depart + timedelta(days=random.randint(3, 15))
                create = datetime.now() - timedelta(days=random.randint(0, 60), hours=random.randint(0, 23))
                status = random.choice(["已支付", "已支付", "已完成", "已取消"])
                await conn.execute(text("""
                    INSERT INTO order_info (order_id, user_id, order_type, total_amount, dest_country,
                                            depart_date, return_date, passenger_count, create_time, order_status)
                    VALUES (:oid, :uid, :otype, :amt, :cty, :dep, :ret, :np, :ct, :st)
                """), {
                    "oid": oid, "uid": uid, "otype": otype, "amt": amount,
                    "cty": country, "dep": depart, "ret": ret, "np": n_pass,
                    "ct": create, "st": status,
                })
                for k in range(n_pass):
                    await conn.execute(text("""
                        INSERT INTO passenger_info (passenger_id, order_id, name, id_type, id_number, nationality, age)
                        VALUES (:pid, :oid, :name, :itype, :idnum, '中国', :age)
                    """), {
                        "pid": f"PSG_B{order_count:05d}_{k}",
                        "oid": oid,
                        "name": NAMES[random.randrange(len(NAMES))],
                        "itype": random.choice(["身份证", "护照", "身份证", "护照"]),
                        "idnum": _gen_passport(order_count * 10 + k),
                        "age": random.randint(8, 70),
                    })

                # 4. 签证 / 5. 酒店 / 6. 机票 按订单类型补充
                if otype == "签证":
                    await conn.execute(text("""
                        INSERT INTO visa_application (visa_id, user_id, dest_country, visa_type, reject_history, submit_time)
                        VALUES (:vid, :uid, :cty, '旅游签证', :rej, :st)
                    """), {
                        "vid": f"VISA_B{order_count:05d}", "uid": uid, "cty": country,
                        "rej": 1 if random.random() < 0.08 else 0,
                        "st": create,
                    })
                elif otype == "酒店":
                    await conn.execute(text("""
                        INSERT INTO booking_hotel (booking_id, order_id, hotel_id, check_in, check_out, room_count, is_refundable)
                        VALUES (:bid, :oid, :hid, :ci, :co, 1, 1)
                    """), {
                        "bid": f"HTL_B{order_count:05d}", "oid": oid,
                        "hid": random.choice(HOTELS), "ci": depart, "co": ret,
                    })
                elif otype == "机票":
                    dept, arr = random.choice(AIRPORTS)
                    await conn.execute(text("""
                        INSERT INTO booking_flight (booking_id, order_id, flight_no, depart_airport, arrive_airport, cabin_class)
                        VALUES (:bid, :oid, :fno, :dpt, :arr, '经济舱')
                    """), {
                        "bid": f"FLT_B{order_count:05d}", "oid": oid,
                        "fno": random.choice(FLIGHT_NOS), "dpt": dept, "arr": arr,
                    })

                # 7. 退改 (10% 概率)
                if random.random() < 0.10:
                    await conn.execute(text("""
                        INSERT INTO order_refund (refund_id, order_id, user_id, refund_amount, refund_type, refund_status, apply_time)
                        VALUES (:rid, :oid, :uid, :amt, '退款', '处理中', :at)
                    """), {
                        "rid": f"RFD_B{order_count:05d}", "oid": oid, "uid": uid,
                        "amt": amount * 0.3, "at": datetime.now() - timedelta(hours=random.randint(1, 72)),
                    })

        # ---- 8. 黑名单 (双写: risk_blacklist 权威 + blacklist_extra 台账) ----
        black_entries = [
            ("护照号", _gen_passport(999999), "批量造数黑护照"),
            ("护照号", _gen_passport(888888), "批量造数黑护照"),
            ("设备指纹", "DEVICE_GEN_001", "批量造数黄牛设备"),
        ]
        for btype, value, reason in black_entries:
            await conn.execute(text("""
                INSERT IGNORE INTO risk_blacklist (blacklist_type, blacklist_value, reason)
                VALUES (:t, :v, :r)
            """), {"t": btype, "v": value, "r": reason})
            await conn.execute(text("""
                INSERT IGNORE INTO blacklist_extra (type, value, reason)
                VALUES (:t, :v, :r)
            """), {"t": btype, "v": value, "r": reason})

        await conn.commit()

        # ---- 统计 ----
        r = await conn.execute(text("SELECT COUNT(*) FROM user_info WHERE user_id LIKE 'U%'"))
        total_users = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM order_info"))
        total_orders = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM passenger_info"))
        total_passengers = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM visa_application"))
        total_visas = r.scalar()
        print(f"\n[完成] 旅游业务数据生成完成!")
        print(f"  用户:     {total_users}")
        print(f"  订单:     {total_orders}")
        print(f"  乘客:     {total_passengers}")
        print(f"  签证:     {total_visas}")
        print(f"  黑名单:   双写 {len(black_entries)} 条 (risk_blacklist + blacklist_extra)")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="造旅游业务数据 (默认 40 用户).")
    parser.add_argument("--users", type=int, default=40, help="用户数 (默认 40)")
    parser.add_argument("--reset", action="store_true", help="先清 U% 用户及其关联数据")
    args = parser.parse_args()
    asyncio.run(gen_business_data(users_count=args.users, reset=args.reset))
