"""
银行风控系统 - RISK 高风险用户生成脚本 (同步 pymysql)

生成 --count 个 RISK 前缀高风险用户, 每个用户配套:
  - 低信用分 (350~480) / KYC L1 / 注册 <60 天 (新客)
  - 1~2 张卡 (含低额度信用卡)
  - 8~15 笔高风险交易: 异地大额 / 夜间密集 / 代理IP / 黑卡 / 多卡归集
    (命中 R001 异地大额 / R002 凌晨密集 / R008 多卡归集 / R015 低信用大额 / R030 黑卡)
  - 1~2 笔贷款: 大额高负债 (命中 R010 高负债大额申贷 / R012 信贷申请突击)
  - 5~15 次登录: 含失败登录 (命中 R003 深夜异常登录 / R005 新设备)
  - 2~3 台设备 (含 <7 天新设备 → 命中 R005 新设备大额)
  - 代理/秒拨 IP (命中 R025 IP代理)

用途: gen_risk_data.py --balance-pos 会 80% 概率从 RISK 用户挑样本,
保证训练正例比例 ≈ 30% (val_auc >= 0.8 的前提).

用法: python scripts/gen_risky_users.py --count 30
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

# 复用 gen_bank_data 的城市/代理池约定
PROXY_IPS = [f"45.155.204.{i}" for i in range(10, 30)]
PROXY_CITY = "黑龙江-哈尔滨"
# 多城代理池 (造 ip_geo_location 用): 登录集中哈尔滨建"常用城市", 交易走多城 → txn_city_match=1
MULTI_CITY_PROXY = [
    ("45.155.205.10", "美国", "California", "LA", "ProxyLayer", 1, 0, "北京-北京"),
    ("45.155.205.11", "美国", "California", "LA", "ProxyLayer", 1, 0, "北京-北京"),
    ("45.155.206.10", "美国", "Oregon", "PDX", "ProxyLayer", 1, 0, "上海-上海"),
    ("45.155.206.11", "美国", "Oregon", "PDX", "ProxyLayer", 1, 0, "上海-上海"),
    ("45.155.207.10", "美国", "Texas", "DAL", "ProxyLayer", 1, 0, "辽宁-沈阳"),
    ("45.155.207.11", "美国", "Texas", "DAL", "ProxyLayer", 1, 0, "辽宁-沈阳"),
]
BLACK_CARDS = ["card_black_0001", "card_black_b001"]  # init 打样黑卡 + 批量黑卡
CHANNELS = ["APP", "网银", "第三方"]
SURNAMES = ["赵", "孙", "李", "周", "吴", "郑", "王", "冯", "陈", "褚"]
GIVEN_NAMES = ["敏", "磊", "强", "艳", "军", "洋", "勇", "杰", "娟", "涛"]
OS_POOL = ["Android 10", "Android 11", "iOS 15", "HarmonyOS 3"]
BROWSER_POOL = ["Chrome", "UCMobile", "HuaweiBrowser"]
BANK_CODES = ["CMB", "PSBC", "SPDB", "CITIC"]


def _rand_time(days_span: int = 30) -> datetime:
    now = datetime.now()
    return (now - timedelta(days=random.uniform(0, days_span))).replace(microsecond=0)


def _rand_night() -> datetime:
    """夜间 0~4 点时刻 (近 10 天, 命中 R002/R003)."""
    now = datetime.now()
    d = now - timedelta(days=random.uniform(0, 10))
    return d.replace(hour=random.randint(0, 4), minute=random.randint(0, 59), microsecond=0)


def build_user(idx: int):
    """1 个 RISK 用户 + 配套卡/交易/贷款/登录/设备 数据"""
    uid = f"RISK{idx:03d}"
    credit = random.randint(350, 480)
    register_at = datetime.now() - timedelta(days=random.randint(7, 60))
    name = random.choice(SURNAMES) + random.choice(GIVEN_NAMES)

    # ---- 卡 (1~2 张, 含低额度信用卡) ----
    cards = [(f"card_{uid}_d1", uid, f"CARDHASH_{uid}_D1", random.choice(BANK_CODES), "借记卡", 0)]
    if random.random() < 0.5:
        cards.append((f"card_{uid}_c1", uid, f"CARDHASH_{uid}_C1",
                      random.choice(BANK_CODES), "信用卡", random.randint(2000, 15000)))

    # ---- 设备 (2~3 台, 含 1 台 <7 天新设备) ----
    devices = []
    for j in range(1, random.randint(2, 3) + 1):
        dev_id = f"dev_{uid}_{j}"
        first_seen = _rand_time(7) if j == 1 else _rand_time(20)
        devices.append((dev_id, uid, f"FPHASH_{dev_id}", first_seen, datetime.now(),
                        random.choice(OS_POOL), random.choice(BROWSER_POOL)))
    # 最后 1 台: 新设备 (1~6 天前 → login_device_new=1 / card_device_new=1)
    new_dev = f"dev_{uid}_new"
    devices.append((new_dev, uid, f"FPHASH_{new_dev}",
                    datetime.now() - timedelta(days=random.randint(1, 6)),
                    datetime.now(), random.choice(OS_POOL), random.choice(BROWSER_POOL)))

    # ---- 交易 (8~15 笔, 高风险模式) ----
    txns = []
    card_ids = [c[0] for c in cards]
    base_time = _rand_time()  # 1h 密集 burst 的基准时刻
    burst_done = False
    for k in range(1, random.randint(8, 15) + 1):
        from_card = random.choice(card_ids)
        # 黑卡概率 30% (命中 R030); 第 1 笔强制黑卡 → 保证每用户必命中 R030
        if k == 1 or random.random() < 0.3:
            to_card = random.choice(BLACK_CARDS)
        else:
            to_card = f"card_u{random.randint(1, 230):04d}_c1"
        # 大额: 2万~15万 (命中 R001/R015); 50% 概率 >5万 (命中 R001 异地大额)
        amount = round(random.uniform(20000, 150000), 2)
        if random.random() < 0.5:
            amount = round(random.uniform(50000, 150000), 2)
        # 夜间概率 50% (命中 R002); 第 2 笔强制夜间 → 保证每用户必有夜间交易
        txn_time = _rand_night() if (k == 2 or random.random() < 0.5) else _rand_time()
        # 设备: 70% 新设备 (命中 R005 信用卡场景)
        device_id = new_dev if random.random() < 0.7 else random.choice([d[0] for d in devices])
        # IP: 40% 哈尔滨代理 (常用城市) / 40% 多城代理 (异地 → R001) / 20% 普通 IP
        ip_roll = random.random()
        if ip_roll < 0.4:
            ip, geo = random.choice(PROXY_IPS), PROXY_CITY
        elif ip_roll < 0.8:
            _ip, *_g = random.choice(MULTI_CITY_PROXY)
            ip, geo = _ip, _g[-1]
        else:
            ip, geo = f"10.{random.randint(1, 6)}.{random.randint(1, 10)}.{random.randint(1, 254)}", "广东-深圳"
        txns.append((f"txn_{uid}_{k:03d}", from_card, to_card, amount,
                     random.choice(CHANNELS), device_id, ip, geo, txn_time))

    # 1h 密集 burst (命中 R002 凌晨密集 / R008 多卡归集): 每用户 1 组 3~5 笔
    if random.random() < 0.7:
        burst = random.randint(3, 5)
        for j in range(burst):
            b_from = random.choice(card_ids)
            b_to = random.choice(BLACK_CARDS) if random.random() < 0.3 else f"card_u{random.randint(1, 230):04d}_c1"
            b_time = base_time + timedelta(minutes=j * random.randint(5, 15))
            b_time = b_time.replace(hour=random.randint(0, 4), minute=random.randint(0, 59))
            txns.append((f"txn_{uid}_b{j:03d}", b_from, b_to,
                         round(random.uniform(1000, 30000), 2),
                         random.choice(CHANNELS), new_dev,
                         random.choice(PROXY_IPS), PROXY_CITY, b_time))
        burst_done = True

    # ---- 贷款 (2~4 笔: 高负债大额 → R010; 30 天多笔 → R012) ----
    loans = []
    for k in range(1, random.randint(2, 4) + 1):
        amount = round(random.uniform(100000, 500000), 2)
        income = round(random.uniform(3000, 8000), 2)
        debt = round(random.uniform(0.60, 0.90), 4)
        loans.append((f"loan_{uid}_{k:02d}", uid, amount, random.randint(12, 36),
                      random.choice(["周转", "投资"]), income, debt, _rand_time()))

    # ---- 登录 (5~15 次, 40% 失败 → R003; 集中在近 10 天 → user_failed_login_7d) ----
    logins = []
    login_total = random.randint(5, 15)
    for k in range(1, login_total + 1):
        device_id = new_dev if random.random() < 0.6 else random.choice([d[0] for d in devices])
        ip, geo = random.choice(PROXY_IPS), PROXY_CITY
        # 40% 失败; 最后 1 次强制失败 → 保证每用户必有失败登录 (命中 R003)
        success = 0 if (k == login_total or random.random() < 0.4) else 1
        login_at = _rand_night() if random.random() < 0.4 else _rand_time(10)
        logins.append((f"login_{uid}_{k:03d}", uid, device_id, ip, geo, success, login_at))

    return uid, name, credit, register_at, cards, devices, txns, loans, logins


def main():
    parser = argparse.ArgumentParser(description="银行风控系统 - RISK 高风险用户生成")
    parser.add_argument("--count", type=int, default=30, help="高风险用户数 (默认 30)")
    args = parser.parse_args()

    conn = pymysql.connect(
        host=settings.DB_HOST, port=settings.DB_PORT,
        user=settings.DB_USER, password=settings.DB_PASSWORD,
        database=settings.DB_NAME, charset="utf8mb4",
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            # 已存在的 RISK 用户数 (避免与 init 打样重复)
            cur.execute("SELECT COUNT(*) FROM user_info WHERE user_id LIKE 'RISK%'")
            existing = cur.fetchone()[0]
            print(f"已存在 {existing} 个 RISK 用户, 目标 {args.count} 个 (补足差额)")

            # 用户表: 一次性把 30 个全查出来, 判断哪些已存在
            cur.execute("SELECT user_id FROM user_info WHERE user_id LIKE 'RISK%'")
            exist_ids = {r[0] for r in cur.fetchall()}
            need = max(0, args.count - len(exist_ids))
            if need <= 0:
                print(f"已有 {len(exist_ids)} 个 RISK 用户 >= 目标 {args.count}, 跳过")
                return
            # 用 1~999 编号, 跳过已占用的
            used = {int(x.replace("RISK", "")) for x in exist_ids if x.replace("RISK", "").isdigit()}
            new_idx = [i for i in range(1, 1000) if i not in used][:need]

            users, cards, devices, txns, loans, logins = [], [], [], [], [], []
            for idx in new_idx:
                uid, name, credit, register_at, cds, devs, tx, lo, lg = build_user(idx)
                users.append((uid, name, f"HASH_{uid}", credit, register_at, 1))
                cards.extend(cds)
                devices.extend(devs)
                txns.extend(tx)
                loans.extend(lo)
                logins.extend(lg)
            print(f"本次生成 {len(users)} 个 RISK 用户, 配套卡 {len(cards)} / 交易 {len(txns)} / "
                  f"贷款 {len(loans)} / 登录 {len(logins)} / 设备 {len(devices)}")

            def _exec(sql, rows, batch=500):
                for i in range(0, len(rows), batch):
                    cur.executemany(sql, rows[i:i + batch])

            # 多城代理 IP (供交易异地 → txn_city_match=1)
            cur.executemany(
                "INSERT IGNORE INTO ip_geo_location (ip, country, province, city, isp, is_proxy, is_tor) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                [(_ip, country, province, city, isp, is_proxy, is_tor)
                 for _ip, country, province, city, isp, is_proxy, is_tor, _geo in MULTI_CITY_PROXY],
            )
            print(f"  IP 地理位置: 补充 {len(MULTI_CITY_PROXY)} 个多城代理 IP")

            _exec("INSERT INTO user_info (user_id, name, id_card_hash, credit_score, register_at, kyc_level) "
                  "VALUES (%s,%s,%s,%s,%s,%s)", users)
            _exec("INSERT INTO bank_card (card_id, user_id, card_no_hash, bank_code, card_type, credit_limit) "
                  "VALUES (%s,%s,%s,%s,%s,%s)", cards)
            _exec("INSERT INTO device_fingerprint (device_id, user_id, fingerprint_hash, first_seen, last_seen, os, browser) "
                  "VALUES (%s,%s,%s,%s,%s,%s,%s)", devices)
            _exec("INSERT INTO transaction (txn_id, from_card, to_card, amount, channel, device_id, ip, geo, txn_time) "
                  "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", txns)
            _exec("INSERT INTO loan_application (loan_id, user_id, amount, term_months, purpose, monthly_income, debt_ratio, apply_time) "
                  "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", loans)
            _exec("INSERT INTO login_log (login_id, user_id, device_id, ip, geo, success, login_at) "
                  "VALUES (%s,%s,%s,%s,%s,%s,%s)", logins)

        conn.commit()
        print(f"\n完成! 新增 {len(users)} 个 RISK 高风险用户 (总计 {len(exist_ids) + len(users)}).")
        print("下一步: python scripts/gen_risk_data.py --days 30 --per-day 100 --balance-pos --target-pos-ratio 0.30")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
