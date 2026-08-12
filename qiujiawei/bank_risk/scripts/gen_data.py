"""
银行风控系统 - 测试数据生成脚本

造数据顺序:
  1. user_info       (N 个用户)
  2. bank_card        (每用户 1-3 张卡)
  3. device_fingerprint (每用户 1-2 个设备)
  4. ip_geo_location  (N 个 IP 地理位置记录)
  5. transaction     (N×3 笔交易)
  6. loan_application (N/3 条贷款申请)
  7. login_log       (N×2 条登录记录)

用法:
  python -m bank_risk.scripts.gen_data              # 默认 100 用户
  python -m bank_risk.scripts.gen_data --count 50   # 50 用户
  python -m bank_risk.scripts.gen_data --clean       # 先清空再造
"""
import argparse
import asyncio
import hashlib
import random
import sys
from datetime import datetime, timedelta

import aiomysql

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 3306
DEFAULT_USER = "root"
DEFAULT_PASSWORD = "123321"
DEFAULT_DB = "bank_risk"

# 随机数据池
NAMES = ["张伟", "王芳", "李强", "刘洋", "陈静", "杨杰", "赵敏", "黄磊", "周婷", "吴昊",
         "徐丽", "孙鹏", "马超", "朱琳", "胡军", "郭敏", "林浩", "何婷", "高翔", "罗静",
         "郑伟", "梁宇", "谢雯", "宋佳", "唐磊", "韩雪", "冯刚", "邓婕", "曹辉", "彭丽"]

PROVINCES = ["北京", "上海", "广东", "浙江", "江苏", "四川", "湖北", "福建", "山东", "河南"]
CITIES = {"北京": "北京", "上海": "上海", "广东": "深圳", "浙江": "杭州", "江苏": "南京",
           "四川": "成都", "湖北": "武汉", "福建": "厦门", "山东": "青岛", "河南": "郑州"}
BANK_CODES = ["ICBC", "ABC", "BOC", "CCB", "BCM", "CMB", "CMBC", "SPDB", "CITIC", "CEB"]
CARD_TYPES = ["debit", "credit", "savings"]
CHANNELS = ["online", "atm", "counter", "mobile", "pos"]
TXN_TYPES = ["transfer", "payment", "withdrawal", "deposit"]
OSES = ["Windows", "macOS", "iOS", "Android", "Linux"]
BROWSERS = ["Chrome", "Safari", "Firefox", "Edge"]
LOAN_PURPOSES = ["购房", "购车", "装修", "教育", "医疗", "经营周转", "消费"]
ISPS = ["中国电信", "中国联通", "中国移动", "长城宽带"]


def random_ip():
    return f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def random_hash(prefix=""):
    """生成随机哈希 (模拟卡号/身份证哈希)"""
    s = prefix + str(random.random()) + str(datetime.now().timestamp())
    return hashlib.sha256(s.encode()).hexdigest()[:32]


def random_phone():
    prefixes = ["138", "139", "136", "135", "158", "159", "186", "188", "133", "189"]
    return random.choice(prefixes) + "".join([str(random.randint(0,9)) for _ in range(8)])


def random_datetime(days_back=90):
    """生成最近 N 天内的随机时间"""
    base = datetime.now() - timedelta(days=days_back)
    offset = timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return base + offset


async def clean_data(conn):
    """清空所有业务表数据 (保留表结构)"""
    print("清空业务数据...")
    async with conn.cursor() as cur:
        for table in ["transaction", "loan_application", "login_log",
                       "device_fingerprint", "ip_geo_location", "blacklist_extra",
                       "bank_card", "user_info"]:
            await cur.execute(f"DELETE FROM `{table}`")
    print("  已清空")


