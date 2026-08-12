"""生成可复现的银行业务数据（信用卡/贷款/转账/登录）。

先运行 ``python scripts/init_db.py --reset --yes`` 建表，再运行本脚本。
主键由 seed 和序号确定，使用 INSERT IGNORE，可重复执行而不制造重复记录。
"""
import argparse
import hashlib
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _connect(args):
    return pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.db,
        charset="utf8mb4",
        autocommit=False,
    )


def generate(args) -> dict[str, int]:
    rng = random.Random(args.seed)
    now = datetime.now().replace(microsecond=0)
    cities = ["北京", "上海", "广州", "深圳", "杭州", "成都"]
    user_count = max(12, args.count // 8)

    users = []
    cards = []
    devices = []
    ips = []
    for i in range(user_count):
        user_id = f"G{args.seed:03d}U{i:05d}"
        home_city = cities[i % len(cities)]
        income = rng.randrange(6_000, 50_001, 500)
        users.append((
            user_id, f"生成客户{i:05d}", _hash(f"id:{args.seed}:{i}"),
            rng.randint(480, 790), now - timedelta(days=rng.randint(30, 3000)),
            rng.randint(1, 3), home_city, income, "正常",
        ))
        card_id = f"G{args.seed:03d}C{i:05d}"
        limit = rng.randrange(20_000, 200_001, 5_000)
        cards.append((
            card_id, user_id, _hash(f"card:{args.seed}:{i}"), "DEMO",
            "信用卡" if i % 2 == 0 else "借记卡", limit,
            round(limit * rng.uniform(0.05, 0.75), 2),
            now - timedelta(days=rng.randint(20, 1800)), "正常",
        ))
        device_id = f"G{args.seed:03d}D{i:05d}"
        devices.append((
            device_id, user_id, _hash(f"device:{args.seed}:{i}"),
            now - timedelta(days=rng.randint(3, 900)), now,
            rng.choice(["Android", "iOS", "Windows"]),
            rng.choice(["App", "Chrome", "Edge"]), 1,
        ))
        ip = f"10.{args.seed % 200}.{i // 250}.{i % 250 + 1}"
        ips.append((ip, "中国", home_city, home_city, "教学网络", 0, 0, 5, now))

    transactions = []
    loans = []
    logins = []
    for i in range(args.count):
        user_idx = rng.randrange(user_count)
        user_id = users[user_idx][0]
        card_id = cards[user_idx][0]
        device_id = devices[user_idx][0]
        ip = ips[user_idx][0]
        home_city = users[user_idx][6]
        risky = i % 10 == 0
        txn_type = "转账" if i % 2 == 0 else "信用卡"
        amount = round(rng.uniform(30_000, 120_000), 2) if risky else round(rng.uniform(20, 8_000), 2)
        geo = cities[(user_idx + 2) % len(cities)] if risky else home_city
        event_time = now - timedelta(minutes=i * 7)
        if risky and i % 20 == 0:
            event_time = event_time.replace(hour=2, minute=i % 60)
        transactions.append((
            f"G{args.seed:03d}T{i:07d}", user_id, txn_type, card_id,
            f"EXT{rng.randint(1, 40):04d}" if txn_type == "转账" else None,
            amount, rng.choice(["手机银行", "网上银行", "POS"]), device_id,
            ip, geo, "零售消费" if txn_type == "信用卡" else None, 1, event_time,
        ))

        if i < max(20, args.count // 3):
            loan_risky = i % 7 == 0
            loans.append((
                f"G{args.seed:03d}L{i:06d}", user_id,
                f"INST-{i % (5 if loan_risky else 2) + 1}",
                round(rng.uniform(100_000, 500_000), 2) if loan_risky else round(rng.uniform(5_000, 80_000), 2),
                rng.choice([6, 12, 24, 36]), "消费", users[user_idx][7],
                round(rng.uniform(0.65, 0.95), 4) if loan_risky else round(rng.uniform(0.05, 0.45), 4),
                device_id, ip, now - timedelta(hours=i * 5), "待审批",
            ))

        if i < max(40, args.count // 2):
            failed = i % 9 == 0
            logins.append((
                f"G{args.seed:03d}I{i:06d}", user_id, device_id, ip, geo,
                0 if failed else 1, "密码错误" if failed else None,
                now - timedelta(minutes=i * 11),
            ))

    statements = [
        ("INSERT IGNORE INTO user_info VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", users, "user_info"),
        ("INSERT IGNORE INTO bank_card VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", cards, "bank_card"),
        ("INSERT IGNORE INTO device_fingerprint "
         "(device_id,user_id,fingerprint_hash,first_seen,last_seen,os,browser,trusted) "
         "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", devices, "device_fingerprint"),
        ("INSERT IGNORE INTO ip_geo_location VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", ips, "ip_geo_location"),
        ("INSERT IGNORE INTO bank_transaction VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", transactions, "bank_transaction"),
        ("INSERT IGNORE INTO loan_application VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", loans, "loan_application"),
        ("INSERT IGNORE INTO login_log VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", logins, "login_log"),
    ]

    counts: dict[str, int] = {}
    conn = _connect(args)
    try:
        with conn.cursor() as cursor:
            for sql, rows, table in statements:
                cursor.executemany(sql, rows)
                counts[table] = len(rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="生成幂等、可复现的银行业务样例数据")
    parser.add_argument("--count", type=int, default=200, help="交易流水数，最少 100")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--host", default=settings.DB_HOST)
    parser.add_argument("--port", type=int, default=settings.DB_PORT)
    parser.add_argument("--user", default=settings.DB_USER)
    parser.add_argument("--password", default=settings.DB_PASSWORD)
    parser.add_argument("--db", default=settings.DB_NAME)
    args = parser.parse_args()
    if args.count < 100:
        parser.error("--count 必须不少于 100")
    counts = generate(args)
    print("银行业务数据生成完成（重复执行不会重复插入）:")
    for table, count in counts.items():
        print(f"  {table:<24} {count:>6}")
    print(f"  {'合计':<24} {sum(counts.values()):>6}")


if __name__ == "__main__":
    main()
