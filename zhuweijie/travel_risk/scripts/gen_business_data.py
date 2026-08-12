"""
旅游风控系统 - 业务数据生成脚本 (OTA 行业)
生成: 用户 / 订单 / 乘客 / 签证 / 机票 / 酒店 / 扩展黑名单
默认写入 MySQL (需先 init_db); --sql 参数导出 INSERT SQL 文件.

用法:
  python scripts/gen_business_data.py                          # 写入 travel_risk 库
  python scripts/gen_business_data.py --users 50               # 指定用户数
  python scripts/gen_business_data.py --sql sql/init_business_data.sql   # 导出 SQL
"""
import argparse
import hashlib
import random
import sys
from datetime import datetime, timedelta

import os

# 确保 import app 命中本项目 (基线已 editable 安装进 venv, 不加会 import 到电商版)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.stdout.reconfigure(encoding="utf-8")

from faker import Faker  # noqa: E402

from app.config import settings  # noqa: E402

COUNTRIES = ["日本", "泰国", "新加坡", "法国", "美国", "意大利", "阿联酋", "缅甸", "中国"]
CITIES = ["北京", "上海", "广州", "深圳", "成都", "杭州"]
FLIGHT_NOS = ["CA1831", "MU5101", "CZ3908", "HU7605", "9C8821", "CA9999"]
HOTEL_IDS = ["H001", "H002", "H003", "H004", "H005", "H006"]

# 高风险用户样本 (保证任务3规则能命中):
#   U001 黄牛囤票(同航班5单) / U002 拒签2次 / U003 新号大单 / U004 多次取消 / U005 黑护照
RISKY_USERS = {
    "U001": {"age": 30, "pattern": "flight_scalper"},
    "U002": {"age": 90, "pattern": "visa_reject"},
    "U003": {"age": 5, "pattern": "big_new"},
    "U004": {"age": 200, "pattern": "cancel_abuse"},
    "U005": {"age": 400, "pattern": "black_passport"},
}
BLACK_PASSPORT = "E12345678"


def _id(prefix: str, i: int) -> str:
    return f"{prefix}{i:03d}"


