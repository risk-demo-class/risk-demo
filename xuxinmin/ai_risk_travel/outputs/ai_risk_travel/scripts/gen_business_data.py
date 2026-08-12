"""
旅游风控系统 - 行业业务数据生成脚本 (可重复运行)

生成 7 张行业业务表数据:
  user_info / order_info / passenger_info / visa_application
  / booking_flight / booking_hotel / blacklist_extra

内置 7 个 RISK 高风险画像用户, 保证规则可命中:
  RISK001 新用户大单     → R025 (注册<7天 + 订单>1万)
  RISK002 拒签刷签       → R001/R002 (90天拒签≥2次 + 30天多国签证)
  RISK003 黄牛囤票       → R008 (订单关联≥5个航班)
  RISK004 0点突击下单    → R012 (凌晨1-5点 + 行程<7天)
  RISK005 盗用证件代订   → R018 (乘客证件与历史匹配率<30%)
  RISK006 高频退订       → R020 (退改签≥3次)
  RISK007 黑护照乘客     → 前置黑名单拦截 (blocked_by=护照号)

用法:
  python scripts/gen_business_data.py                 # 直连 MySQL 入库
  python scripts/gen_business_data.py --export-sql    # 导出 sql/init_business_data.sql (无需 DB)
"""
import argparse
import os
import random
import sys
from datetime import datetime, timedelta

# 项目根目录
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# 常量
# ============================================================

COUNTRIES = ["日本", "泰国", "新加坡", "马来西亚", "韩国", "美国", "法国", "澳大利亚",
             "英国", "意大利", "西班牙", "越南", "印度尼西亚", "俄罗斯", "土耳其", "阿联酋"]
AIRPORTS = [("北京首都", "PEK"), ("上海浦东", "PVG"), ("广州白云", "CAN"), ("成都天府", "TFU"),
            ("深圳宝安", "SZX"), ("杭州萧山", "HGH"), ("西安咸阳", "XIY"), ("重庆江北", "CKG")]
HOTELS = [f"HTL{i:04d}" for i in range(1, 81)]
FLIGHT_NOS = [f"{c}{n}" for c, n in [
    ("CA", 183), ("MU", 503), ("CZ", 301), ("HU", 771), ("3U", 888), ("ZH", 921),
    ("CA", 405), ("MU", 221), ("CZ", 762), ("HU", 115), ("3U", 302), ("ZH", 777),
]]
ORD_STATUS = ["已支付", "已出票", "已支付", "已出票", "已退订", "已取消", "待支付"]


def _uid(i: int) -> str:
    return f"U{i:04d}"


