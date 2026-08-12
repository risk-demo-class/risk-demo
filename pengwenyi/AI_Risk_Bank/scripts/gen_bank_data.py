"""
银行风控系统 - 批量业务数据生成脚本 (同步 pymysql)

生成规模 (与 init_bank_data.sql 打样数据共存, ID 不冲突):
  - 用户:   270 个 (正常 U1001~U1230 占 80% + 中风险 M1001~M1040 占 20%)
  - 银行卡: ~800 张 (每人 2~4 张, 含信用卡)
  - 交易:   ~8000 笔 (30 天跨度, 含大额/夜间/异地/代理IP/1h密集/黑卡等风险模式)
  - 贷款:   ~400 笔 (正常少量小额, 中风险大额高负债)
  - 登录:   ~3000 次 (中风险含失败登录)
  - 设备:   ~380 台 (每人 1~3 台)
  - IP:     ~80 个 (60 常用 + 20 代理/秒拨)
  - 黑名单扩展: 2 条 (黑卡 + 代理IP)

高风险 RISK 用户由 scripts/gen_risky_users.py 单独生成 (--count 30).
中风险 M 前缀用户提供部分风险特征 (大额/夜间/换设备), 但不足以触发拒绝级规则.

用法:
  python scripts/gen_bank_data.py
  python scripts/gen_bank_data.py --users 270 --txns 8000
"""
import argparse
import os
import random
import sys
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pymysql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings  # noqa: E402

# ============================================================
# 常量
# ============================================================
NORMAL_PREFIX = "U"     # 正常用户
MID_PREFIX = "M"        # 中风险用户
RISK_PREFIX = "RISK"    # 高风险用户 (由 gen_risky_users.py 生成)
DAYS_SPAN = 30          # 数据跨度 30 天

SURNAMES = ["张", "李", "王", "刘", "陈", "杨", "黄", "赵", "周", "吴",
            "徐", "孙", "马", "朱", "胡", "郭", "何", "林", "罗", "郑"]
GIVEN_NAMES = ["伟", "芳", "娜", "秀英", "敏", "静", "丽", "强", "磊", "军",
               "洋", "勇", "艳", "杰", "娟", "涛", "明", "超", "霞", "平",
               "刚", "桂英", "文", "辉", "力"]

# 城市池: 正常用户的常驻地 (IP/geo 与城市绑定)
CITY_POOL = [
    ("广东-深圳", "10.1."), ("上海-上海", "10.2."), ("北京-北京", "10.3."),
    ("广东-广州", "10.4."), ("浙江-杭州", "10.5."), ("四川-成都", "10.6."),
]
# 代理/秒拨 IP 池 (异地 + is_proxy=1)
PROXY_IPS = [f"45.155.204.{i}" for i in range(10, 30)]
PROXY_CITY = "黑龙江-哈尔滨"   # 与正常用户常驻地不同 → 异地

CHANNELS = ["APP", "网银", "ATM", "第三方"]
OS_POOL = ["iOS 17", "Android 14", "HarmonyOS 4", "Windows 11", "macOS 14"]
BROWSER_POOL = ["Chrome", "Safari", "Edge", "Firefox"]
BANK_CODES = ["ICBC", "CCB", "ABC", "BOC", "CMB", "PSBC", "CITIC", "SPDB"]

# 黑名单扩展: 批量黑卡 (配合 R030 黑卡拦截)
BLACK_CARD_ID = "card_black_b001"

# ============================================================
# 工具
# ============================================================
def _rand_time(days_span: int = DAYS_SPAN) -> datetime:
    """最近 days_span 天内随机时刻"""
    now = datetime.now()
    d = now - timedelta(days=random.uniform(0, days_span))
    return d.replace(microsecond=0)


def _rand_name() -> str:
    return random.choice(SURNAMES) + random.choice(GIVEN_NAMES)


def _rand_os_browser():
    return random.choice(OS_POOL), random.choice(BROWSER_POOL)