def _hash(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()[:32]


def _esc(v):
    if v is None:
        return "NULL"
    s = str(v)
    return "'" + s.replace("'", "''") + "'"


def build_dataset(users_n: int = 30, seed: int = 42):
    """构造数据集, 返回 (users, orders, passengers, visas, flights, hotels, blacklist) 元组列表"""
    random.seed(seed)
    fk = Faker("zh_CN")
    fk.seed_instance(seed)

    users, orders, passengers, visas, flights, hotels = [], [], [], [], [], []
    blacklist = [
        ("护照号", BLACK_PASSPORT, "挂失护照", None),
        ("设备指纹", "DEV-SCALPER-001", "黄牛设备", None),
        ("支付账号", "PAY-CASH-001", "套现代付账号", None),
    ]

    now = datetime.now()
    for i in range(1, users_n + 1):
        uid = _id("U", i)
        risky = RISKY_USERS.get(uid)
        age = risky["age"] if risky else random.randint(30, 900)
        real = "已实名" if random.random() < 0.85 else "未实名"
        users.append((
            uid, fk.name(), real, _hash(fk.ssn()), random.randint(0, 5), age,
            (now - timedelta(days=age)).strftime("%Y-%m-%d %H:%M:%S"),
        ))

        if risky and risky["pattern"] == "flight_scalper":
            n_orders = 5
        elif risky and risky["pattern"] == "cancel_abuse":
            n_orders = 4
        else:
            n_orders = random.randint(1, 4)
        for j in range(1, n_orders + 1):
            oid = _id("O", i * 100 + j)
            if risky and risky["pattern"] == "flight_scalper":
                otype, flight_no = "机票", "CA9999"
                depart_day = now + timedelta(days=3)
            else:
                r = random.random()
                otype = "机票" if r < 0.45 else ("酒店" if r < 0.8 else "跟团游")
                flight_no = random.choice(FLIGHT_NOS)
                depart_day = now + timedelta(days=random.randint(1, 90))

            dest = random.choice(COUNTRIES) if otype != "酒店" else random.choice(["中国", "泰国", "日本"])
            if risky and risky["pattern"] == "visa_reject":
                dest = random.choice(["法国", "美国", "阿联酋"])
            amount = {"机票": random.randint(800, 15000),
                      "酒店": random.randint(300, 8000),
                      "跟团游": random.randint(3000, 80000)}[otype]
            if risky and risky["pattern"] == "big_new":
                amount = max(amount, 12000)
            if risky and risky["pattern"] == "flight_scalper":
                amount = random.randint(1000, 4000)

            pcount = random.randint(1, 4)
            if risky and risky["pattern"] == "cancel_abuse" and j >= 2:
                pay = "已取消"
            else:
                pay = random.choices(["已支付", "待支付", "已取消"], [0.8, 0.15, 0.05])[0]

            create = now - timedelta(days=random.randint(0, 60), hours=random.randint(0, 23))
            if random.random() < 0.15:
                create = create.replace(hour=random.randint(0, 5))
            pay_time = (create + timedelta(minutes=random.randint(1, 60))) if pay == "已支付" else None

            orders.append((
                oid, uid, otype, float(amount), dest,
                depart_day.strftime("%Y-%m-%d"),
                (depart_day + timedelta(days=random.randint(3, 15))).strftime("%Y-%m-%d"),
                pcount, pay,
                create.strftime("%Y-%m-%d %H:%M:%S"),
                pay_time.strftime("%Y-%m-%d %H:%M:%S") if pay_time else None,
            ))

            for k in range(1, pcount + 1):
                pid = _id("P", len(passengers) + 1)
                id_type = "护照" if (dest != "中国" and random.random() < 0.7) else "身份证"
                if risky and risky["pattern"] == "black_passport" and k == 1:
                    id_number = BLACK_PASSPORT
                else:
                    id_number = fk.passport_number() if id_type == "护照" else fk.ssn()
                nationality = dest if (risky and risky["pattern"] == "black_passport") else "中国"
                passengers.append((pid, oid, fk.name(), id_type, id_number, nationality, random.randint(5, 80)))

            if otype == "机票":
                for _ in range(random.randint(1, 2)):
                    bid = _id("F", len(flights) + 1)
                    dep_t = depart_day + timedelta(hours=random.randint(6, 22))
                    flights.append((bid, oid, flight_no, random.choice(CITIES), random.choice(CITIES),
                                    random.choices(["经济舱", "公务舱", "头等舱"], [0.85, 0.1, 0.05])[0],
                                    dep_t.strftime("%Y-%m-%d %H:%M:%S")))
            elif otype == "酒店":
                bid = _id("H", len(hotels) + 1)
                check_in = depart_day
                hotels.append((bid, oid, random.choice(HOTEL_IDS), check_in.strftime("%Y-%m-%d"),
                               (check_in + timedelta(days=random.randint(1, 7))).strftime("%Y-%m-%d"),
                               random.randint(1, 3), 1))

        if risky or random.random() < 0.4:
            n_visa = 2 if (risky and risky["pattern"] == "visa_reject") else 1
            for v in range(1, n_visa + 1):
                vid = _id("V", len(visas) + 1)
                reject = random.randint(0, 1)
                if risky and risky["pattern"] == "visa_reject":
                    reject = 2 if v == 1 else 1
                visas.append((vid, uid, random.choice(["日本", "泰国", "法国", "美国", "新加坡", "阿联酋"]),
                              "旅游签证", reject,
                              (now - timedelta(days=random.randint(1, 90))).strftime("%Y-%m-%d %H:%M:%S")))

    return users, orders, passengers, visas, flights, hotels, blacklist


TABLE_COLS = {
    "user_info": ("user_id", "name", "real_name_status", "id_card_hash", "vip_level", "account_age_days", "register_at"),
    "order_info": ("order_id", "user_id", "order_type", "total_amount", "dest_country", "depart_date",
                   "return_date", "passenger_count", "pay_status", "create_time", "payment_time"),
    "passenger_info": ("passenger_id", "order_id", "name", "id_type", "id_number", "nationality", "age"),
    "visa_application": ("visa_id", "user_id", "dest_country", "visa_type", "reject_history", "submit_time"),
    "booking_flight": ("booking_id", "order_id", "flight_no", "depart_airport", "arrive_airport", "cabin_class", "depart_time"),
    "booking_hotel": ("booking_id", "order_id", "hotel_id", "check_in", "check_out", "room_count", "is_refundable"),
    "blacklist_extra": ("type", "value", "reason", "expire_at"),
}


def dump_sql(dataset, path: str) -> int:
    """导出 INSERT SQL 文件, 返回总行数"""
    tables = ["user_info", "order_info", "passenger_info", "visa_application",
              "booking_flight", "booking_hotel", "blacklist_extra"]
    lines = ["-- 旅游风控系统 - 业务数据 (由 scripts/gen_business_data.py 生成, 请勿手改)", "SET NAMES utf8mb4;", "SET FOREIGN_KEY_CHECKS = 0;", ""]
    total = 0
    for name, rows in zip(tables, dataset):
        if not rows:
            continue
        cols = TABLE_COLS[name]
        lines.append(f"-- Table `{name}`: {len(rows)} rows")
        lines.append(f"INSERT INTO `{name}` ({', '.join('`' + c + '`' for c in cols)}) VALUES")
        chunk = []
        for r in rows:
            chunk.append("(" + ", ".join(_esc(v) for v in r) + ")")
        lines.append(",\n".join(chunk) + ";")
        lines.append("")
        total += len(rows)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return total


def insert_db(dataset) -> int:
    """写入 MySQL"""
    import pymysql
    conn = pymysql.connect(host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER,
                           password=settings.DB_PASSWORD, database=settings.DB_NAME, charset="utf8mb4")
    tables = ["user_info", "order_info", "passenger_info", "visa_application",
              "booking_flight", "booking_hotel", "blacklist_extra"]
    total = 0
    try:
        with conn.cursor() as cur:
            for name, rows in zip(tables, dataset):
                if not rows:
                    continue
                cols = TABLE_COLS[name]
                sql = (f"INSERT INTO `{name}` ({', '.join('`' + c + '`' for c in cols)}) "
                       f"VALUES ({', '.join(['%s'] * len(cols))})")
                cur.executemany(sql, [tuple(r) for r in rows])
                total += len(rows)
        conn.commit()
    finally:
        conn.close()
    return total


def main():
    parser = argparse.ArgumentParser(description="旅游风控业务造数脚本")
    parser.add_argument("--users", type=int, default=30, help="用户数 (默认30)")
    parser.add_argument("--seed", type=int, default=42, help="随机种子 (默认42, 保证可复现)")
    parser.add_argument("--sql", default=None, help="导出 SQL 文件路径 (不写库)")
    args = parser.parse_args()

    dataset = build_dataset(users_n=args.users, seed=args.seed)
    total = sum(len(r) for r in dataset)
    print(f"数据集: {args.users} 用户 / 共 {total} 行 (订单 {len(dataset[1])}, 乘客 {len(dataset[2])}, 签证 {len(dataset[3])})")

    if args.sql:
        n = dump_sql(dataset, args.sql)
        print(f"已导出 SQL: {args.sql} ({n} 行)")
    else:
        n = insert_db(dataset)
        print(f"已写入 {settings.DB_NAME} 库: {n} 行")


if __name__ == "__main__":
    main()