def _rid(prefix: str, i: int) -> str:
    return f"{prefix}{i:05d}"


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def build_rows(count_users: int = 40) -> dict[str, list[dict]]:
    """构造全部业务数据行 (纯 stdlib, 确定性 seed=42)."""
    rng = random.Random(42)
    now = _now()

    users: list[dict] = []
    orders: list[dict] = []
    passengers: list[dict] = []
    visas: list[dict] = []
    flights: list[dict] = []
    hotels: list[dict] = []
    blacklist_extra: list[dict] = []

    # ---------- 普通用户 (U0001 起) ----------
    normal_count = max(count_users - 7, 0)
    for i in range(1, normal_count + 1):
        uid = _uid(i)
        age_days = rng.randint(90, 1500)
        users.append({
            "user_id": uid,
            "name": f"旅客{uid}",
            "phone": f"13{rng.randint(100000000, 999999999):09d}",
            "id_card_hash": f"IDH{uid}",
            "real_name_status": 1 if rng.random() < 0.9 else 0,
            "vip_level": rng.randint(0, 3),
            "account_age_days": age_days,
            "register_at": now - timedelta(days=age_days),
        })
        # 每人 2-4 单
        n_orders = rng.randint(2, 4)
        for _ in range(n_orders):
            create_time = now - timedelta(days=rng.randint(1, 90), hours=rng.randint(6, 20))
            trip_days = rng.randint(3, 15)
            depart = create_time + timedelta(days=rng.randint(3, 45))
            pax = rng.randint(1, 4)
            order_id = _rid("ORD", len(orders) + 1)
            orders.append({
                "order_id": order_id,
                "user_id": uid,
                "order_type": rng.choice(["机票", "机票", "酒店", "跟团游", "签证"]),
                "total_amount": float(rng.randint(800, 30000)),
                "dest_country": rng.choice(COUNTRIES),
                "depart_date": depart,
                "return_date": depart + timedelta(days=trip_days),
                "passenger_count": pax,
                "order_status": rng.choice(["已支付", "已出票", "已出票"]),
                "create_time": create_time,
                "payment_time": create_time + timedelta(minutes=rng.randint(1, 60)),
            })
            # 乘客
            for k in range(pax):
                passengers.append({
                    "passenger_id": _rid("PAS", len(passengers) + 1),
                    "order_id": order_id,
                    "name": f"乘客{len(passengers) + 1}",
                    "id_type": rng.choice(["身份证", "身份证", "护照"]),
                    "id_number": f"ID{rng.randint(100000000, 999999999)}{k}",
                    "nationality": "中国" if rng.random() < 0.9 else rng.choice(COUNTRIES),
                    "age": rng.randint(8, 75),
                })
            # 机票订单关联航班
            if orders[-1]["order_type"] in ("机票", "跟团游"):
                n_flights = rng.randint(1, 2)
                for _ in range(n_flights):
                    dep_air, dep_code = rng.choice(AIRPORTS)
                    arr_air, arr_code = rng.choice(AIRPORTS)
                    flights.append({
                        "booking_id": _rid("FLB", len(flights) + 1),
                        "order_id": order_id,
                        "flight_no": rng.choice(FLIGHT_NOS),
                        "depart_airport": f"{dep_air}({dep_code})",
                        "arrive_airport": f"{arr_air}({arr_code})",
                        "depart_time": depart + timedelta(hours=rng.randint(6, 20)),
                        "cabin_class": rng.choice(["经济舱", "经济舱", "公务舱"]),
                    })
            # 酒店订单关联酒店
            if orders[-1]["order_type"] in ("酒店", "跟团游"):
                hotels.append({
                    "booking_id": _rid("HTB", len(hotels) + 1),
                    "order_id": order_id,
                    "hotel_id": rng.choice(HOTELS),
                    "check_in": depart,
                    "check_out": depart + timedelta(days=trip_days),
                    "room_count": rng.randint(1, 3),
                    "is_refundable": 1 if rng.random() < 0.7 else 0,
                })

    # ---------- 签证申请 (普通用户一部分) ----------
    visa_user_pool = [_uid(i) for i in range(1, normal_count + 1) if rng.random() < 0.6]
    for uid in visa_user_pool:
        for _ in range(rng.randint(1, 2)):
            submit = now - timedelta(days=rng.randint(1, 90))
            visas.append({
                "visa_id": _rid("VSA", len(visas) + 1),
                "user_id": uid,
                "dest_country": rng.choice(COUNTRIES),
                "visa_type": rng.choice(["旅游", "旅游", "商务"]),
                "reject_history": 0,
                "visa_status": rng.choice(["通过", "通过", "通过", "审核中", "被拒"]),
                "submit_time": submit,
            })

    # ---------- RISK 高风险用户 (RISK001-RISK007) ----------
    risk_spec = [
        # (id, age_days, real_name, 订单数, 场景)
        ("RISK001", 3, 0, 5, "new_big"),
        ("RISK002", 400, 1, 3, "visa_reject"),
        ("RISK003", 200, 1, 6, "scalper"),
        ("RISK004", 150, 1, 5, "night_urgent"),
        ("RISK005", 500, 1, 4, "pax_inconsistent"),
        ("RISK006", 300, 1, 6, "frequent_refund"),
        ("RISK007", 600, 1, 3, "black_passport"),
    ]
    for uid, age_days, real_name, n_orders, scenario in risk_spec:
        users.append({
            "user_id": uid,
            "name": f"{uid}用户",
            "phone": f"15{rng.randint(100000000, 999999999):09d}",
            "id_card_hash": f"IDH{uid}",
            "real_name_status": real_name,
            "vip_level": 0,
            "account_age_days": age_days,
            "register_at": now - timedelta(days=age_days),
        })
        for j in range(n_orders):
            if scenario == "new_big":
                create_time = now - timedelta(days=rng.randint(0, 2), hours=rng.randint(8, 20))
                amount = float(rng.randint(12000, 60000))
                status = "已支付"
                order_type = rng.choice(["机票", "跟团游"])
            elif scenario == "scalper":
                create_time = now - timedelta(days=rng.randint(1, 10), hours=rng.randint(8, 22))
                amount = float(rng.randint(5000, 30000))
                status = "已出票"
                order_type = "机票"
            elif scenario == "night_urgent":
                create_time = now - timedelta(days=rng.randint(0, 5))
                create_time = create_time.replace(hour=3, minute=rng.randint(0, 59))
                amount = float(rng.randint(2000, 15000))
                status = "已支付"
                order_type = "机票"
            elif scenario == "pax_inconsistent":
                create_time = now - timedelta(days=rng.randint(5, 30), hours=rng.randint(8, 20))
                amount = float(rng.randint(3000, 25000))
                status = "已出票"
                order_type = rng.choice(["机票", "跟团游"])
            elif scenario == "frequent_refund":
                create_time = now - timedelta(days=rng.randint(1, 60), hours=rng.randint(8, 20))
                amount = float(rng.randint(1500, 12000))
                status = "已退订" if j < 4 else "已出票"
                order_type = rng.choice(["机票", "酒店"])
            elif scenario == "black_passport":
                create_time = now - timedelta(days=rng.randint(1, 15), hours=rng.randint(8, 20))
                amount = float(rng.randint(4000, 20000))
                status = "已支付"
                order_type = "机票"
            else:  # visa_reject
                create_time = now - timedelta(days=rng.randint(5, 60), hours=rng.randint(8, 20))
                amount = float(rng.randint(1000, 8000))
                status = "已支付"
                order_type = "签证"

            depart = create_time + timedelta(
                days=0 if scenario == "night_urgent" else rng.randint(3, 40),
            )
            if scenario == "night_urgent":
                depart = create_time + timedelta(days=rng.randint(1, 5))
            trip_days = rng.randint(3, 12)
            pax = 8 if scenario == "scalper" else rng.randint(1, 4)
            order_id = _rid("ORD", len(orders) + 1)
            orders.append({
                "order_id": order_id,
                "user_id": uid,
                "order_type": order_type,
                "total_amount": amount,
                "dest_country": rng.choice(COUNTRIES),
                "depart_date": depart,
                "return_date": depart + timedelta(days=trip_days),
                "passenger_count": pax,
                "order_status": status,
                "create_time": create_time,
                "payment_time": create_time + timedelta(minutes=rng.randint(1, 30)),
            })
            # 乘客
            for k in range(pax):
                if scenario == "pax_inconsistent":
                    # 全是新证件号, 与历史乘客匹配率 = 0
                    id_number = f"NEW{len(passengers) + 1:08d}"
                elif scenario == "black_passport" and j == 0 and k == 0:
                    id_number = "PBLK00000000001"  # 命中黑名单护照
                else:
                    id_number = f"ID{rng.randint(100000000, 999999999)}{k}"
                passengers.append({
                    "passenger_id": _rid("PAS", len(passengers) + 1),
                    "order_id": order_id,
                    "name": f"乘客{len(passengers) + 1}",
                    "id_type": "护照" if id_number.startswith(("PBLK", "NEW")) or rng.random() < 0.3 else "身份证",
                    "id_number": id_number,
                    "nationality": "中国",
                    "age": rng.randint(8, 75),
                })
            # 航班: 黄牛 5 个航班
            if order_type in ("机票", "跟团游"):
                n_flights = 5 if scenario == "scalper" else rng.randint(1, 2)
                for _ in range(n_flights):
                    dep_air, dep_code = rng.choice(AIRPORTS)
                    arr_air, arr_code = rng.choice(AIRPORTS)
                    flights.append({
                        "booking_id": _rid("FLB", len(flights) + 1),
                        "order_id": order_id,
                        "flight_no": rng.choice(FLIGHT_NOS),
                        "depart_airport": f"{dep_air}({dep_code})",
                        "arrive_airport": f"{arr_air}({arr_code})",
                        "depart_time": depart + timedelta(hours=rng.randint(6, 22)),
                        "cabin_class": rng.choice(["经济舱", "经济舱", "公务舱"]),
                    })
            if order_type in ("酒店", "跟团游"):
                hotels.append({
                    "booking_id": _rid("HTB", len(hotels) + 1),
                    "order_id": order_id,
                    "hotel_id": rng.choice(HOTELS),
                    "check_in": depart,
                    "check_out": depart + timedelta(days=trip_days),
                    "room_count": rng.randint(1, 3),
                    "is_refundable": 1,
                })

        # RISK002 拒签刷签: 90 天内 ≥2 次被拒 + 30 天内 3 国申请
        if scenario == "visa_reject":
            for k in range(3):
                visas.append({
                    "visa_id": _rid("VSA", len(visas) + 1),
                    "user_id": uid,
                    "dest_country": COUNTRIES[k],
                    "visa_type": "旅游",
                    "reject_history": 3 if k < 2 else 0,
                    "visa_status": "被拒" if k < 2 else "审核中",
                    "submit_time": now - timedelta(days=[40, 20, 10][k], hours=3),
                })
        elif scenario == "new_big":
            # 新用户补一单签证申请
            visas.append({
                "visa_id": _rid("VSA", len(visas) + 1),
                "user_id": uid,
                "dest_country": rng.choice(COUNTRIES),
                "visa_type": "旅游",
                "reject_history": 0,
                "visa_status": "审核中",
                "submit_time": now - timedelta(days=1),
            })

    # ---------- 行业黑名单扩展表 ----------
    blacklist_extra = [
        {"entry_id": None, "entry_type": "护照号", "entry_value": "PBLK00000000001",
         "reason": "黑护照测试", "expire_at": None},
        {"entry_id": None, "entry_type": "设备指纹", "entry_value": "DEV_RISK_BOT",
         "reason": "疑似黄牛设备", "expire_at": None},
        {"entry_id": None, "entry_type": "身份证号", "entry_value": "ID999999999",
         "reason": "盗用证件代订", "expire_at": now + timedelta(days=90)},
        {"entry_id": None, "entry_type": "IP", "entry_value": "45.155.204.101",
         "reason": "代理 IP", "expire_at": None},
        {"entry_id": None, "entry_type": "签证号", "entry_value": "VNO88888888",
         "reason": "签证黑产", "expire_at": None},
    ]

    return {
        "user_info": users,
        "order_info": orders,
        "passenger_info": passengers,
        "visa_application": visas,
        "booking_flight": flights,
        "booking_hotel": hotels,
        "blacklist_extra": blacklist_extra,
    }


