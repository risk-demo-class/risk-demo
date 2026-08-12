"""
旅游风控系统 - 随机业务数据生成 (一次性脚本)
================
生成规模 (默认可调):
  - 用户 (user_info):           N_USER     (默认 5000)
  - 设备 (device_info):         N_USER * 1.6
  - 用户设备 (user_device):     N_USER * 1.6
  - 出行人 (traveler_info):     N_USER * 2  (平均 2 人/用户)
  - 旅游订单 (booking_info):    N_USER * 3  (平均 3 单/人)
  - 订单明细 (booking_detail):  N_ORDER * 1.3
  - 订单出行人 (booking_traveler): N_ORDER * 出行人数
  - 支付 (payment_info):        N_ORDER * 90%
  - 退改 (refund_change):       N_ORDER * 15%
  - 理赔 (claim_info):          N_ORDER * 3%
  - 投诉 (complaint_info):      N_ORDER * 3%
  - 点评 (review_info):         N_ORDER * 20%
  - 总条目:                     ≈ 12w+

风险画像 (自动注入):
  - 80% 正常用户 (低退改率, 1-2 设备, 正常时段下单)
  - 15% 中风险 (高退改率 30-50% / 多设备 2-3 / 中额订单)
  - 5%  高风险 (大额订单 5w+ / 深夜下单 / 极高退改率 50%+ / 多设备 4+ / 理赔+投诉)

幂等: 重复跑会因 UNIQUE 约束报错, 建议用 init_db.py --drop 后重跑.
"""
import argparse
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from dotenv import load_dotenv
from faker import Faker

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "123321"),
    "db": os.getenv("DB_NAME", "travel_risk"),
    "charset": "utf8mb4",
    "autocommit": True,
}

# 产品分类 (FK: product_category)
PRODUCT_CATEGORIES = ["跟团游", "自由行", "酒店", "机票", "门票", "签证", "邮轮", "租车"]
# 订单状态 (FK: booking_status)
BOOKING_STATUSES = ["待支付", "已支付", "出行中", "已完成", "已取消", "已退订"]
# 支付渠道
PAY_CHANNELS = ["微信", "支付宝", "银联", "银行卡"]
# 退改类型 / 状态
REFUND_TYPES = ["退订", "改期", "部分退款"]
REFUND_STATUSES = ["处理中", "已完成", "已驳回"]
# 理赔类型 / 状态
CLAIM_TYPES = ["航班延误", "取消险", "意外险", "行程变更"]
CLAIM_STATUSES = ["审核中", "已通过", "已驳回"]
# 投诉类型
COMPLAINT_TYPES = ["服务质量", "住宿", "行程安排", "费用争议", "航司服务", "签证"]


def _connect():
    return pymysql.connect(**DB_CONFIG)


def _risk_tier() -> str:
    """风险分层: normal 80% / medium 15% / high 5%"""
    r = random.random()
    if r < 0.05:
        return "high"
    elif r < 0.20:
        return "medium"
    return "normal"


def _night_hour() -> int:
    return random.choice([0, 1, 2, 3, 4, 5])


