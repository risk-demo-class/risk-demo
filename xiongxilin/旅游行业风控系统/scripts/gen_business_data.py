"""
旅游行业风控系统 - 业务原始数据生成脚本

默认生成 sql/init_business_data.sql，并保证 10 张旅游业务表每张至少 110 条数据。

用法:
  python scripts/gen_business_data.py
  python scripts/gen_business_data.py --min-rows 150
  python scripts/gen_business_data.py --output sql/init_business_data.sql
"""

from __future__ import annotations

import argparse
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = BASE_DIR / "sql" / "init_business_data.sql"
RANDOM_SEED = 20260812


COUNTRIES = [
    ("中国", "北京", "低", 18, 0),
    ("中国", "上海", "低", 16, 0),
    ("中国", "广州", "低", 20, 0),
    ("中国", "成都", "低", 22, 0),
    ("中国", "三亚", "中", 38, 0),
    ("日本", "东京", "中", 42, 1),
    ("日本", "大阪", "中", 40, 1),
    ("韩国", "首尔", "中", 36, 1),
    ("泰国", "曼谷", "中", 45, 1),
    ("新加坡", "新加坡", "低", 28, 1),
    ("马来西亚", "吉隆坡", "中", 41, 1),
    ("印度尼西亚", "巴厘岛", "中", 46, 1),
    ("法国", "巴黎", "中", 50, 1),
    ("意大利", "罗马", "中", 48, 1),
    ("英国", "伦敦", "中", 44, 1),
    ("美国", "洛杉矶", "高", 72, 1),
    ("美国", "纽约", "高", 75, 1),
    ("土耳其", "伊斯坦布尔", "高", 78, 1),
    ("埃及", "开罗", "高", 82, 1),
    ("巴西", "里约热内卢", "高", 80, 1),
    ("南非", "开普敦", "高", 84, 1),
    ("俄罗斯", "莫斯科", "高", 76, 1),
    ("阿联酋", "迪拜", "中", 52, 1),
    ("澳大利亚", "悉尼", "中", 43, 1),
]

SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
GIVEN_NAMES = ["宇轩", "雨桐", "子涵", "一诺", "浩然", "欣怡", "梓萱", "嘉豪", "思源", "雅婷", "明哲", "晨曦"]
ORDER_TYPES = ["跟团游", "自由行", "机票", "酒店", "签证"]
ORDER_STATUS = ["待支付", "已支付", "已出票", "已确认", "已取消", "已完成", "退款中", "已退款"]
CHANNELS = ["App", "小程序", "H5", "旅行社后台"]
AIRLINES = ["国航", "东航", "南航", "海航", "厦航", "春秋航空", "吉祥航空", "川航"]
AIRPORTS = ["PEK", "PKX", "SHA", "PVG", "CAN", "CTU", "SZX", "HGH", "NRT", "ICN", "BKK", "SIN", "LAX", "JFK"]
HOTELS = ["云端国际酒店", "湖畔度假酒店", "城市精选酒店", "星河酒店", "海景假日酒店", "悦途酒店"]
COMPLAINT_TYPES = ["行程变更", "酒店问题", "航班延误", "签证问题", "服务态度", "重复索赔"]
REFUND_REASONS = ["行程取消", "航班延误", "签证未通过", "酒店无法确认", "价格争议", "服务不符"]