# ============================================================
# 主生成逻辑
# ============================================================
def gen_users(n_normal: int, n_mid: int):
    """生成用户: 正常 + 中风险"""
    rows = []
    for i in range(1, n_normal + 1):
        uid = f"{NORMAL_PREFIX}{1000 + i}"
        credit = random.randint(600, 780)
        kyc = random.choices([2, 3, 4], weights=[0.6, 0.25, 0.15])[0]
        register_at = datetime.now() - timedelta(days=random.randint(200, 800))
        rows.append((uid, _rand_name(), f"HASH_{uid}", credit, register_at, kyc))
    for i in range(1, n_mid + 1):
        uid = f"{MID_PREFIX}{1000 + i}"
        credit = random.randint(500, 599)
        kyc = random.choices([1, 2], weights=[0.4, 0.6])[0]
        register_at = datetime.now() - timedelta(days=random.randint(60, 200))
        rows.append((uid, _rand_name(), f"HASH_{uid}", credit, register_at, kyc))
    return rows


def gen_cards(users):
    """每用户 2~4 张卡 (借记卡为主, 30% 用户含信用卡)"""
    rows = []
    for uid, _, _, credit, _, _ in users:
        n_cards = random.randint(2, 4)
        for j in range(1, n_cards + 1):
            card_id = f"card_{uid}_c{j}"
            is_credit = (j >= 2 and random.random() < 0.45)
            if is_credit:
                # 信用卡额度与信用分挂钩: 高分高额度
                limit = int(credit * 80 + random.uniform(-5000, 15000))
                limit = max(3000, min(200000, limit))
                rows.append((card_id, uid, f"CARDHASH_{card_id}",
                             random.choice(BANK_CODES), "信用卡", limit))
            else:
                rows.append((card_id, uid, f"CARDHASH_{card_id}",
                             random.choice(BANK_CODES), "借记卡", 0))
    return rows


def gen_ips():
    """IP 地理位置表: 60 常用 + 20 代理/秒拨"""
    rows = []
    for idx, (geo, prefix) in enumerate(CITY_POOL):
        for k in range(1, 11):
            city = geo.split("-")[1]
            rows.append((f"{prefix}{k}", "中国", geo.split("-")[0], city,
                         random.choice(["中国电信", "中国联通", "中国移动"]), 0, 0))
    for i, ip in enumerate(PROXY_IPS):
        rows.append((ip, "美国", "California", "LA", "ProxyLayer",
                     1, 1 if i % 3 == 0 else 0))
    return rows


def gen_devices(users):
    """每人 1~3 台设备"""
    rows = []
    for uid, _, _, _, _, _ in users:
        n_dev = 1 if uid.startswith(NORMAL_PREFIX) and random.random() < 0.85 else random.randint(2, 3)
        for j in range(1, n_dev + 1):
            dev_id = f"dev_{uid}_{j}"
            os_name, browser = _rand_os_browser()
            first_seen = _rand_time(DAYS_SPAN + 300)
            rows.append((dev_id, uid, f"FPHASH_{dev_id}", first_seen,
                         datetime.now(), os_name, browser))
    return rows