def main(
    n_user: int = 5000,
    min_orders: int = 1,
    max_orders: int = 8,
    seed: int = 42,
):
    random.seed(seed)
    fake = Faker("zh_CN")
    fake.seed_instance(seed)
    conn = _connect()

    print("=" * 60)
    print(f"旅游风控系统 - 生成随机业务数据 (用户 {n_user}, 每用户 {min_orders}~{max_orders} 单)")
    print("=" * 60)

    with conn.cursor() as cur:
        # 读取已有产品 (seed 数据 P001-P040)
        cur.execute("SELECT product_id, price, is_overseas FROM product_info ORDER BY product_id")
        products = [(r[0], float(r[1]), int(r[2])) for r in cur.fetchall()]
        # 读取供应商
        cur.execute("SELECT supplier_id FROM supplier_info")
        suppliers = [r[0] for r in cur.fetchall()]
        # 读取区域
        cur.execute("SELECT country, province, city FROM region")
        regions = [(r[0], r[1], r[2]) for r in cur.fetchall()]

        if not products:
            raise SystemExit("product_info 为空, 请先跑 python scripts/init_db.py 灌种子数据")

        # 补足产品到 200 个 (P100 起, 避免只有 40 个产品太集中)
        if len(products) < 200:
            print(f"[1/9] 补充产品到 200 个 (当前 {len(products)})...")
            new_products = []
            for i in range(100, 100 + (200 - len(products))):
                cat = random.choice(PRODUCT_CATEGORIES)
                country, province, city = random.choice(regions)
                overseas = 1 if country != "中国" else 0
                price = random.choice([99, 199, 399, 680, 1200, 1680, 2680, 3980, 4980, 6980, 8800, 12800, 15800, 18800, 22800, 26800, 36800])
                pid = f"P{i}"
                new_products.append((pid, pid, cat, random.choice(suppliers), price,
                                     country, province, city, random.randint(10, 2000), overseas, random.randint(1, 10)))
                products.append((pid, price, overseas))
            cur.executemany(
                "INSERT INTO product_info (product_id, product_name, product_category, supplier_id, price,"
                " destination_country, destination_province, destination_city, stock, is_overseas, trip_days)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                new_products,
            )
        print(f"[1/9] 产品就绪: {len(products)} 个")

        # 2. 用户 + 风险分层
        print(f"[2/9] 生成用户 {n_user} 个...")
        user_ids = [f"U{10000 + i}" for i in range(1, n_user + 1)]
        user_risk = {uid: _risk_tier() for uid in user_ids}
        user_rows = []
        device_rows = []
        user_device_rows = []
        for i, uid in enumerate(user_ids):
            reg_days_ago = random.randint(30, 800)
            reg_time = datetime.now() - timedelta(days=reg_days_ago)
            phone = f"13{random.randint(100000000, 999999999)}"
            user_phone_map[uid] = phone
            channel = random.choice(["APP", "WEB", "小程序", "H5"])
            verified = 1 if random.random() < 0.7 else 0
            user_rows.append((uid, phone, reg_time, channel, verified))

            risk = user_risk[uid]
            n_dev = random.randint(1, 2) if risk == "normal" else (random.randint(2, 3) if risk == "medium" else random.randint(4, 6))
            for d in range(n_dev):
                dev_id = f"DEV{uid}{d}"
                device_rows.append((dev_id, random.choice(["iPhone 15", "小米14", "华为Mate60", "OPPO X7", "红米K70", "三星S24"]),
                                    random.choice(["iOS 17", "Android 14", "HarmonyOS 4", "Windows 11"]),
                                    random.choice(["Safari", "Chrome", "Edge"])))
                user_device_rows.append((uid, dev_id, reg_time + timedelta(days=d * 30)))
        batch_insert(conn, "user_info (user_id, phone, register_time, register_channel, is_verified)", user_rows, 2000)
        batch_insert(conn, "device_info (device_id, device_model, os, browser)", device_rows, 2000)
        batch_insert(conn, "user_device (user_id, device_id, bind_time)", user_device_rows, 2000)
        n_high = sum(1 for v in user_risk.values() if v == "high")
        n_med = sum(1 for v in user_risk.values() if v == "medium")
        print(f"  → {n_user} 用户 (高风险 {n_high}, 中风险 {n_med}, 正常 {n_user - n_high - n_med})")

        # 3. 出行人
        print("[3/9] 生成出行人...")
        traveler_rows = []
        booking_traveler_rows = []
        traveler_id_counter = 1
        for uid in user_ids:
            risk = user_risk[uid]
            n_travelers = random.randint(1, 3) if risk == "normal" else (random.randint(2, 4) if risk == "medium" else random.randint(3, 8))
            traveler_ids = []
            for t in range(n_travelers):
                tid = f"TRV{traveler_id_counter:06d}"
                traveler_id_counter += 1
                name = fake.name()
                id_no = f"{random.randint(110000000000000000, 999999999999999999)}"
                tphone = f"15{random.randint(100000000, 999999999)}"
                traveler_rows.append((tid, uid, name, id_no, tphone))
                traveler_ids.append(tid)
            user_travelers[uid] = traveler_ids
        batch_insert(conn, "traveler_info (traveler_id, user_id, traveler_name, id_card_no, phone)", traveler_rows, 2000)
        print(f"  → {len(traveler_rows)} 出行人")

        # 4. 旅游订单 + 明细 + 出行人关联 + 支付
        print("[4/9] 生成旅游订单...")
        booking_rows = []
        detail_rows = []
        payment_rows = []
        refund_rows = []
        claim_rows = []
        complaint_rows = []
        review_rows = []
        booking_id_counter = 100000
        detail_id_counter = 100000
        pay_id_counter = 100000

        for uid in user_ids:
            risk = user_risk[uid]
            n_orders = random.randint(min_orders, max_orders)
            for oi in range(n_orders):
                bid = f"B{booking_id_counter}"
                booking_id_counter += 1
                create_time = datetime.now() - timedelta(days=random.randint(1, 365), hours=random.randint(0, 23), minutes=random.randint(0, 59))
                # 高风险用户 40% 概率深夜下单
                if risk == "high" and random.random() < 0.4:
                    create_time = create_time.replace(hour=_night_hour(), minute=random.randint(0, 59))

                departure = create_time + timedelta(days=random.randint(1, 60))
                n_detail = random.randint(1, 5)
                # 高风险用户大额订单概率 30%
                big_order = risk == "high" and random.random() < 0.3
                total_amount = 0.0
                discount_amount = 0.0
                final_amount = 0.0
                for di in range(n_detail):
                    pid, price, overseas = random.choice(products)
                    qty = random.randint(1, 4)
                    if big_order:
                        price = price * random.choice([3, 5, 8])
                    total = round(price * qty, 2)
                    discount = round(total * random.choice([0.0, 0.0, 0.05, 0.1, 0.2]), 2)
                    final = round(total - discount, 2)
                    total_amount += total
                    discount_amount += discount
                    final_amount += final
                    did = f"D{detail_id_counter}"
                    detail_id_counter += 1
                    detail_rows.append((did, bid, pid, pid, qty, round(price, 2), round(total, 2), round(discount, 2), round(final, 2)))

                # 订单状态: 已完成 60% / 已支付 20% / 待支付 10% / 已取消 5% / 已退订 5% / 出行中
                status = random.choices(
                    ["已完成", "已支付", "待支付", "出行中", "已取消", "已退订"],
                    weights=[60, 20, 8, 4, 5, 3],
                )[0]
                traveler_count = random.randint(1, min(len(user_travelers[uid]), 6))
                chosen_travelers = random.sample(user_travelers[uid], traveler_count)
                contact_phone = user_phone_map.get(uid) or f"13{random.randint(100000000, 999999999)}"
                booking_rows.append((bid, create_time, None if status == "待支付" else create_time + timedelta(seconds=random.randint(6, 3600)),
                                     departure, departure + timedelta(days=random.randint(1, 10)),
                                     uid, contact_phone, status, traveler_count))
                for tid in chosen_travelers:
                    booking_traveler_rows.append((bid, tid, "本人" if random.random() < 0.4 else "同行人"))

                if status != "待支付":
                    pay_id = f"PAY{pay_id_counter}"
                    pay_id_counter += 1
                    payment_rows.append((pay_id, bid, uid, create_time + timedelta(minutes=random.randint(1, 60)),
                                         round(final_amount, 2), random.choice(PAY_CHANNELS), "成功"))

                # 退改 (高风险用户 50% 概率)
                if risk == "high" and random.random() < 0.5:
                    refund_rows.append((f"RF{bid}", create_time + timedelta(days=random.randint(1, 10)),
                                        None, bid, round(final_amount * 0.9, 2), random.choice(REFUND_TYPES),
                                        fake.sentence(nb_words=6), random.choice(REFUND_STATUSES)))
                elif risk == "medium" and random.random() < 0.15:
                    refund_rows.append((f"RF{bid}", create_time + timedelta(days=random.randint(1, 10)),
                                        None, bid, round(final_amount * 0.9, 2), random.choice(REFUND_TYPES),
                                        fake.sentence(nb_words=6), random.choice(REFUND_STATUSES)))

                # 理赔 (高风险用户 20% 概率, 航班延误为主)
                if risk == "high" and random.random() < 0.2:
                    claim_rows.append((f"CL{bid}", bid, uid, random.choice(CLAIM_TYPES), 600.00,
                                       create_time + timedelta(days=random.randint(1, 5)), random.choice(CLAIM_STATUSES)))

                # 投诉 (高风险用户 15% 概率)
                if risk == "high" and random.random() < 0.15:
                    complaint_rows.append((f"CP{bid}", bid, uid, create_time + timedelta(days=random.randint(1, 30)),
                                           fake.sentence(nb_words=10), random.choice(COMPLAINT_TYPES), random.choice(["处理中", "已完成"])))

                # 点评 (已完成订单 30% 概率)
                if status == "已完成" and random.random() < 0.3:
                    review_rows.append((f"RV{bid}", bid, pid, uid, random.randint(1, 5),
                                        fake.sentence(nb_words=8), departure + timedelta(days=random.randint(1, 10)), 1))

        batch_insert(conn, "booking_info (booking_id, create_time, payment_time, departure_time, end_time, user_id,"
                           " contact_phone, booking_status, traveler_count)", booking_rows, 1000)
        print(f"  → {len(booking_rows)} 订单")

        print("[5/9] 生成订单明细 / 出行人关联 / 支付...")
        batch_insert(conn, "booking_detail (booking_detail_id, booking_id, product_id, product_name, quantity,"
                           " unit_price, total_amount, discount_amount, final_amount)", detail_rows, 1000)
        batch_insert(conn, "booking_traveler (booking_id, traveler_id, relation)", booking_traveler_rows, 1000)
        batch_insert(conn, "payment_info (payment_id, booking_id, user_id, pay_time, pay_amount, pay_channel, pay_status)",
                     payment_rows, 1000)
        print(f"  → 明细 {len(detail_rows)} / 出行人关联 {len(booking_traveler_rows)} / 支付 {len(payment_rows)}")

        print("[6/9] 生成退改/理赔/投诉/点评...")
        batch_insert(conn, "refund_change (refund_id, create_time, complete_time, booking_id, refund_amount,"
                           " refund_type, refund_reason, refund_status)", refund_rows, 1000)
        batch_insert(conn, "claim_info (claim_id, booking_id, user_id, claim_type, claim_amount, apply_time, claim_status)",
                     claim_rows, 1000)
        batch_insert(conn, "complaint_info (complaint_id, booking_id, user_id, complaint_time, complaint_content,"
                           " complaint_type, complaint_status)", complaint_rows, 1000)
        batch_insert(conn, "review_info (review_id, booking_id, product_id, user_id, rating, content, review_time, is_verified)",
                     review_rows, 1000)
        print(f"  → 退改 {len(refund_rows)} / 理赔 {len(claim_rows)} / 投诉 {len(complaint_rows)} / 点评 {len(review_rows)}")

        # 7. 汇总
        total = (len(user_rows) + len(device_rows) + len(user_device_rows) + len(traveler_rows)
                 + len(booking_rows) + len(detail_rows) + len(booking_traveler_rows) + len(payment_rows)
                 + len(refund_rows) + len(claim_rows) + len(complaint_rows) + len(review_rows))
        print("\n" + "=" * 60)
        print(f"生成完成! 总条目 ≈ {total} 条")
        print(f"  用户 {len(user_rows)} / 设备 {len(device_rows)} / 出行人 {len(traveler_rows)}")
        print(f"  订单 {len(booking_rows)} / 明细 {len(detail_rows)} / 支付 {len(payment_rows)}")
        print("=" * 60)
        print("下一步: python scripts/gen_risk_data.py 100 --balance-pos  生成风控评估")
        print("        python scripts/train_xgb_model.py                训练 XGBoost")

    conn.close()


# 内存映射 (模块级, 供循环引用)
user_travelers: dict[str, list[str]] = {}
user_phone_map: dict[str, str] = {}


def batch_insert(conn, table_cols: str, rows: list[tuple], batch_size: int = 1000):
    """分批 executemany 插入."""
    if not rows:
        return
    sql = f"INSERT INTO {table_cols} VALUES ({','.join(['%s'] * len(rows[0]))})"
    with conn.cursor() as cur:
        for i in range(0, len(rows), batch_size):
            cur.executemany(sql, rows[i:i + batch_size])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="旅游风控系统随机业务数据生成")
    parser.add_argument("--users", type=int, default=5000, help="用户数 (默认 5000)")
    parser.add_argument("--min-orders", type=int, default=1, help="每用户最少订单数")
    parser.add_argument("--max-orders", type=int, default=8, help="每用户最多订单数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()
    main(n_user=args.users, min_orders=args.min_orders, max_orders=args.max_orders, seed=args.seed)