def sql_value(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return f"'{value:%Y-%m-%d %H:%M:%S}'" if isinstance(value, datetime) else f"'{value:%Y-%m-%d}'"
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


def insert_many(table: str, columns: list[str], rows: list[tuple]) -> str:
    values = []
    for row in rows:
        values.append("(" + ", ".join(sql_value(v) for v in row) + ")")
    col_text = ", ".join(f"`{c}`" for c in columns)
    return f"INSERT INTO `{table}` ({col_text}) VALUES\n" + ",\n".join(values) + ";\n"


def pick_name(i: int) -> str:
    return random.choice(SURNAMES) + random.choice(GIVEN_NAMES) + str(i % 10)


def risk_flag(i: int) -> int:
    return 1 if i % 9 in (0, 1) else 0


def make_users(n: int):
    rows = []
    now = datetime.now().replace(microsecond=0)
    for i in range(1, n + 1):
        label = risk_flag(i)
        account_age = random.randint(1, 25) if label else random.randint(30, 1200)
        register_time = now - timedelta(days=account_age, hours=random.randint(0, 23))
        user_id = f"TU{i:04d}"
        pay_group = i % 18 if label else i
        device_group = i % 16 if label else i
        rows.append((
            user_id,
            pick_name(i),
            f"13{random.randint(100000000, 999999999)}",
            "未实名" if label and i % 3 == 0 else "已实名",
            random.choice(["普通", "银卡", "金卡", "白金"]),
            account_age,
            register_time,
            f"pay_{pay_group:04d}@wallet",
            f"dev_{device_group:04d}",
            f"10.{i % 255}.{(i * 7) % 255}.{(i * 13) % 255}",
            random.choice(CHANNELS),
            label,
        ))
    return rows


def make_destinations(n: int):
    rows = []
    now = datetime.now().replace(microsecond=0)
    for i in range(1, n + 1):
        country, city, level, score, cross_border = COUNTRIES[(i - 1) % len(COUNTRIES)]
        city_name = city if i <= len(COUNTRIES) else f"{city}{i // len(COUNTRIES) + 1}"
        adjusted_score = min(100, max(0, score + random.randint(-5, 8)))
        adjusted_level = "极高" if adjusted_score >= 90 else "高" if adjusted_score >= 70 else "中" if adjusted_score >= 30 else "低"
        rows.append((
            f"DST{i:04d}",
            country,
            city_name,
            adjusted_level,
            adjusted_score,
            f"{country}{city_name}旅游热度与合规风险综合评分",
            cross_border,
            now - timedelta(days=random.randint(0, 30)),
        ))
    return rows


def make_orders(n: int, users, destinations):
    rows = []
    now = datetime.now().replace(microsecond=0)
    for i in range(1, n + 1):
        user = users[(i - 1) % len(users)]
        destination = destinations[(i * 3) % len(destinations)]
        label = 1 if user[-1] == 1 or i % 13 == 0 else 0
        create_time = now - timedelta(days=random.randint(0, 120), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        days_to_depart = random.randint(1, 5) if label and i % 2 == 0 else random.randint(7, 90)
        depart_date = (create_time + timedelta(days=days_to_depart)).date()
        trip_days = random.randint(2, 18)
        passenger_count = random.randint(5, 12) if label and i % 4 == 0 else random.randint(1, 4)
        amount_base = random.randint(1200, 9000)
        if destination[6] == 1:
            amount_base += random.randint(3000, 16000)
        if label:
            amount_base += random.randint(8000, 60000)
        total_amount = Decimal(amount_base * passenger_count).quantize(Decimal("0.01"))
        order_type = random.choice(ORDER_TYPES)
        payment_time = create_time + timedelta(minutes=random.randint(2, 90)) if i % 7 != 0 else None
        rows.append((
            f"TO{i:05d}",
            user[0],
            order_type,
            total_amount,
            destination[1],
            destination[2],
            depart_date,
            depart_date + timedelta(days=trip_days),
            passenger_count,
            random.choice(ORDER_STATUS),
            create_time,
            payment_time,
            user[7],
            user[8],
            f"172.{i % 255}.{(i * 5) % 255}.{(i * 11) % 255}",
            random.choice(CHANNELS),
            label,
        ))
    return rows


def make_passengers(n: int, orders):
    rows = []
    for i in range(1, n + 1):
        order = orders[(i - 1) % len(orders)]
        label = 1 if order[-1] == 1 and i % 3 == 0 else 0
        id_type = "护照" if order[4] != "中国" or i % 4 == 0 else "身份证"
        passport_no = f"P{86000000 + i:08d}" if id_type == "护照" else None
        rows.append((
            f"TP{i:05d}",
            order[0],
            order[1],
            pick_name(i + 2000),
            id_type,
            f"{110100 + i % 800000}{1980 + i % 30:04d}{(i % 12) + 1:02d}{(i % 27) + 1:02d}{i % 9999:04d}",
            passport_no,
            "中国" if i % 5 else random.choice(["美国", "日本", "韩国", "新加坡"]),
            random.randint(18, 70),
            date.today() + timedelta(days=random.randint(-30, 3000)),
            "疑似冒用" if label and i % 5 == 0 else "有效",
            label,
        ))
    return rows


def make_visas(n: int, orders):
    rows = []
    now = datetime.now().replace(microsecond=0)
    for i in range(1, n + 1):
        order = orders[(i * 2) % len(orders)]
        label = 1 if order[-1] == 1 or i % 15 == 0 else 0
        status = "拒签" if label and i % 3 == 0 else random.choice(["申请中", "通过", "补材料"])
        rows.append((
            f"TV{i:05d}",
            order[1],
            order[0],
            order[4],
            random.choice(["旅游签", "商务签", "探亲签", "过境签"]),
            random.randint(2, 4) if label else random.randint(0, 1),
            now - timedelta(days=random.randint(0, 90), hours=random.randint(0, 23)),
            status,
            random.randint(3, 8) if label else random.randint(0, 2),
            "材料真实性存疑" if status == "拒签" else None,
            label,
        ))
    return rows


def make_hotels(n: int, orders):
    rows = []
    for i in range(1, n + 1):
        order = orders[(i * 5) % len(orders)]
        check_in = order[6]
        nights = max(1, (order[7] - order[6]).days)
        label = 1 if order[-1] == 1 and i % 2 == 0 else 0
        rows.append((
            f"TH{i:05d}",
            order[0],
            f"HOTEL{i % 60:04d}",
            random.choice(HOTELS),
            order[5],
            check_in,
            check_in + timedelta(days=nights),
            random.randint(3, 8) if label else random.randint(1, 3),
            nights,
            0 if label and i % 4 == 0 else 1,
            "不一致" if label and i % 3 == 0 else "有效",
            label,
        ))
    return rows


def make_flights(n: int, orders):
    rows = []
    for i in range(1, n + 1):
        order = orders[(i * 7) % len(orders)]
        label = 1 if order[-1] == 1 and i % 2 == 1 else 0
        flight_no = f"{random.choice(['CA','MU','CZ','HU','MF'])}{1000 + i % 800}"
        depart_time = datetime.combine(order[6], datetime.min.time()) + timedelta(hours=random.randint(6, 23))
        rows.append((
            f"TF{i:05d}",
            order[0],
            flight_no,
            random.choice(AIRLINES),
            random.choice(AIRPORTS[:8]),
            random.choice(AIRPORTS[8:]),
            depart_time,
            random.choice(["经济舱", "超级经济舱", "商务舱", "头等舱"]),
            random.randint(5, 9) if label else random.randint(1, 3),
            random.choice(["不可退", "有条件退", "免费退"]),
            label,
        ))
    return rows


def make_refunds(n: int, orders):
    rows = []
    now = datetime.now().replace(microsecond=0)
    for i in range(1, n + 1):
        order = orders[(i * 11) % len(orders)]
        label = 1 if order[-1] == 1 or i % 17 == 0 else 0
        rate = Decimal("0.85") if label else Decimal(str(random.uniform(0.05, 0.45)))
        refund_amount = (order[3] * rate).quantize(Decimal("0.01"))
        rows.append((
            f"TR{i:05d}",
            order[0],
            order[1],
            random.choice(["退款", "改签", "取消", "补偿"]),
            refund_amount,
            random.choice(REFUND_REASONS),
            now - timedelta(days=random.randint(0, 90), hours=random.randint(0, 23)),
            random.choice(["待审核", "已通过", "已拒绝", "已完成"]),
            label,
        ))
    return rows


def make_complaints(n: int, orders):
    rows = []
    now = datetime.now().replace(microsecond=0)
    for i in range(1, n + 1):
        order = orders[(i * 13) % len(orders)]
        label = 1 if order[-1] == 1 or i % 19 == 0 else 0
        compensation = Decimal(random.randint(2000, 12000) if label else random.randint(0, 1500)).quantize(Decimal("0.01"))
        rows.append((
            f"TC{i:05d}",
            order[0],
            order[1],
            "重复索赔" if label and i % 4 == 0 else random.choice(COMPLAINT_TYPES),
            now - timedelta(days=random.randint(0, 90), hours=random.randint(0, 23)),
            compensation,
            random.choice(["待处理", "处理中", "已赔付", "已驳回", "已关闭"]),
            label,
        ))
    return rows


def make_blacklist(n: int, users, passengers, orders):
    rows = []
    now = datetime.now().replace(microsecond=0)
    value_by_type = {
        "用户": lambda i: users[i % len(users)][0],
        "手机号": lambda i: users[i % len(users)][2],
        "护照号": lambda i: passengers[i % len(passengers)][6] or f"PBL{i:08d}",
        "身份证号": lambda i: passengers[i % len(passengers)][5],
        "支付账号": lambda i: users[i % len(users)][7],
        "设备指纹": lambda i: users[i % len(users)][8],
        "IP": lambda i: orders[i % len(orders)][14],
        "订单": lambda i: orders[i % len(orders)][0],
    }
    types = list(value_by_type)
    used = set()
    i = 1
    while len(rows) < n:
        bl_type = types[(i - 1) % len(types)]
        value = value_by_type[bl_type](i)
        key = (bl_type, value)
        if key not in used:
            used.add(key)
            rows.append((
                f"BL{len(rows) + 1:05d}",
                bl_type,
                value,
                f"{bl_type}命中旅游业务高风险样例",
                now + timedelta(days=random.randint(30, 365)) if i % 4 else None,
                now - timedelta(days=random.randint(0, 30)),
                1,
            ))
        i += 1
    return rows


def build_dataset(min_rows: int):
    row_count = max(110, min_rows)
    users = make_users(row_count)
    destinations = make_destinations(row_count)
    orders = make_orders(max(row_count + 50, 160), users, destinations)
    passengers = make_passengers(max(row_count + 130, 240), orders)
    visas = make_visas(row_count, orders)
    hotels = make_hotels(row_count, orders)
    flights = make_flights(row_count, orders)
    refunds = make_refunds(row_count, orders)
    complaints = make_complaints(row_count, orders)
    blacklist = make_blacklist(row_count, users, passengers, orders)
    return {
        "user_info": users,
        "destination_risk": destinations,
        "order_info": orders,
        "passenger_info": passengers,
        "visa_application": visas,
        "booking_hotel": hotels,
        "booking_flight": flights,
        "travel_refund": refunds,
        "travel_complaint": complaints,
        "blacklist_extra": blacklist,
    }


TABLE_COLUMNS = {
    "user_info": ["user_id", "name", "phone", "real_name_status", "vip_level", "account_age_days", "register_time", "pay_account", "device_id", "login_ip", "source_channel", "risk_label"],
    "destination_risk": ["destination_id", "country", "city", "risk_level", "risk_score", "risk_reason", "is_cross_border", "update_time"],
    "order_info": ["order_id", "user_id", "order_type", "total_amount", "dest_country", "dest_city", "depart_date", "return_date", "passenger_count", "order_status", "create_time", "payment_time", "pay_account", "device_id", "ip_address", "source_channel", "risk_label"],
    "passenger_info": ["passenger_id", "order_id", "user_id", "name", "id_type", "id_number", "passport_no", "nationality", "age", "document_expire_date", "document_status", "risk_label"],
    "visa_application": ["visa_id", "user_id", "order_id", "dest_country", "visa_type", "reject_history", "submit_time", "visa_status", "material_change_count", "reject_reason", "risk_label"],
    "booking_hotel": ["booking_id", "order_id", "hotel_id", "hotel_name", "city", "check_in", "check_out", "room_count", "night_count", "is_refundable", "guest_document_status", "risk_label"],
    "booking_flight": ["booking_id", "order_id", "flight_no", "airline", "depart_airport", "arrive_airport", "depart_time", "cabin_class", "ticket_count", "refund_rule", "risk_label"],
    "travel_refund": ["refund_id", "order_id", "user_id", "refund_type", "refund_amount", "refund_reason", "apply_time", "refund_status", "risk_label"],
    "travel_complaint": ["complaint_id", "order_id", "user_id", "complaint_type", "complaint_time", "compensation_amount", "complaint_status", "risk_label"],
    "blacklist_extra": ["entry_id", "type", "value", "reason", "expire_at", "create_time", "risk_label"],
}


def render_sql(dataset: dict[str, list[tuple]]) -> str:
    lines = [
        "-- ============================================",
        "-- 旅游行业风控系统 - 业务初始化数据",
        "-- 由 scripts/gen_business_data.py 生成",
        "-- ============================================",
        "",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS = 0;",
        "",
    ]
    for table, rows in dataset.items():
        lines.append(f"-- {table}: {len(rows)} rows")
        lines.append(f"DELETE FROM `{table}`;")
        lines.append(insert_many(table, TABLE_COLUMNS[table], rows))
    lines.extend([
        "SET FOREIGN_KEY_CHECKS = 1;",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成旅游行业业务初始化数据 SQL")
    parser.add_argument("--min-rows", type=int, default=120, help="每张业务表至少生成多少条数据，默认 120")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出 SQL 文件路径")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="随机种子，默认 20260812")
    args = parser.parse_args()

    random.seed(args.seed)
    dataset = build_dataset(args.min_rows)
    output = Path(args.output)
    if not output.is_absolute():
        output = BASE_DIR / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_sql(dataset), encoding="utf-8")

    print("旅游行业业务数据 SQL 已生成:")
    print(f"  {output}")
    for table, rows in dataset.items():
        status = "OK" if len(rows) >= 110 else "FAIL"
        print(f"  [{status}] {table:<20} {len(rows)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