def gen_txns(users, cards, dev_by_user, ips_by_user, target_count: int):
    """生成交易: 含风险模式 (大额/夜间/异地/代理IP/1h密集/黑卡归集)"""
    rows = []
    cards_by_user = {}
    for cid, uid, *_ in cards:
        cards_by_user.setdefault(uid, []).append(cid)
    all_uid = list(cards_by_user.keys())
    card_owner = {cid: uid for cid, uid, *_ in cards}

    seq = 1
    while len(rows) < target_count:
        uid = random.choice(all_uid)
        is_mid = uid.startswith(MID_PREFIX)
        own_cards = cards_by_user[uid]
        from_card = random.choice(own_cards)
        # 收款卡: 随机其他用户 (或黑卡)
        if is_mid and random.random() < 0.08:
            to_card = BLACK_CARD_ID
        else:
            others = [c for c in all_uid if c != uid]
            to_uid = random.choice(others)
            to_card = random.choice(cards_by_user[to_uid])

        # 金额分布: 中风险偏大
        if is_mid:
            amount = random.uniform(500, 50000)
            if random.random() < 0.3:
                amount = random.uniform(20000, 60000)
        else:
            amount = random.uniform(50, 5000)
            if random.random() < 0.05:
                amount = random.uniform(10000, 40000)
        amount = round(amount, 2)

        # 时间: 30% 概率夜间
        txn_time = _rand_time()
        if random.random() < (0.25 if is_mid else 0.10):
            txn_time = txn_time.replace(hour=random.randint(0, 4), minute=random.randint(0, 59))

        # 设备/IP
        device_id = random.choice(dev_by_user[uid])
        if is_mid and random.random() < 0.2:
            ip = random.choice(PROXY_IPS)
            geo = PROXY_CITY
        else:
            ip, geo = random.choice(ips_by_user[uid])

        channel = random.choices(CHANNELS, weights=[0.55, 0.2, 0.1, 0.15])[0]
        rows.append((f"txn_b_{seq:06d}", from_card, to_card, amount, channel,
                     device_id, ip, geo, txn_time))
        seq += 1

        # 中风险 4% 概率: 1 小时内密集多笔 (命中 R002 凌晨密集 / R008 多卡归集)
        if is_mid and random.random() < 0.04 and len(rows) < target_count:
            burst = random.randint(2, 4)
            for _ in range(burst):
                b_from = random.choice(own_cards)
                b_to = BLACK_CARD_ID if random.random() < 0.5 else random.choice(
                    cards_by_user[random.choice([c for c in all_uid if c != uid])])
                b_time = txn_time + timedelta(minutes=random.randint(2, 50))
                rows.append((f"txn_b_{seq:06d}", b_from, b_to,
                             round(random.uniform(1000, 30000), 2),
                             random.choice(CHANNELS), device_id, ip, geo, b_time))
                seq += 1
                if len(rows) >= target_count:
                    break
    return rows


def gen_loans(users, target_count: int):
    """贷款申请: 正常用户少量小额, 中风险大额高负债"""
    rows = []
    seq = 1
    for uid, _, _, credit, _, _ in users:
        is_mid = uid.startswith(MID_PREFIX)
        if is_mid:
            n = random.randint(3, 6)
        else:
            n = random.randint(0, 2) if random.random() < 0.55 else 0
        for _ in range(n):
            if is_mid:
                amount = random.uniform(100000, 500000)
                income = random.uniform(4000, 10000)
                debt = random.uniform(0.40, 0.70)
                purpose = random.choice(["周转", "投资", "装修", "购车"])
            else:
                amount = random.uniform(50000, 300000)
                income = random.uniform(8000, 50000)
                debt = random.uniform(0.15, 0.40)
                purpose = random.choice(["装修", "购车", "教育", "旅游", "消费"])
            rows.append((f"loan_b_{seq:04d}", uid, round(amount, 2),
                         random.randint(12, 36), purpose, round(income, 2),
                         round(debt, 4), _rand_time()))
            seq += 1
        if len(rows) >= target_count:
            break
    return rows


def gen_logins(users, dev_by_user, ips_by_user, target_count: int):
    """登录日志: 正常高成功, 中风险含失败"""
    rows = []
    seq = 1
    for uid, *_ in users:
        is_mid = uid.startswith(MID_PREFIX)
        n = random.randint(3, 20) if not is_mid else random.randint(10, 40)
        for _ in range(n):
            device_id = random.choice(dev_by_user[uid])
            if is_mid and random.random() < 0.2:
                ip, geo = random.choice(PROXY_IPS), PROXY_CITY
            else:
                ip, geo = random.choice(ips_by_user[uid])
            success = 0 if (is_mid and random.random() < 0.15) else 1
            rows.append((f"login_b_{seq:05d}", uid, device_id, ip, geo,
                         success, _rand_time()))
            seq += 1
        if len(rows) >= target_count:
            break
    return rows


def gen_blacklist_extra():
    """黑名单扩展: 批量黑卡 + 代理 IP"""
    return [
        ("银行卡号", BLACK_CARD_ID, "批量造数: 涉赌涉诈归集卡 (监管止付名单)", None),
        ("IP", "45.155.204.12", "批量造数: 秒拨代理池 IP", None),
    ]


# ============================================================
# 入库
# ============================================================
def _executemany(cur, sql, rows, batch=500):
    for i in range(0, len(rows), batch):
        cur.executemany(sql, rows[i:i + batch])
        print(f"    已写入 {min(i + batch, len(rows))}/{len(rows)} 条")