# ============================================================
# 导出 SQL 快照 (无需 DB)
# ============================================================

def _fmt(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, datetime):
        return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
    return f"'{str(v).replace(chr(39), chr(39) + chr(39))}'"


_TABLE_COLUMNS = {
    "user_info": ["user_id", "name", "phone", "id_card_hash", "real_name_status",
                  "vip_level", "account_age_days", "register_at"],
    "order_info": ["order_id", "user_id", "order_type", "total_amount", "dest_country",
                   "depart_date", "return_date", "passenger_count", "order_status",
                   "create_time", "payment_time"],
    "passenger_info": ["passenger_id", "order_id", "name", "id_type", "id_number",
                       "nationality", "age"],
    "visa_application": ["visa_id", "user_id", "dest_country", "visa_type",
                         "reject_history", "visa_status", "submit_time"],
    "booking_flight": ["booking_id", "order_id", "flight_no", "depart_airport",
                       "arrive_airport", "depart_time", "cabin_class"],
    "booking_hotel": ["booking_id", "order_id", "hotel_id", "check_in", "check_out",
                      "room_count", "is_refundable"],
    "blacklist_extra": ["entry_type", "entry_value", "reason", "expire_at"],
}


def export_sql(rows: dict[str, list[dict]], output_path: str) -> None:
    """把 rows 导出成 sql/init_business_data.sql (INSERT 语句)."""
    lines = [
        "-- ============================================================",
        "-- 旅游风控系统 - 行业业务数据 (由 scripts/gen_business_data.py --export-sql 生成)",
        "-- 至少 100 条业务数据, 含 7 个 RISK 高风险画像用户",
        "-- ============================================================",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS = 0;",
        "",
    ]
    total = 0
    for table, columns in _TABLE_COLUMNS.items():
        table_rows = rows[table]
        if not table_rows:
            continue
        lines.append(f"-- {table} ({len(table_rows)} 条)")
        col_sql = ", ".join(f"`{c}`" for c in columns)
        for row in table_rows:
            values = ", ".join(_fmt(row.get(c)) for c in columns)
            lines.append(f"INSERT INTO `{table}` ({col_sql}) VALUES ({values});")
            total += 1
        lines.append("")
    lines.append(f"-- 共 {total} 条业务数据")
    lines.append("SET FOREIGN_KEY_CHECKS = 1;")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"已导出 {total} 条业务数据 → {output_path}")