async def gen_users(conn, n):
    """生成 N 个用户"""
    print(f"生成 {n} 个用户...")
    sql = """INSERT INTO user_info
        (user_id, name, id_card_hash, credit_score, register_at, kyc_level, phone, email, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    rows = []
    for i in range(n):
        uid = f"U{10001 + i:05d}"
        name = random.choice(NAMES)
        id_hash = random_hash(uid)
        credit = random.randint(300, 850)
        reg_time = random_datetime(365)
        kyc = random.choices([0, 1, 2, 3], weights=[10, 30, 40, 20])[0]
        phone = random_phone()
        email = f"{uid.lower()}@{'gmail' if random.random()>0.5 else 'qq'}.com"
        status = random.choices(["active", "frozen", "closed"], weights=[90, 7, 3])[0]
        rows.append((uid, name, id_hash, credit, reg_time, kyc, phone, email, status))
    async with conn.cursor() as cur:
        await cur.executemany(sql, rows)
    print(f"  插入 {len(rows)} 条")
    return [r[0] for r in rows]  # 返回 user_id 列表


async def gen_bank_cards(conn, user_ids):
    """每用户 1-3 张卡"""
    print("生成银行卡...")
    sql = """INSERT INTO bank_card
        (card_id, user_id, card_no_hash, bank_code, card_type, credit_limit, balance, status, create_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    rows = []
    card_idx = 0
    for uid in user_ids:
        n_cards = random.choices([1, 2, 3], weights=[50, 35, 15])[0]
        for _ in range(n_cards):
            card_idx += 1
            cid = f"C{20001 + card_idx:05d}"
            card_hash = random_hash(cid)
            bank_code = random.choice(BANK_CODES)
            card_type = random.choice(CARD_TYPES)
            if card_type == "credit":
                limit = random.choice([5000, 10000, 20000, 50000, 100000])
                balance = random.choice([0, random.randint(0, int(limit/2))])
            else:
                limit = None
                balance = random.randint(100, 500000)
            status = random.choices(["active", "frozen", "closed"], weights=[90, 7, 3])[0]
            rows.append((cid, uid, card_hash, bank_code, card_type, limit, balance, status, random_datetime(300)))
    async with conn.cursor() as cur:
        await cur.executemany(sql, rows)
    print(f"  插入 {len(rows)} 条")
    return rows


async def gen_devices(conn, user_ids):
    """每用户 1-2 个设备"""
    print("生成设备指纹...")
    sql = """INSERT INTO device_fingerprint
        (device_id, user_id, fingerprint_hash, first_seen, last_seen, os, browser, risk_score)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
    rows = []
    dev_idx = 0
    for uid in user_ids:
        n_devs = random.choices([1, 2], weights=[70, 30])[0]
        for _ in range(n_devs):
            dev_idx += 1
            did = f"D{hex(dev_idx + 0x1000)[2:].upper()}"
            fp_hash = random_hash(did)
            first = random_datetime(365)
            last = first + timedelta(days=random.randint(0, 30))
            os_name = random.choice(OSES)
            browser = random.choice(BROWSERS)
            risk = random.choices([0, 10, 30, 50, 80], weights=[70, 15, 8, 5, 2])[0]
            rows.append((did, uid, fp_hash, first, last, os_name, browser, risk))
    async with conn.cursor() as cur:
        await cur.executemany(sql, rows)
    print(f"  插入 {len(rows)} 条")
    # 返回 device_id → user_id 映射
    return {r[0]: r[1] for r in rows}


async def gen_ip_geo(conn, n):
    """生成 N 个 IP 地理位置"""
    print(f"生成 {n} 个 IP 地理位置...")
    sql = """INSERT INTO ip_geo_location
        (ip, country, province, city, isp, is_proxy, is_tor, last_update)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""
    rows = []
    seen = set()
    for _ in range(n):
        ip = random_ip()
        if ip in seen:
            continue
        seen.add(ip)
        prov = random.choice(PROVINCES)
        city = CITIES[prov]
        isp = random.choice(ISPS)
        is_proxy = random.choices([0, 1], weights=[95, 5])[0]
        is_tor = random.choices([0, 1], weights=[98, 2])[0]
        rows.append((ip, "中国", prov, city, isp, is_proxy, is_tor, datetime.now()))
    async with conn.cursor() as cur:
        await cur.executemany(sql, rows)
    print(f"  插入 {len(rows)} 条")
    return [r[0] for r in rows]  # 返回 IP 列表


async def gen_transactions(conn, user_ids, card_rows, device_map, ip_list, multiplier=3):
    """每用户 multiplier 笔交易"""
    print(f"生成交易记录 (每用户 {multiplier} 笔)...")
    sql = """INSERT INTO transaction
        (txn_id, from_card, to_card, user_id, amount, channel, txn_type, device_id, ip, geo, status, txn_at, create_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    # 构建 user_id → [card_id] 映射
    user_cards = {}
    for r in card_rows:
        uid = r[1]
        cid = r[0]
        user_cards.setdefault(uid, []).append(cid)
    # 构建 user_id → [device_id] 映射
    user_devices = {}
    for dev_id, uid in device_map.items():
        user_devices.setdefault(uid, []).append(dev_id)

    rows = []
    txn_idx = 0
    for uid in user_ids:
        cards = user_cards.get(uid, [])
        if not cards:
            continue
        devices = user_devices.get(uid, [])
        for _ in range(multiplier):
            txn_idx += 1
            tid = f"T{30001 + txn_idx:06d}"
            from_card = random.choice(cards)
            to_card = random.choice(cards) if random.random() > 0.3 else None
            amount = round(random.choices(
                [random.uniform(10, 1000), random.uniform(1000, 10000),
                 random.uniform(10000, 60000), random.uniform(60000, 200000)],
                weights=[40, 35, 20, 5]
            )[0], 2)
            channel = random.choice(CHANNELS)
            txn_type = random.choice(TXN_TYPES)
            device_id = random.choice(devices) if devices else None
            ip = random.choice(ip_list) if ip_list else None
            prov = random.choice(PROVINCES)
            geo = f"{prov}/{CITIES[prov]}" if random.random() > 0.1 else None
            status = random.choices(["success", "pending", "failed"], weights=[85, 10, 5])[0]
            txn_time = random_datetime(30)
            rows.append((tid, from_card, to_card, uid, amount, channel, txn_type,
                         device_id, ip, geo, status, txn_time, datetime.now()))
    async with conn.cursor() as cur:
        await cur.executemany(sql, rows)
    print(f"  插入 {len(rows)} 条")


async def gen_loan_applications(conn, user_ids, ratio=3):
    """每 ratio 个用户 1 条贷款申请"""
    print(f"生成贷款申请 (每 {ratio} 用户 1 条)...")
    sql = """INSERT INTO loan_application
        (loan_id, user_id, amount, term_months, purpose, monthly_income, debt_ratio, status, apply_at, create_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    rows = []
    loan_idx = 0
    for uid in user_ids[::ratio]:
        loan_idx += 1
        lid = f"L{40001 + loan_idx:05d}"
        amount = round(random.uniform(50000, 500000), 2)
        term = random.choice([6, 12, 24, 36, 60])
        purpose = random.choice(LOAN_PURPOSES)
        income = round(random.uniform(5000, 50000), 2)
        debt = round(random.uniform(0.05, 0.8), 4)
        status = random.choices(["pending", "approved", "rejected", "disbursed"], weights=[30, 30, 20, 20])[0]
        apply_time = random_datetime(60)
        rows.append((lid, uid, amount, term, purpose, income, debt, status, apply_time, datetime.now()))
    async with conn.cursor() as cur:
        await cur.executemany(sql, rows)
    print(f"  插入 {len(rows)} 条")


async def gen_login_logs(conn, user_ids, device_map, ip_list, multiplier=2):
    """每用户 multiplier 条登录记录"""
    print(f"生成登录日志 (每用户 {multiplier} 条)...")
    sql = """INSERT INTO login_log
        (user_id, device_id, ip, geo, success, fail_reason, login_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)"""
    user_devices = {}
    for dev_id, uid in device_map.items():
        user_devices.setdefault(uid, []).append(dev_id)

    rows = []
    for uid in user_ids:
        devices = user_devices.get(uid, [])
        for _ in range(multiplier):
            device_id = random.choice(devices) if devices else None
            ip = random.choice(ip_list) if ip_list else None
            prov = random.choice(PROVINCES)
            geo = f"{prov}/{CITIES[prov]}"
            success = random.choices([1, 0], weights=[88, 12])[0]
            fail_reason = None if success else random.choice(["密码错误", "验证码超时", "设备异常", "IP风控"])
            login_time = random_datetime(14)
            rows.append((uid, device_id, ip, geo, success, fail_reason, login_time))
    async with conn.cursor() as cur:
        await cur.executemany(sql, rows)
    print(f"  插入 {len(rows)} 条")


async def main():
    parser = argparse.ArgumentParser(description="银行风控系统 - 测试数据生成")
    parser.add_argument("--count", type=int, default=100, help="用户数量 (默认 100)")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--clean", action="store_true", help="先清空再造")
    args = parser.parse_args()

    print("=" * 60)
    print(f"银行风控系统 - 测试数据生成")
    print(f"目标: {args.user}@{args.host}:{args.port}/{args.db}")
    print(f"用户数: {args.count}")
    print("=" * 60)

    conn = await aiomysql.connect(
        host=args.host, port=args.port, user=args.user,
        password=args.password, db=args.db, charset="utf8mb4", autocommit=True,
    )

    try:
        if args.clean:
            await clean_data(conn)

        # 1. 用户
        user_ids = await gen_users(conn, args.count)

        # 2. 银行卡
        card_rows = await gen_bank_cards(conn, user_ids)

        # 3. 设备指纹
        device_map = await gen_devices(conn, user_ids)

        # 4. IP 地理位置库
        ip_list = await gen_ip_geo(conn, max(args.count, 50))

        # 5. 交易记录
        await gen_transactions(conn, user_ids, card_rows, device_map, ip_list, multiplier=3)

        # 6. 贷款申请
        await gen_loan_applications(conn, user_ids, ratio=3)

        # 7. 登录日志
        await gen_login_logs(conn, user_ids, device_map, ip_list, multiplier=2)

        # 统计
        print("\n" + "=" * 60)
        print("数据生成完成! 各表行数:")
        tables = ["user_info", "bank_card", "transaction", "loan_application",
                  "login_log", "device_fingerprint", "ip_geo_location"]
        async with conn.cursor() as cur:
            for t in tables:
                await cur.execute(f"SELECT COUNT(*) FROM `{t}`")
                cnt = (await cur.fetchone())[0]
                print(f"  {t:<25} {cnt:>6} 行")
        print("=" * 60)
    finally:
        await conn.ensure_closed()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