def main():
    parser = argparse.ArgumentParser(description="银行风控系统 - 批量业务数据生成")
    parser.add_argument("--users", type=int, default=270, help="非高风险用户数 (默认 270: 80% 正常 + 20% 中风险)")
    parser.add_argument("--txns", type=int, default=8000, help="目标交易数 (默认 8000)")
    args = parser.parse_args()

    n_normal = int(args.users * 0.8)
    n_mid = args.users - n_normal
    print(f"开始生成批量业务数据: {args.users} 用户 ({n_normal} 正常 + {n_mid} 中风险), 目标交易 {args.txns} 笔")

    conn = pymysql.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        database=settings.DB_NAME, charset="utf8mb4",
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            # 1. 用户
            print("[1/8] 生成用户...")
            users = gen_users(n_normal, n_mid)
            _executemany(cur, """
                INSERT INTO user_info (user_id, name, id_card_hash, credit_score, register_at, kyc_level)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, users)
            print(f"  用户: {len(users)} 个")

            # 2. 银行卡
            print("[2/8] 生成银行卡...")
            cards = gen_cards(users)
            _executemany(cur, """
                INSERT INTO bank_card (card_id, user_id, card_no_hash, bank_code, card_type, credit_limit)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, cards)
            print(f"  银行卡: {len(cards)} 张")

            # 3. IP 地理位置
            print("[3/8] 生成 IP 地理位置...")
            ips = gen_ips()
            _executemany(cur, """
                INSERT INTO ip_geo_location (ip, country, province, city, isp, is_proxy, is_tor)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, ips)
            print(f"  IP: {len(ips)} 个")

            # 4. 设备指纹
            print("[4/8] 生成设备指纹...")
            devices = gen_devices(users)
            _executemany(cur, """
                INSERT INTO device_fingerprint (device_id, user_id, fingerprint_hash, first_seen, last_seen, os, browser)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, devices)
            print(f"  设备: {len(devices)} 台")

            # 用户 → 设备/IP 映射 (供交易/登录使用)
            dev_by_user, ips_by_user = {}, {}
            for dev_id, uid, *_ in devices:
                dev_by_user.setdefault(uid, []).append(dev_id)
            # 常用 IP 按网段归属城市 (10.1.x → 深圳, 10.2.x → 上海 ...)
            normal_ips_by_geo = {}
            for geo, prefix in CITY_POOL:
                normal_ips_by_geo[geo] = [f"{prefix}{k}" for k in range(1, 11)]
            for uid, *_ in users:
                geo = random.choice(CITY_POOL)[0]
                ips_by_user[uid] = [(ip, geo) for ip in normal_ips_by_geo[geo]]

            # 5. 交易
            print("[5/8] 生成交易...")
            txns = gen_txns(users, cards, dev_by_user, ips_by_user, args.txns)
            _executemany(cur, """
                INSERT INTO transaction (txn_id, from_card, to_card, amount, channel, device_id, ip, geo, txn_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, txns, batch=800)
            print(f"  交易: {len(txns)} 笔")

            # 6. 贷款
            print("[6/8] 生成贷款申请...")
            loans = gen_loans(users, 400)
            _executemany(cur, """
                INSERT INTO loan_application (loan_id, user_id, amount, term_months, purpose, monthly_income, debt_ratio, apply_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, loans)
            print(f"  贷款: {len(loans)} 笔")

            # 7. 登录日志
            print("[7/8] 生成登录日志...")
            logins = gen_logins(users, dev_by_user, ips_by_user, 3000)
            _executemany(cur, """
                INSERT INTO login_log (login_id, user_id, device_id, ip, geo, success, login_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, logins)
            print(f"  登录: {len(logins)} 次")

            # 8. 黑名单扩展
            print("[8/8] 生成黑名单扩展...")
            bl = gen_blacklist_extra()
            _executemany(cur, """
                INSERT INTO blacklist_extra (type, value, reason, expire_at)
                VALUES (%s, %s, %s, %s)
            """, bl)
            print(f"  黑名单扩展: {len(bl)} 条")

        conn.commit()
        print("\n完成! 批量业务数据已写入 risk_bank 库.")
        print(f"  用户 {len(users)} / 卡 {len(cards)} / 交易 {len(txns)} / 贷款 {len(loans)} / 登录 {len(logins)}")
        print(f"  下一步: python scripts/gen_risky_users.py --count 30")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