# ============================================================
# 入库 (需要 MySQL + sqlalchemy)
# ============================================================

async def insert_rows(rows: dict[str, list[dict]]) -> None:
    """把数据写进 MySQL (先清空 7 张行业业务表再插入)."""
    from sqlalchemy import delete

    from app.database import AsyncSessionLocal, async_engine
    from app.models_business import (
        BlacklistExtra,
        BookingFlight,
        BookingHotel,
        OrderInfo,
        PassengerInfo,
        UserInfo,
        VisaApplication,
    )

    model_map = {
        "user_info": UserInfo,
        "order_info": OrderInfo,
        "passenger_info": PassengerInfo,
        "visa_application": VisaApplication,
        "booking_flight": BookingFlight,
        "booking_hotel": BookingHotel,
        "blacklist_extra": BlacklistExtra,
    }
    try:
        async with AsyncSessionLocal() as db:
            # 清空旧数据 (先清子表)
            for table in ("passenger_info", "booking_flight", "booking_hotel",
                          "visa_application", "order_info", "user_info", "blacklist_extra"):
                await db.execute(delete(model_map[table]))
            for table, model in model_map.items():
                for row in rows[table]:
                    db.add(model(**{k: v for k, v in row.items() if k != "entry_id"}))
            await db.commit()
        print("入库完成!")
        for table, items in rows.items():
            print(f"  {table:<20} {len(items)} 条")
    finally:
        await async_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="旅游风控系统 - 行业业务数据生成")
    parser.add_argument("--count", type=int, default=40, help="用户数 (默认 40, 含 7 个 RISK 用户)")
    parser.add_argument("--export-sql", action="store_true",
                        help="只导出 sql/init_business_data.sql, 不连数据库")
    args = parser.parse_args()

    rows = build_rows(args.count)
    total = sum(len(v) for v in rows.values())
    print(f"业务数据总量: {total} 条 (用户 {len(rows['user_info'])} / 订单 {len(rows['order_info'])} / "
          f"乘客 {len(rows['passenger_info'])} / 签证 {len(rows['visa_application'])} / "
          f"航班 {len(rows['booking_flight'])} / 酒店 {len(rows['booking_hotel'])} / "
          f"黑名单扩展 {len(rows['blacklist_extra'])}")

    if args.export_sql:
        export_sql(rows, os.path.join(ROOT, "sql", "init_business_data.sql"))
        return

    import asyncio
    sys.path.insert(0, ROOT)
    asyncio.run(insert_rows(rows))


if __name__ == "__main__":
    main()
