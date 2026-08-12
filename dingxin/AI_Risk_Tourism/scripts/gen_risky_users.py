"""
生成有风险行为的旅游用户测试数据 (异步).
12 种模式轮换生成, 保证 12 条规则 (R001-R034) 每条都有专属高风险样本:
  模式 0  拒签史       → R001  90天拒签≥2
  模式 1  短期多国     → R002  30天≥3国签证
  模式 2  大额跨境     → R005  订单≥5万
  模式 3  黄牛囤票     → R008  1小时同航班≥5张
  模式 4  0点突击     → R012  凌晨1-5点+行程<7天
  模式 5  乘客不一致   → R018  历史乘客匹配率<30%
  模式 6  新用户大单   → R025/R032  注册<7天+订单≥1万+5乘客
  模式 7  黑护照       → R030  乘客证件命中黑名单
  模式 8  高频退改     → R031  退改率≥50%+订单≥5
  模式 9  临行改签     → R033  临近出行机票改期
  模式 10 酒店倒卖     → R034  1小时同酒店≥3间
  模式 11 正常用户     → 对照组 (不触发规则)

例:
  python scripts/gen_risky_users.py                # 默认 5 个 (RISK001-005)
  python scripts/gen_risky_users.py --count 30     # 30 个 (多轮循环)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 用户再生成
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.config import settings  # noqa: E402

RISK_MODES = [
    "拒签史", "短期多国", "大额跨境", "黄牛囤票", "0点突击", "乘客不一致",
    "新用户大单", "黑护照", "高频退改", "临行改签", "酒店倒卖", "正常用户",
]


async def _insert_user(conn, user_id: str, age_days: int = 300):
    await conn.execute(text("""
        INSERT IGNORE INTO user_info (user_id, name, real_name_status, vip_level, account_age_days, register_time)
        VALUES (:uid, :name, 1, 0, :days, :reg)
    """), {"uid": user_id, "name": f"风险{user_id[-3:]}", "days": age_days,
           "reg": datetime.now() - timedelta(days=age_days)})


async def _insert_order(conn, user_id: str, seq: int, otype: str, amount: float, country: str,
                        depart_days: int, trip_days: int, create_dt: datetime, status: str = "已支付",
                        n_pass: int = 1):
    oid = f"ORD_{user_id[4:]}_{seq:02d}"
    depart = datetime.now() + timedelta(days=depart_days)
    ret = depart + timedelta(days=trip_days)
    await conn.execute(text("""
        INSERT IGNORE INTO order_info (order_id, user_id, order_type, total_amount, dest_country,
                                       depart_date, return_date, passenger_count, create_time, order_status)
        VALUES (:oid, :uid, :otype, :amt, :cty, :dep, :ret, :np, :ct, :st)
    """), {"oid": oid, "uid": user_id, "otype": otype, "amt": amount, "cty": country,
           "dep": depart, "ret": ret, "np": n_pass, "ct": create_dt, "st": status})
    return oid


async def _insert_passenger(conn, order_id: str, seq: int, idnum: str, id_type: str = "护照"):
    await conn.execute(text("""
        INSERT IGNORE INTO passenger_info (passenger_id, order_id, name, id_type, id_number, nationality, age)
        VALUES (:pid, :oid, :name, :itype, :idnum, '中国', 30)
    """), {"pid": f"{order_id.replace('ORD_', 'PSG_')}_{seq}", "oid": order_id,
           "name": f"乘客{seq}", "itype": id_type, "idnum": idnum})


async def _insert_visa(conn, user_id: str, seq: int, country: str, reject: int, days_ago: int):
    await conn.execute(text("""
        INSERT IGNORE INTO visa_application (visa_id, user_id, dest_country, visa_type, reject_history, submit_time)
        VALUES (:vid, :uid, :cty, '旅游签证', :rej, :st)
    """), {"vid": f"VISA_{user_id[4:]}_{seq:02d}", "uid": user_id, "cty": country,
           "rej": reject, "st": datetime.now() - timedelta(days=days_ago)})


async def _insert_flight(conn, order_id: str, seq: int, flight_no: str = "CA123"):
    await conn.execute(text("""
        INSERT IGNORE INTO booking_flight (booking_id, order_id, flight_no, depart_airport, arrive_airport, cabin_class)
        VALUES (:bid, :oid, :fno, 'PEK', 'NRT', '经济舱')
    """), {"bid": f"{order_id.replace('ORD_', 'FLT_')}_{seq}", "oid": order_id, "fno": flight_no})


async def _insert_hotel(conn, order_id: str, seq: int, hotel_id: str = "H1001"):
    await conn.execute(text("""
        INSERT IGNORE INTO booking_hotel (booking_id, order_id, hotel_id, check_in, check_out, room_count, is_refundable)
        VALUES (:bid, :oid, :hid, :ci, :co, 1, 1)
    """), {"bid": f"{order_id.replace('ORD_', 'HTL_')}_{seq}", "oid": order_id, "hid": hotel_id,
           "ci": datetime.now() + timedelta(days=10), "co": datetime.now() + timedelta(days=15)})


async def _insert_refund(conn, order_id: str, user_id: str, seq: int, refund_type: str = "退款"):
    await conn.execute(text("""
        INSERT IGNORE INTO order_refund (refund_id, order_id, user_id, refund_amount, refund_type, refund_status, apply_time)
        VALUES (:rid, :oid, :uid, 1000, :rtype, '处理中', :at)
    """), {"rid": f"{order_id.replace('ORD_', 'RFD_')}_{seq}", "oid": order_id, "uid": user_id,
           "rtype": refund_type, "at": datetime.now() - timedelta(hours=2)})


async def _gen_reject_user(conn, user_id: str):
    """模式 0: 拒签史 (90天≥2次拒签)"""
    await _insert_user(conn, user_id)
    await _insert_visa(conn, user_id, 1, "美国", 1, 80)
    await _insert_visa(conn, user_id, 2, "法国", 1, 50)
    await _insert_visa(conn, user_id, 3, "日本", 0, 20)


async def _gen_multi_country_user(conn, user_id: str):
    """模式 1: 短期多国 (30天≥3国)"""
    await _insert_user(conn, user_id)
    for i, cty in enumerate(["美国", "法国", "日本"], 1):
        await _insert_visa(conn, user_id, i, cty, 0, 30 - i * 8)


async def _gen_big_cross_user(conn, user_id: str):
    """模式 2: 大额跨境 (订单≥5万)"""
    await _insert_user(conn, user_id)
    oid = await _insert_order(conn, user_id, 1, "跟团游", 60000, "冰岛", 55, 7,
                              datetime.now() - timedelta(days=2), n_pass=2)
    await _insert_passenger(conn, oid, 1, "E60000001")
    await _insert_passenger(conn, oid, 2, "E60000002")


async def _gen_ticket_scalper_user(conn, user_id: str):
    """模式 3: 黄牛囤票 (1小时同航班≥5张)"""
    await _insert_user(conn, user_id)
    base = datetime.now() - timedelta(hours=3)
    for i in range(5):
        create = base + timedelta(minutes=i * 10)  # 50 分钟内 5 单
        oid = await _insert_order(conn, user_id, i + 1, "机票", 3000, "日本", 20, 7, create)
        await _insert_passenger(conn, oid, 1, f"E8{i:07d}")
        await _insert_flight(conn, oid, i + 1, "CA123")


async def _gen_night_user(conn, user_id: str):
    """模式 4: 0点突击 (凌晨2点 + 行程<7天)"""
    await _insert_user(conn, user_id)
    night = datetime.now().replace(hour=2, minute=15, second=0)
    oid = await _insert_order(conn, user_id, 1, "机票", 4500, "韩国", 4, 5, night)
    await _insert_passenger(conn, oid, 1, "E70000001")
    await _insert_flight(conn, oid, 1)


async def _gen_mismatch_user(conn, user_id: str):
    """模式 5: 乘客不一致 (历史乘客匹配率<30%: 3人只有1人匹配)"""
    await _insert_user(conn, user_id)
    hist_oid = await _insert_order(conn, user_id, 1, "机票", 3000, "日本", 40, 7,
                                   datetime.now() - timedelta(days=30))
    await _insert_passenger(conn, hist_oid, 1, "E91000001")
    cur_oid = await _insert_order(conn, user_id, 2, "机票", 3500, "泰国", 10, 7,
                                  datetime.now() - timedelta(days=1), n_pass=3)
    await _insert_passenger(conn, cur_oid, 1, "E91000001")  # 匹配
    await _insert_passenger(conn, cur_oid, 2, "E92000002")  # 不匹配
    await _insert_passenger(conn, cur_oid, 3, "E93000003")  # 不匹配


async def _gen_new_user_big_order(conn, user_id: str):
    """模式 6: 新用户大单 (注册5天 + 订单≥1万 + 5乘客)"""
    await _insert_user(conn, user_id, age_days=5)
    oid = await _insert_order(conn, user_id, 1, "跟团游", 15000, "法国", 30, 9,
                              datetime.now() - timedelta(hours=6), n_pass=5)
    for i in range(1, 6):
        await _insert_passenger(conn, oid, i, f"E5{i:07d}")


async def _gen_black_passport_user(conn, user_id: str):
    """模式 7: 黑护照 (乘客证件命中黑名单 → R030)"""
    await _insert_user(conn, user_id)
    oid = await _insert_order(conn, user_id, 1, "机票", 5000, "美国", 25, 10,
                              datetime.now() - timedelta(days=1))
    await _insert_passenger(conn, oid, 1, "E11223344")  # 种子黑护照 (init_risk_data.sql 已入黑名单)


async def _gen_refund_abuse_user(conn, user_id: str):
    """模式 8: 高频退改 (5订单 + 3退改 = 退改率60% → R031)"""
    await _insert_user(conn, user_id)
    for i in range(1, 6):
        oid = await _insert_order(conn, user_id, i, "机票", 2000, "日本", 30 - i, 5,
                                  datetime.now() - timedelta(days=60 - i * 5))
        await _insert_passenger(conn, oid, 1, f"E4{i:07d}")
    for i in range(1, 4):
        oid = f"ORD_{user_id[4:]}_{i:02d}"
        await _insert_refund(conn, oid, user_id, i)


async def _gen_urgent_refund_user(conn, user_id: str):
    """模式 9: 临行改签 (出发<7天机票 + 改期 → R033)"""
    await _insert_user(conn, user_id)
    oid = await _insert_order(conn, user_id, 1, "机票", 6500, "新加坡", 3, 6,
                              datetime.now() - timedelta(days=2))
    await _insert_passenger(conn, oid, 1, "E30000001")
    await _insert_flight(conn, oid, 1)
    await _insert_refund(conn, oid, user_id, 1, refund_type="改期")


async def _gen_hotel_scalper_user(conn, user_id: str):
    """模式 10: 酒店倒卖 (1小时同酒店≥3间 → R034)"""
    await _insert_user(conn, user_id)
    base = datetime.now() - timedelta(hours=2)
    for i in range(3):
        create = base + timedelta(minutes=i * 15)
        oid = await _insert_order(conn, user_id, i + 1, "酒店", 2500, "泰国", 20, 5, create)
        await _insert_passenger(conn, oid, 1, f"E2{i:07d}")
        await _insert_hotel(conn, oid, i + 1, "H1001")


async def _gen_normal_user(conn, user_id: str):
    """模式 11: 正常用户 (对照组, 不触发规则)"""
    await _insert_user(conn, user_id, age_days=500)
    oid = await _insert_order(conn, user_id, 1, "酒店", 1500, "中国", 15, 4,
                              datetime.now() - timedelta(days=7))
    await _insert_passenger(conn, oid, 1, "E10000001", id_type="身份证")
    await _insert_hotel(conn, oid, 1, "H1002")


MODE_GENERATORS = [
    _gen_reject_user,          # 0 拒签史
    _gen_multi_country_user,   # 1 短期多国
    _gen_big_cross_user,       # 2 大额跨境
    _gen_ticket_scalper_user,  # 3 黄牛囤票
    _gen_night_user,           # 4 0点突击
    _gen_mismatch_user,        # 5 乘客不一致
    _gen_new_user_big_order,   # 6 新用户大单
    _gen_black_passport_user,  # 7 黑护照
    _gen_refund_abuse_user,    # 8 高频退改
    _gen_urgent_refund_user,   # 9 临行改签
    _gen_hotel_scalper_user,   # 10 酒店倒卖
    _gen_normal_user,          # 11 正常用户
]


async def gen_risky_users(count: int = 5, reset: bool = False):
    """生成 N 个 RISK 高风险用户 (12 种模式轮换)."""
    if count < 1:
        raise ValueError(f"--count 必须 >= 1, 当前 {count}")

    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        if reset:
            print("[reset] 删旧 RISK 用户 + 关联数据...")
            await conn.execute(text(
                "DELETE FROM order_refund WHERE user_id LIKE 'RISK%'"))
            await conn.execute(text(
                "DELETE FROM passenger_info WHERE order_id IN (SELECT order_id FROM order_info WHERE user_id LIKE 'RISK%')"))
            await conn.execute(text(
                "DELETE FROM booking_flight WHERE order_id IN (SELECT order_id FROM order_info WHERE user_id LIKE 'RISK%')"))
            await conn.execute(text(
                "DELETE FROM booking_hotel WHERE order_id IN (SELECT order_id FROM order_info WHERE user_id LIKE 'RISK%')"))
            await conn.execute(text(
                "DELETE FROM visa_application WHERE user_id LIKE 'RISK%'"))
            await conn.execute(text("DELETE FROM order_info WHERE user_id LIKE 'RISK%'"))
            await conn.execute(text("DELETE FROM user_info WHERE user_id LIKE 'RISK%'"))
            print("  清理完成")

        print(f"[generate] 生成 {count} 个 RISK 用户 (12 模式轮换)...")
        user_ids = [f"RISK{i:03d}" for i in range(1, count + 1)]
        for idx, user_id in enumerate(user_ids):
            mode_idx = idx % len(MODE_GENERATORS)
            mode_name = RISK_MODES[mode_idx]
            print(f"  [{idx+1}/{count}] {user_id} (模式 {mode_idx}: {mode_name})")
            await MODE_GENERATORS[mode_idx](conn, user_id)

        await conn.commit()
        r = await conn.execute(text("SELECT COUNT(*) FROM user_info WHERE user_id LIKE 'RISK%'"))
        print(f"\n[完成] 高风险用户数据生成完成! RISK 用户: {r.scalar()} 个")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="造旅游 RISK 高风险用户 (12 模式轮换).")
    parser.add_argument("--count", type=int, default=5, help="生成 RISK 用户数 (默认 5)")
    parser.add_argument("--reset", action="store_true", help="先删旧 RISK 数据再生成")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))
