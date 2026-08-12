"""
旅游风控系统 - 生成高风险演示用户 (RISK001-RISK030)
================
用于规则引擎单测和前端演示, 每个用户带一种典型旅游风险画像:
  RISK001 高退改率用户    (退改率 80%+)
  RISK002 大额订单用户    (单笔 5w+ 一票否决)
  RISK003 深夜下单用户    (0-6 点高频下单)
  RISK004 多设备用户      (6 台设备)
  RISK005 批量囤票用户    (单笔 8+ 出行人)
  ... 更多 (出行人手机号聚集 / 理赔骗保 / 恶意投诉 / 刷评 / 出境游大额)

用法:
  python scripts/gen_risky_users.py
  python scripts/gen_risky_users.py --count 30
"""
import argparse
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql
from dotenv import load_dotenv

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


def _connect():
    return pymysql.connect(**DB_CONFIG)


def main(count: int = 30):
    conn = _connect()
    cur = conn.cursor()

    # 读取产品 (按价格排序, 高价产品用于大额订单)
    cur.execute("SELECT product_id, price, is_overseas FROM product_info ORDER BY price DESC")
    products = [(r[0], float(r[1]), int(r[2])) for r in cur.fetchall()]
    # 读取供应商/区域
    cur.execute("SELECT supplier_id FROM supplier_info")
    suppliers = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT country, province, city FROM region")
    regions = cur.fetchall()

    print("=" * 60)
    print(f"生成高风险演示用户 RISK001-RISK{count:03d}")
    print("=" * 60)

    for i in range(1, count + 1):
        uid = f"RISK{i:03d}"
        _cleanup_user(conn, uid)
        _generate_user(conn, cur, uid, products, suppliers, regions, i)
        print(f"  ✓ {uid} 生成完成")

    cur.close()
    conn.close()
    print("\n完成! 可用这些用户在前端做风控检查演示:")
    print("  例如: POST /api/risk/check  event_type=下单, user_id=RISK001, source_id=<订单ID>")


def _cleanup_user(conn, uid: str):
    """删除用户相关数据 (幂等重跑)."""
    with conn.cursor() as cur:
        # 先取设备 ID, 再删绑定, 最后删设备 (避免子查询引用已删行)
        cur.execute("SELECT device_id FROM user_device WHERE user_id=%s", (uid,))
        device_ids = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT booking_id FROM booking_info WHERE user_id=%s", (uid,))
        booking_ids = [r[0] for r in cur.fetchall()]
        for bid in booking_ids:
            cur.execute("DELETE FROM booking_traveler WHERE booking_id=%s", (bid,))
            cur.execute("DELETE FROM booking_detail WHERE booking_id=%s", (bid,))
            cur.execute("DELETE FROM payment_info WHERE booking_id=%s", (bid,))
            cur.execute("DELETE FROM refund_change WHERE booking_id=%s", (bid,))
            cur.execute("DELETE FROM complaint_info WHERE booking_id=%s", (bid,))
            cur.execute("DELETE FROM claim_info WHERE booking_id=%s", (bid,))
            cur.execute("DELETE FROM review_info WHERE booking_id=%s", (bid,))
        cur.execute("DELETE FROM booking_info WHERE user_id=%s", (uid,))
        cur.execute("DELETE FROM booking_traveler WHERE traveler_id IN (SELECT traveler_id FROM traveler_info WHERE user_id=%s)", (uid,))
        cur.execute("DELETE FROM traveler_info WHERE user_id=%s", (uid,))
        cur.execute("DELETE FROM user_device WHERE user_id=%s", (uid,))
        for dev_id in device_ids:
            cur.execute("DELETE FROM device_info WHERE device_id=%s", (dev_id,))
        cur.execute("DELETE FROM user_info WHERE user_id=%s", (uid,))
        cur.execute("DELETE FROM risk_user_profile WHERE user_id=%s", (uid,))
        cur.execute("DELETE FROM risk_blacklist WHERE blacklist_value=%s AND blacklist_type='用户'", (uid,))


def _generate_user(conn, cur, uid: str, products, suppliers, regions, idx: int):
    """生成 1 个高风险用户 (含订单/出行人/退改/理赔/投诉)."""
    now = datetime.now()
    reg_time = now - timedelta(days=300)
    phone = f"199{idx:08d}"
    cur.execute(
        "INSERT INTO user_info (user_id, phone, register_time, register_channel, is_verified) VALUES (%s,%s,%s,'APP',0)",
        (uid, phone, reg_time),
    )

    # 设备: 默认 3 台, 多设备画像更多
    n_dev = 6 if idx in (4, 12, 22) else 3
    dev_ids = []
    for d in range(n_dev):
        dev_id = f"RDEV{idx:03d}{d}"
        dev_ids.append(dev_id)
        cur.execute(
            "INSERT INTO device_info (device_id, device_model, os, browser) VALUES (%s,%s,%s,%s)",
            (dev_id, f"Model{idx}-{d}", "Android 14", "Chrome"),
        )
        cur.execute(
            "INSERT INTO user_device (user_id, device_id, bind_time) VALUES (%s,%s,%s)",
            (uid, dev_id, reg_time + timedelta(days=d * 40)),
        )

    # 出行人
    n_travelers = 9 if idx == 5 else (8 if idx == 19 else 4)
    traveler_ids = []
    for t in range(n_travelers):
        tid = f"RTRV{idx:03d}{t}"
        traveler_ids.append(tid)
        cur.execute(
            "INSERT INTO traveler_info (traveler_id, user_id, traveler_name, id_card_no, phone) VALUES (%s,%s,%s,%s,%s)",
            (tid, uid, f"出行人{idx}_{t}", f"{idx:018d}{t}", f"15{idx:03d}{t:05d}" if t > 0 else phone),
        )

    # 订单: 高风险用户 8-15 单
    n_orders = 10 + (idx % 6)
    for oi in range(n_orders):
        bid = f"RISKB{idx:03d}{oi:02d}"
        create_time = now - timedelta(days=random.randint(1, 200), hours=random.randint(0, 23))
        # 深夜下单画像: 全部凌晨
        if idx in (3, 23, 29):
            create_time = create_time.replace(hour=random.choice([0, 1, 2, 3, 4, 5]), minute=random.randint(0, 59))

        # 大额画像: 前 3 单 5w+
        if idx in (2, 22, 25) and oi < 3:
            pid, price, overseas = products[0]
            price = price * 2
        else:
            pid, price, overseas = random.choice(products)
        qty = random.randint(1, 5)
        total = round(price * qty, 2)
        discount = round(total * 0.1, 2)
        final = round(total - discount, 2)
        departure = create_time + timedelta(days=random.randint(1, 30))

        status = "已完成" if oi < n_orders - 2 else "已支付"
        traveler_count = min(len(traveler_ids), 9 if (idx == 5 and oi < 2) else random.randint(1, 6))
        chosen = traveler_ids[:traveler_count]
        cur.execute(
            "INSERT INTO booking_info (booking_id, create_time, payment_time, departure_time, end_time, user_id,"
            " contact_phone, booking_status, traveler_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (bid, create_time, create_time + timedelta(minutes=1), departure, departure + timedelta(days=random.randint(1, 9)),
             uid, phone, status, traveler_count),
        )
        cur.execute(
            "INSERT INTO booking_detail (booking_detail_id, booking_id, product_id, product_name, quantity, unit_price,"
            " total_amount, discount_amount, final_amount) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (f"RD{bid}", bid, pid, pid, qty, price, total, discount, final),
        )
        for tid in chosen:
            cur.execute(
                "INSERT INTO booking_traveler (booking_id, traveler_id, relation) VALUES (%s,%s,%s)",
                (bid, tid, "同行人"),
            )
        cur.execute(
            "INSERT INTO payment_info (payment_id, booking_id, user_id, pay_time, pay_amount, pay_channel, pay_status)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (f"RPAY{bid}", bid, uid, create_time + timedelta(minutes=1), final, "银行卡", "成功"),
        )

        # 退改: 高退改画像用户几乎全退
        if idx in (1, 11, 21, 27) and random.random() < 0.8:
            cur.execute(
                "INSERT INTO refund_change (refund_id, create_time, complete_time, booking_id, refund_amount,"
                " refund_type, refund_reason, refund_status) VALUES (%s,%s,%s,%s,%s,%s,%s,'已完成')",
                (f"RRF{bid}", create_time + timedelta(days=1), create_time + timedelta(days=2),
                 bid, final, "退订", "行程取消", ),
            )
        # 理赔: 骗保画像
        if idx in (6, 16, 26) and random.random() < 0.6:
            cur.execute(
                "INSERT INTO claim_info (claim_id, booking_id, user_id, claim_type, claim_amount, apply_time, claim_status)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (f"RCL{bid}", bid, uid, "航班延误", 600.0, create_time + timedelta(days=1), "已通过"),
            )
        # 投诉: 恶意投诉画像
        if idx in (7, 17, 27, 28) and random.random() < 0.5:
            cur.execute(
                "INSERT INTO complaint_info (complaint_id, booking_id, user_id, complaint_time, complaint_content,"
                " complaint_type, complaint_status) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (f"RCP{bid}", bid, uid, create_time + timedelta(days=2), "服务与描述不符，要求全额退款", "服务质量", "已完成"),
            )
        # 点评: 刷评画像 (订单少但点评多)
        if idx in (8, 18, 28) and oi < 12:
            cur.execute(
                "INSERT INTO review_info (review_id, booking_id, product_id, user_id, rating, content, review_time, is_verified)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,1)",
                (f"RRV{bid}", bid, pid, uid, 5, "很好", create_time + timedelta(days=3)),
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="生成高风险演示用户")
    parser.add_argument("--count", type=int, default=30, help="用户数 (默认 30)")
    args = parser.parse_args()
    main(args.count)
