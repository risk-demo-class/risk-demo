"""
银行风控系统 - 测试数据生成脚本 (异步)
================================
生成覆盖四大场景的测试数据:
  - 用户 (user_info):              50 人 (含正常/中风险/高风险画像)
  - 银行卡 (bank_card):            ~120 张 (储蓄卡+信用卡)
  - 设备指纹 (device_fingerprint):  30 台 (含模拟器/root设备)
  - IP 地理位置 (ip_geo_location):  50 条 (含代理/Tor/VPN)
  - 登录日志 (login_log):          ~200 条 (含成功/失败/异地)
  - 交易 (transaction):            ~300 笔 (含小额试探/大额/归集/凌晨)
  - 贷款申请 (loan_application):   ~25 笔 (含多头/突击/团伙)
  - 黑名单 (blacklist_extra):      ~25 条 (含涉诈卡/失信人/代理IP)
  - 用户画像 (user_profile):        50 条
  - 风险事件 (risk_event):         ~80 条 (规则触发记录)
  - 设备用户关联 (device_user_rel): ~60 条

风险分层:
  - 70% 正常用户
  - 20% 中风险 (异地登录/高转账频率)
  - 10% 高风险 (涉诈/套现/团伙)

依赖: 先跑 init_db.py 建表, 再跑本脚本灌数据
运行: python gen_test_data.py          # 默认配置
      python gen_test_data.py --users 100  # 100 用户
"""

import argparse
import asyncio
import hashlib
import os
import random
import sys
from datetime import datetime, timedelta

import aiomysql

# 项目根目录 (MY_RISK)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 默认连接配置
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 3306
DEFAULT_USER = "root"
DEFAULT_PASSWORD = "1234"
DEFAULT_DB = "bank_risk"

# ============================================================
# 常量: 枚举映射 & 数据池
# ============================================================

# 银行代码
BANK_CODES = ["ICBC", "CCB", "ABC", "BOC", "CMB", "COMM", "CIB", "CITIC", "CEB", "SPDB", "PAB", "CMBC"]

# 中国省份 & 城市
CHINESE_CITIES = {
    "北京": "北京市", "上海": "上海市", "广东": "广州市", "浙江": "杭州市",
    "江苏": "南京市", "四川": "成都市", "湖北": "武汉市", "福建": "福州市",
    "山东": "济南市", "河南": "郑州市", "河北": "石家庄市", "湖南": "长沙市",
    "安徽": "合肥市", "江西": "南昌市", "陕西": "西安市", "辽宁": "沈阳市",
    "吉林": "长春市", "黑龙江": "哈尔滨市", "广西": "南宁市", "云南": "昆明市",
}
PROVINCES = list(CHINESE_CITIES.keys())

# IP 池 (模拟各类 IP)
NORMAL_IPS = [
    "202.96.128.86", "114.114.114.114", "223.5.5.5", "119.29.29.29",
    "180.76.76.76", "123.125.81.6", "111.13.101.208", "117.136.12.34",
    "183.232.231.172", "106.11.47.19", "112.80.248.75", "58.240.115.35",
]
PROXY_IPS = ["103.35.168.38", "45.33.32.156", "198.58.118.17", "89.187.162.5"]
TOR_IPS = ["185.220.101.34", "23.129.64.200", "199.249.230.89"]
VPN_IPS = ["104.28.7.19", "172.64.11.22", "141.101.119.33"]

# OS 池
OS_TYPES = ["iOS 17.4", "iOS 16.8", "Android 14", "Android 13", "Android 12", "Windows 11", "macOS 14"]
BROWSERS = ["Safari", "Chrome", "Edge", "Firefox", "UC Browser"]

# 交易渠道
CHANNELS = ["APP", "网银", "ATM", "POS", "第三方"]

# 贷款用途
LOAN_PURPOSES = ["消费", "经营", "购车", "装修"]

# 姓名池 (常见中文姓名)
SURNAMES = ["张", "李", "王", "陈", "刘", "黄", "赵", "周", "吴", "徐", "孙", "马", "朱", "胡", "林", "何", "郭", "罗", "郑", "梁"]
GIVEN_NAMES = ["伟", "芳", "敏", "静", "丽", "强", "磊", "洋", "勇", "艳", "杰", "娟", "涛", "明", "超", "秀英", "华", "慧", "鑫", "文"]

# ISP 运营商
ISPS = ["中国电信", "中国联通", "中国移动", "中国广电", "鹏博士"]

# ============================================================
# 工具函数
# ============================================================
def sha256_hash(value: str) -> str:
    """SHA-256 哈希"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def random_name() -> str:
    """随机生成中文姓名"""
    return random.choice(SURNAMES) + random.choice(GIVEN_NAMES) + (random.choice(GIVEN_NAMES) if random.random() < 0.5 else "")


def random_phone() -> str:
    """随机生成手机号"""
    prefixes = ["138", "139", "150", "151", "152", "158", "159", "186", "187", "188", "135", "136", "137", "176", "177", "189"]
    return random.choice(prefixes) + "".join([str(random.randint(0, 9)) for _ in range(8)])


def random_id_card() -> str:
    """随机生成 18 位身份证号 (格式正确, 非真实)"""
    province_code = random.choice(["11", "32", "44", "51", "33", "42", "37", "21", "41", "50"])
    city_code = f"{random.randint(1, 28):02d}"
    district_code = f"{random.randint(1, 20):02d}"
    year = random.randint(1970, 2005)
    month = f"{random.randint(1, 12):02d}"
    day = f"{random.randint(1, 28):02d}"
    seq = f"{random.randint(0, 999):03d}"
    body = f"{province_code}{city_code}{district_code}{year}{month}{day}{seq}"
    # 简化校验码
    return body + str(random.randint(0, 9))


def random_card_no() -> str:
    """随机生成银行卡号 (16-19位, 格式正确, 非真实)"""
    prefixes = ["6222", "6217", "6228", "6259", "6225", "6212", "6210", "6221", "6230", "6282"]
    prefix = random.choice(prefixes)
    length = random.choice([16, 18, 19])
    return prefix + "".join([str(random.randint(0, 9)) for _ in range(length - len(prefix))])


def random_datetime(start_days_ago: int = 90, end_days_ago: int = 0) -> datetime:
    """过去 N 天内随机时间"""
    days_ago = random.randint(end_days_ago, start_days_ago)
    hours_ago = random.randint(0, 23)
    minutes_ago = random.randint(0, 59)
    return datetime.now() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)


async def get_connection(host, port, user, password, db=None):
    """获取 MySQL 异步连接"""
    return await aiomysql.connect(
        host=host, port=port, user=user, password=password,
        db=db, charset="utf8mb4", autocommit=True,
    )


async def batch_insert(conn, table: str, columns: list[str], rows: list[tuple], batch_size: int = 200):
    """批量插入 (使用 executemany)"""
    if not rows:
        return 0
    placeholders = ", ".join(["%s"] * len(columns))
    col_names = ", ".join([f"`{c}`" for c in columns])
    sql = f"INSERT IGNORE INTO `{table}` ({col_names}) VALUES ({placeholders})"

    async with conn.cursor() as cur:
        total = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            await cur.executemany(sql, batch)
            total += len(batch)
        return total


# ============================================================
# 主函数
# ============================================================
async def gen_test_data(
    n_user: int = 50,
    min_cards_per_user: int = 1,
    max_cards_per_user: int = 4,
    batch_size: int = 200,
):
    print("=" * 60)
    print(f"银行风控系统 - 测试数据生成")
    print(f"目标: 覆盖登录/转账/贷款/信用卡四大场景")
    print(f"用户数: {n_user}, 每用户 {min_cards_per_user}-{max_cards_per_user} 张卡")
    print("=" * 60)

    # ---------------------------
    # 1. 灌 IP 地理位置 (50 条)
    # ---------------------------
    print("\n[1/11] 灌 IP 地理位置 (~50 条)...")
    all_ips = []
    ip_rows = []

    for ip in NORMAL_IPS:
        prov = random.choice(PROVINCES)
        ip_rows.append((ip, "中国", prov, CHINESE_CITIES[prov],
                        random.choice(ISPS), 0, 0, 0, 1, datetime.now()))
        all_ips.append(ip)
    for ip in PROXY_IPS:
        ip_rows.append((ip, random.choice(["美国", "日本", "新加坡"]),
                        None, None, "海外运营商", 1, 0, 0, 0, datetime.now()))
        all_ips.append(ip)
    for ip in TOR_IPS:
        ip_rows.append((ip, random.choice(["荷兰", "德国", "瑞典"]),
                        None, None, "Tor网络", 0, 1, 0, 0, datetime.now()))
        all_ips.append(ip)
    for ip in VPN_IPS:
        ip_rows.append((ip, random.choice(["美国", "英国", "加拿大"]),
                        None, None, "VPN服务商", 0, 0, 1, 0, datetime.now()))
        all_ips.append(ip)

    # 补充一些随机 IP
    for _ in range(30):
        ip = f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
        prov = random.choice(PROVINCES)
        is_proxy_val = 1 if random.random() < 0.05 else 0
        ip_rows.append((ip, "中国", prov, CHINESE_CITIES[prov],
                        random.choice(ISPS), is_proxy_val, 0, 0, 1, datetime.now()))
        all_ips.append(ip)

    conn = await get_connection(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DB)
    try:
        await batch_insert(conn, "ip_geo_location",
                           ["ip", "country", "province", "city", "isp", "is_proxy", "is_tor", "is_vpn", "is_mobile", "updated_at"],
                           ip_rows, batch_size)
        print(f"  -> {len(ip_rows)} 条 IP 记录")
    finally:
        await conn.ensure_closed()

    # ---------------------------
    # 2. 灌设备指纹 (30 台)
    # ---------------------------
    print("\n[2/11] 灌设备指纹 (30 台)...")
    device_ids = []
    device_rows = []

    for i in range(1, 31):
        device_rows.append((
            i,  # device_id (手动指定, 方便后续关联)
            sha256_hash(f"device_{i}_{random.randint(10000, 99999)}"),
            random.choice(OS_TYPES),
            random.choice(BROWSERS),
            1 if i <= 2 else 0,  # 前 2 个是模拟器
            1 if i == 3 else 0,  # 第 3 个是 root
            3 if i <= 2 else (2 if i <= 5 else 1),  # 状态: 1=正常, 2=高风险, 3=黑名单
            random_datetime(365, 30),
            random_datetime(30, 0),
        ))
        device_ids.append(i)

    conn = await get_connection(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DB)
    try:
        await batch_insert(conn, "device_fingerprint",
                           ["device_id", "fingerprint_hash", "os", "browser", "is_emulator", "is_root", "status", "first_seen", "last_seen"],
                           device_rows, batch_size)
        print(f"  -> {len(device_rows)} 台设备 (含 {sum(1 for d in device_rows if d[4])} 模拟器, {sum(1 for d in device_rows if d[5])} root)")
    finally:
        await conn.ensure_closed()

    # ---------------------------
    # 3. 灌用户 (50 人) + 风险分层
    # ---------------------------
    print(f"\n[3/11] 灌用户 ({n_user} 人)...")
    user_ids = []
    user_rows = []
    user_risk = {}  # user_id -> "normal" | "medium" | "high"

    for i in range(1, n_user + 1):
        user_id = i
        risk_r = random.random()
        if risk_r < 0.10:
            risk = "high"
        elif risk_r < 0.30:
            risk = "medium"
        else:
            risk = "normal"

        user_risk[user_id] = risk

        # 风险标签
        if risk == "high":
            risk_tag = random.choice(["涉诈", "失信", "涉案", "涉诈,失信"])
        elif risk == "medium":
            risk_tag = random.choice([None, "异常登录", "高负债", None, "频繁交易"])
        else:
            risk_tag = None

        # 状态: 正常居多
        if risk == "high":
            status = random.choice([1, 2, 2, 3])  # 偏冻结/止付
        else:
            status = 1  # 正常

        # KYC 等级: 高风险用户偏 L1/L2, 正常偏 L3/L4
        if risk == "high":
            kyc = random.choice([1, 1, 2])
        else:
            kyc = random.choice([2, 3, 3, 4])

        # 信用分
        if risk == "high":
            credit = random.randint(300, 500)
        elif risk == "medium":
            credit = random.randint(500, 650)
        else:
            credit = random.randint(650, 850)

        phone = random_phone()
        id_card = random_id_card()

        user_rows.append((
            user_id, random_name(), sha256_hash(id_card), sha256_hash(phone),
            credit, kyc, risk_tag, status,
            random_datetime(730, 30),  # 注册时间: 过去 30-730 天
            datetime.now(),
        ))
        user_ids.append(user_id)

    conn = await get_connection(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DB)
    try:
        await batch_insert(conn, "user_info",
                           ["user_id", "name", "id_card_hash", "phone_hash", "credit_score",
                            "kyc_level", "risk_tag", "status", "register_at", "updated_at"],
                           user_rows, batch_size)
        print(f"  -> {len(user_rows)} 用户 (高风险 {sum(1 for v in user_risk.values() if v == 'high')}, "
              f"中风险 {sum(1 for v in user_risk.values() if v == 'medium')}, "
              f"正常 {sum(1 for v in user_risk.values() if v == 'normal')})")
    finally:
        await conn.ensure_closed()

    # ---------------------------
    # 4. 灌用户画像 (50 条)
    # ---------------------------
    print(f"\n[4/11] 灌用户画像 (50 条)...")
    profile_rows = []

    for user_id in user_ids:
        risk = user_risk[user_id]
        prov = random.choice(PROVINCES)
        common_city = CHINESE_CITIES[prov]

        if risk == "high":
            avg_amount = round(random.uniform(50000, 500000), 2)
            freq = round(random.uniform(5, 20), 2)
            active = random.choice(["22-6", "0-6", "全天"])
        elif risk == "medium":
            avg_amount = round(random.uniform(5000, 50000), 2)
            freq = round(random.uniform(1, 5), 2)
            active = random.choice(["9-18", "18-24", "全天"])
        else:
            avg_amount = round(random.uniform(100, 5000), 2)
            freq = round(random.uniform(0.1, 1), 2)
            active = random.choice(["9-18", "9-21", "8-20"])

        # 常用设备: 高风险用户更可能用多设备
        common_device = random.choice(device_ids) if random.random() < 0.8 else None

        profile_rows.append((
            user_id, common_city, common_device, avg_amount, freq,
            active, datetime.now(),
        ))

    conn = await get_connection(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DB)
    try:
        await batch_insert(conn, "user_profile",
                           ["user_id", "common_city", "common_device_id", "avg_txn_amount",
                            "txn_freq_day", "active_hours", "profile_at"],
                           profile_rows, batch_size)
        print(f"  -> {len(profile_rows)} 条画像")
    finally:
        await conn.ensure_closed()

    # ---------------------------
    # 5. 灌银行卡 (~120 张)
    # ---------------------------
    print(f"\n[5/11] 灌银行卡 (~{n_user * 2} 张，含储蓄卡+信用卡)...")
    card_rows = []
    user_cards: dict[int, list[int]] = {}  # user_id -> [card_id]
    card_id_counter = 1

    for user_id in user_ids:
        risk = user_risk[user_id]
        n_cards = random.randint(min_cards_per_user, max_cards_per_user)
        user_cards[user_id] = []

        for j in range(n_cards):
            # 第一张储蓄卡, 后续可能是信用卡
            if j == 0:
                card_type = 1  # 储蓄卡
                credit_limit = None
            elif j >= 2 and random.random() < 0.4:
                card_type = 2  # 信用卡
                credit_limit = round(random.uniform(10000, 300000), 2)
            else:
                card_type = 1
                credit_limit = None

            # 高风险用户可能卡片被冻结
            if risk == "high":
                status = random.choice([1, 1, 2, 3, 4])
            elif risk == "medium":
                status = random.choice([1, 1, 1, 2])
            else:
                status = 1

            single_limit = round(random.choice([10000, 20000, 50000, 100000, 200000, 500000]), 2)
            daily_limit = round(single_limit * random.choice([2, 3, 5, 10]), 2)

            card_rows.append((
                card_id_counter, user_id,
                sha256_hash(random_card_no()),
                random.choice(BANK_CODES),
                card_type, credit_limit,
                single_limit, daily_limit, status,
                random_datetime(730, 60), datetime.now(),
            ))
            user_cards[user_id].append(card_id_counter)
            card_id_counter += 1

    conn = await get_connection(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DB)
    try:
        await batch_insert(conn, "bank_card",
                           ["card_id", "user_id", "card_no_hash", "bank_code", "card_type",
                            "credit_limit", "single_limit", "daily_limit", "status", "open_at", "updated_at"],
                           card_rows, batch_size)
        credit_count = sum(1 for c in card_rows if c[4] == 2)
        print(f"  -> {len(card_rows)} 张卡 (储蓄卡 {len(card_rows) - credit_count}, 信用卡 {credit_count})")
    finally:
        await conn.ensure_closed()

    # ---------------------------
    # 6. 灌黑名单 (~25 条)
    # ---------------------------
    print("\n[6/11] 灌黑名单 (~25 条)...")
    blacklist_rows = []

    # 涉诈银行卡号 (从已生成的卡中挑一些高风险用户的卡)
    high_risk_users = [uid for uid, risk in user_risk.items() if risk == "high"]
    for uid in high_risk_users[:3]:
        for card_id in user_cards.get(uid, [])[:1]:
            # 找到对应的 card_no_hash
            card_hash = None
            for cr in card_rows:
                if cr[0] == card_id:
                    card_hash = cr[2]
                    break
            if card_hash:
                blacklist_rows.append((
                    3, card_hash, "公安涉诈名单命中",
                    "公安涉诈", 4, None, 1, datetime.now(), datetime.now(),
                ))

    # 涉诈 IP
    for ip in PROXY_IPS[:2] + TOR_IPS[:2]:
        blacklist_rows.append((
            2, ip, "代理/秒拨 IP",
            "内部", 3, None, 1, datetime.now(), datetime.now(),
        ))

    # 涉诈/失信身份证号
    for uid in high_risk_users[2:5]:
        for ur in user_rows:
            if ur[0] == uid:
                blacklist_rows.append((
                    4, ur[2], "法院失信被执行人",
                    "法院", 4, None, 1, datetime.now(), datetime.now(),
                ))
                break

    # 涉诈手机号
    for uid in high_risk_users[3:5]:
        for ur in user_rows:
            if ur[0] == uid:
                blacklist_rows.append((
                    5, ur[3], "涉诈手机号",
                    "公安涉诈", 4, None, 1, datetime.now(), datetime.now(),
                ))
                break

    # 涉诈设备
    blacklist_rows.append((1, sha256_hash(f"device_1_{random.randint(10000,99999)}"), "模拟器群控设备", "内部", 3, None, 1, datetime.now(), datetime.now()))
    blacklist_rows.append((1, sha256_hash(f"device_2_{random.randint(10000,99999)}"), "涉诈设备指纹", "公安涉诈", 4, None, 1, datetime.now(), datetime.now()))

    # 补充一些外部来源的
    for _ in range(10):
        bl_type = random.choice([3, 4, 5])
        if bl_type == 3:
            value = sha256_hash(random_card_no())
        elif bl_type == 4:
            value = sha256_hash(random_id_card())
        else:
            value = sha256_hash(random_phone())
        source = random.choice(["公安涉诈", "法院", "同业", "外部"])
        blacklist_rows.append((
            bl_type, value, f"{source}推送风险名单",
            source, random.choice([3, 4]), None, 1, datetime.now(), datetime.now(),
        ))

    conn = await get_connection(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DB)
    try:
        await batch_insert(conn, "blacklist_extra",
                           ["type", "value", "reason", "source", "risk_level", "expire_at", "status", "created_at", "updated_at"],
                           blacklist_rows, batch_size)
        print(f"  -> {len(blacklist_rows)} 条黑名单 (涉诈卡/IP/身份证/手机号/设备)")
    finally:
        await conn.ensure_closed()

    # ---------------------------
    # 7. 灌登录日志 (~200 条)
    # ---------------------------
    print("\n[7/11] 灌登录日志 (~200 条)...")
    login_rows = []

    for user_id in user_ids:
        risk = user_risk[user_id]
        # 每人 2-8 次登录
        n_logins = random.randint(2, 8)

        for _ in range(n_logins):
            device_id = random.choice(device_ids)
            # 高风险/中风险用户更可能用代理 IP
            if risk == "high":
                ip = random.choice(all_ips[-20:])  # 后面的 IP 含代理/Tor
            elif risk == "medium":
                ip = random.choice(all_ips[:40] + PROXY_IPS[:1])
            else:
                ip = random.choice(all_ips[:30])

            prov = random.choice(PROVINCES)
            geo = f"{prov}-{CHINESE_CITIES[prov]}"

            # 成功/失败: 高风险用户更容易登录失败 (风控拦截)
            if risk == "high":
                success = random.choice([0, 0, 0, 1])
                fail_reason = random.choice(["风控拦截", "密码错误", "账户冻结"]) if success == 0 else None
            elif risk == "medium":
                success = random.choice([0, 1, 1])
                fail_reason = random.choice(["密码错误", "风控拦截"]) if success == 0 else None
            else:
                success = 1
                fail_reason = None

            login_rows.append((
                user_id, device_id, ip, geo,
                success, fail_reason,
                random_datetime(60, 0),
            ))

    conn = await get_connection(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DB)
    try:
        await batch_insert(conn, "login_log",
                           ["user_id", "device_id", "ip", "geo", "success", "fail_reason", "login_at"],
                           login_rows, batch_size)
        fail_count = sum(1 for lr in login_rows if lr[4] == 0)
        print(f"  -> {len(login_rows)} 条登录日志 (含 {fail_count} 条失败)")
    finally:
        await conn.ensure_closed()

    # ---------------------------
    # 8. 灌交易 (~300 笔)
    # ---------------------------
    print("\n[8/11] 灌交易 (~300 笔)...")
    txn_rows = []

    txn_id_counter = 1
    for user_id in user_ids:
        risk = user_risk[user_id]
        user_card_list = user_cards.get(user_id, [])
        if not user_card_list:
            continue

        # 每人 2-15 笔交易
        n_txns = random.randint(2, 8) if risk == "normal" else random.randint(5, 15)

        for _ in range(n_txns):
            from_card = random.choice(user_card_list)
            device_id = random.choice(device_ids)
            ip = random.choice(all_ips[:40] + PROXY_IPS if risk == "high" else all_ips[:35])
            prov = random.choice(PROVINCES)
            geo = f"{prov}-{CHINESE_CITIES[prov]}"

            # 交易金额: 高风险用户大额或小额试探
            if risk == "high":
                if random.random() < 0.3:
                    # 小额试探
                    amount = round(random.uniform(1, 100), 2)
                else:
                    # 大额
                    amount = round(random.uniform(30000, 500000), 2)
                txn_type = 1  # 转账为主
                status = 4 if random.random() < 0.6 else 1  # 高风险用户常被拒绝
                risk_score = round(random.uniform(70, 100), 2)
            elif risk == "medium":
                amount = round(random.uniform(100, 50000), 2)
                txn_type = random.choice([1, 1, 1, 2, 5])
                status = random.choice([1, 1, 1, 3, 4])
                risk_score = round(random.uniform(30, 70), 2)
            else:
                amount = round(random.uniform(10, 10000), 2)
                txn_type = random.choice([1, 2, 3, 4, 5])
                status = 1
                risk_score = round(random.uniform(0, 30), 2)

            # 对手方信息
            to_other_user = random.choice(user_ids) if random.random() < 0.4 else None
            if to_other_user and to_other_user != user_id and user_cards.get(to_other_user):
                to_card = random.choice(user_cards[to_other_user])
                to_card_hash = None
                to_name_hash = None
                to_bank = None
            else:
                to_card = None
                to_card_hash = sha256_hash(random_card_no())
                to_name_hash = sha256_hash(random_name())
                to_bank = random.choice(BANK_CODES)

            txn_rows.append((
                txn_id_counter, from_card, to_card, to_card_hash, to_name_hash, to_bank,
                amount, txn_type, random.choice(CHANNELS),
                device_id, ip, geo, risk_score, status,
                random_datetime(60, 0),
            ))
            txn_id_counter += 1

    conn = await get_connection(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DB)
    try:
        await batch_insert(conn, "transaction",
                           ["txn_id", "from_card_id", "to_card_id", "to_card_no_hash",
                            "to_account_name_hash", "to_bank_code", "amount", "txn_type",
                            "channel", "device_id", "ip", "geo", "risk_score", "status", "created_at"],
                           txn_rows, batch_size)
        reject_count = sum(1 for t in txn_rows if t[13] == 4)
        print(f"  -> {len(txn_rows)} 笔交易 (含 {reject_count} 笔拒绝)")
    finally:
        await conn.ensure_closed()

    # ---------------------------
    # 9. 灌贷款申请 (~25 笔)
    # ---------------------------
    print("\n[9/11] 灌贷款申请 (~25 笔)...")
    loan_rows = []

    for user_id in user_ids:
        risk = user_risk[user_id]
        # 高风险用户更多贷款, 正常用户较少
        if risk == "high":
            n_loans = random.randint(1, 3)
        elif risk == "medium":
            n_loans = random.randint(0, 2)
        else:
            n_loans = random.randint(0, 1)

        for _ in range(n_loans):
            amount = round(random.uniform(10000, 500000), 2)
            term = random.choice([6, 12, 24, 36, 48, 60])
            purpose = random.choice(LOAN_PURPOSES)
            monthly_income = round(random.uniform(5000, 50000), 2)

            if risk == "high":
                debt_ratio = round(random.uniform(0.60, 0.95), 2)
                credit_q_1m = random.randint(5, 12)
                credit_q_3m = random.randint(10, 25)
                credit_q_6m = random.randint(20, 50)
                device_id = random.choice(device_ids[:5])  # 偏高风险设备
                ip = random.choice(PROXY_IPS + TOR_IPS)
                loan_status = random.choice([3, 4, 5, 7])
            elif risk == "medium":
                debt_ratio = round(random.uniform(0.30, 0.60), 2)
                credit_q_1m = random.randint(2, 6)
                credit_q_3m = random.randint(5, 12)
                credit_q_6m = random.randint(10, 20)
                device_id = random.choice(device_ids)
                ip = random.choice(all_ips[:40])
                loan_status = random.choice([1, 1, 2, 5, 6])
            else:
                debt_ratio = round(random.uniform(0.05, 0.30), 2)
                credit_q_1m = random.randint(0, 2)
                credit_q_3m = random.randint(0, 5)
                credit_q_6m = random.randint(0, 8)
                device_id = random.choice(device_ids[10:])
                ip = random.choice(all_ips[:30])
                loan_status = random.choice([1, 2, 5, 6])

            prov = random.choice(PROVINCES)
            geo = f"{prov}-{CHINESE_CITIES[prov]}"

            loan_rows.append((
                user_id, amount, term, purpose, monthly_income, debt_ratio,
                credit_q_1m, credit_q_3m, credit_q_6m,
                random.choice(CHANNELS[:3]), device_id, ip, geo,
                loan_status, random_datetime(180, 0), datetime.now(),
            ))

    conn = await get_connection(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DB)
    try:
        await batch_insert(conn, "loan_application",
                           ["user_id", "amount", "term_months", "purpose", "monthly_income",
                            "debt_ratio", "credit_query_1m", "credit_query_3m", "credit_query_6m",
                            "channel", "device_id", "ip", "geo", "status", "applied_at", "updated_at"],
                           loan_rows, batch_size)
        overdue_count = sum(1 for l in loan_rows if l[13] == 7)
        print(f"  -> {len(loan_rows)} 笔贷款申请 (含 {overdue_count} 笔逾期)")
    finally:
        await conn.ensure_closed()

    # ---------------------------
    # 10. 灌设备用户关联 (~60 条)
    # ---------------------------
    print("\n[10/11] 灌设备用户关联 (~60 条)...")
    rel_rows = set()

    # 从登录日志生成关联
    for lr in login_rows:
        user_id, device_id = lr[0], lr[1]
        if device_id:
            rel_rows.add((device_id, user_id, 1))

    # 从交易生成关联
    for txn in txn_rows:
        device_id = txn[9]
        # 找到 from_card 对应的 user_id
        from_card = txn[1]
        for uid, cards in user_cards.items():
            if from_card in cards:
                if device_id:
                    rel_rows.add((device_id, uid, 2))
                break

    # 给高风险设备人为增加用户数 (模拟团伙/设备共用)
    for device_id in device_ids[:3]:  # 前 3 个设备
        for uid in random.sample(user_ids, min(6, len(user_ids))):  # 关联 5-6 个用户
            rel_rows.add((device_id, uid, random.choice([1, 3])))

    rel_list = []
    for device_id, user_id, rel_type in rel_rows:
        rel_list.append((
            device_id, user_id, rel_type,
            random_datetime(365, 60),
            random_datetime(60, 0),
        ))

    conn = await get_connection(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DB)
    try:
        await batch_insert(conn, "device_user_rel",
                           ["device_id", "user_id", "rel_type", "first_seen", "last_seen"],
                           rel_list, batch_size)
        print(f"  -> {len(rel_list)} 条关联")
    finally:
        await conn.ensure_closed()

    # ---------------------------
    # 11. 灌风险事件 (~80 条)
    # ---------------------------
    print("\n[11/11] 灌风险事件 (~80 条)...")
    event_rows = []

    # 手动构造一些典型的触发事件
    event_scenarios = [
        # (event_type, user_id, device_id, ip, amount, rule_ids, risk_score, decision, action, status)
        ("LOGIN", None, device_ids[0], PROXY_IPS[0], None, "R025", 45.00, "CHALLENGE", "TAG", 2),
        ("LOGIN", None, device_ids[1], TOR_IPS[0], None, "R025,R018", 65.00, "REJECT", "FREEZE", 2),
        ("LOGIN", None, device_ids[4], all_ips[10], None, None, 10.00, "PASS", None, 2),
        ("TRANSFER", None, None, all_ips[5], 80000.00, "R001,R030", 95.00, "REJECT", "STOP_PAYMENT", 2),
        ("TRANSFER", None, None, all_ips[8], 50000.00, "R005", 72.00, "MANUAL", "TAG", 1),
        ("TRANSFER", None, None, all_ips[3], 50.00, "R010", 55.00, "MANUAL", "TAG", 1),
        ("TRANSFER", None, None, all_ips[6], 200000.00, "R001,R008", 98.00, "REJECT", "FREEZE", 2),
        ("LOAN_APPLY", None, device_ids[1], PROXY_IPS[0], 100000.00, "R012,R033", 78.00, "MANUAL", "TAG", 1),
        ("LOAN_APPLY", None, device_ids[2], TOR_IPS[0], 200000.00, "R012,R020,R033,R035", 92.00, "REJECT", "FREEZE", 2),
        ("LOAN_APPLY", None, device_ids[0], all_ips[12], 50000.00, "R020", 62.00, "MANUAL", "TAG", 1),
        ("DISBURSE", None, None, all_ips[7], 100000.00, "R015", 88.00, "REJECT", "FREEZE", 2),
        ("CARD_APPLY", None, device_ids[0], PROXY_IPS[1], None, "R033", 68.00, "MANUAL", "TAG", 1),
        ("OVERDUE", None, None, None, None, None, 75.00, "REJECT", "FREEZE", 2),
    ]

    # 用真实的高风险/中风险用户填进去
    high_users = [uid for uid, r in user_risk.items() if r == "high"]
    medium_users = [uid for uid, r in user_risk.items() if r == "medium"]
    normal_users = [uid for uid, r in user_risk.items() if r == "normal"]

    scenario_idx = 0
    for event_type, _, dev_id, ip, amount, rule_ids, score, decision, action, status in event_scenarios:
        if scenario_idx < len(high_users):
            uid = high_users[scenario_idx % len(high_users)]
        elif scenario_idx < len(high_users) + len(medium_users):
            uid = medium_users[(scenario_idx - len(high_users)) % len(medium_users)]
        else:
            uid = random.choice(normal_users)

        # 找到用户的卡
        cards = user_cards.get(uid, [])
        card_id = cards[0] if cards else None

        event_rows.append((
            event_type, uid, card_id, dev_id, ip, amount,
            rule_ids, score, decision, action,
            status, "admin" if status == 2 else None,
            datetime.now() if status == 2 else None,
            "系统自动处理" if status == 2 else None,
            random_datetime(60, 0),
        ))
        scenario_idx += 1

    # 自动生成一些随机风险事件
    for _ in range(67):  # 总 ~80 条
        uid = random.choice(user_ids)
        risk = user_risk[uid]

        if risk == "high":
            event_type = random.choice(["LOGIN", "TRANSFER", "LOAN_APPLY", "OVERDUE"])
            score = round(random.uniform(70, 100), 2)
            decision = random.choice(["MANUAL", "REJECT", "CHALLENGE"])
            action = random.choice(["TAG", "FREEZE", "STOP_PAYMENT"])
            status = random.choice([1, 1, 2])
        elif risk == "medium":
            event_type = random.choice(["LOGIN", "TRANSFER", "LOAN_APPLY", "PAYMENT"])
            score = round(random.uniform(30, 70), 2)
            decision = random.choice(["PASS", "CHALLENGE", "MANUAL"])
            action = random.choice([None, "TAG", "LIMIT"])
            status = random.choice([1, 2])
        else:
            event_type = random.choice(["LOGIN", "TRANSFER", "PAYMENT", "WITHDRAW", "REPAY"])
            score = round(random.uniform(0, 30), 2)
            decision = "PASS"
            action = None
            status = 2

        cards = user_cards.get(uid, [])
        card_id = cards[0] if cards else None
        dev_id = random.choice(device_ids)
        ip = random.choice(all_ips[:35] if risk != "high" else all_ips[-20:])
        amount = round(random.uniform(100, 100000), 2) if event_type in ("TRANSFER", "LOAN_APPLY") else None

        event_rows.append((
            event_type, uid, card_id, dev_id, ip, amount,
            None, score, decision, action,
            status, "admin" if status == 2 else None,
            datetime.now() if status == 2 else None,
            "系统自动" if status == 2 else None,
            random_datetime(60, 0),
        ))

    conn = await get_connection(DEFAULT_HOST, DEFAULT_PORT, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_DB)
    try:
        await batch_insert(conn, "risk_event",
                           ["event_type", "user_id", "card_id", "device_id", "ip", "amount",
                            "rule_ids", "risk_score", "decision", "action",
                            "status", "handler", "handled_at", "remark", "created_at"],
                           event_rows, batch_size)
        manual_count = sum(1 for e in event_rows if e[8] == "MANUAL")
        reject_count = sum(1 for e in event_rows if e[8] == "REJECT")
        print(f"  -> {len(event_rows)} 条风险事件 (MANUAL {manual_count}, REJECT {reject_count})")
    finally:
        await conn.ensure_closed()

    # ---------------------------
    # 汇总
    # ---------------------------
    total = (
        len(ip_rows) + len(device_rows) + len(user_rows) + len(profile_rows) +
        len(card_rows) + len(blacklist_rows) + len(login_rows) + len(txn_rows) +
        len(loan_rows) + len(rel_list) + len(event_rows)
    )
    print(f"\n{'=' * 60}")
    print(f"测试数据生成完成! 总计 {total} 条数据")
    print(f"  - IP 地理位置:      {len(ip_rows)}")
    print(f"  - 设备指纹:         {len(device_rows)}")
    print(f"  - 用户:             {len(user_rows)}")
    print(f"  - 用户画像:         {len(profile_rows)}")
    print(f"  - 银行卡:           {len(card_rows)}")
    print(f"  - 黑名单:           {len(blacklist_rows)}")
    print(f"  - 登录日志:         {len(login_rows)}")
    print(f"  - 交易:             {len(txn_rows)}")
    print(f"  - 贷款申请:         {len(loan_rows)}")
    print(f"  - 设备用户关联:     {len(rel_list)}")
    print(f"  - 风险事件:         {len(event_rows)}")
    print(f"\n覆盖场景:")
    print(f"  - 登录: 异地登录 / 代理IP / 设备共用 (R003, R018, R025)")
    print(f"  - 转账: 大额异地 / 凌晨密集 / 多卡归集 / 试探 / 涉诈收款 (R001, R002, R005, R008, R010, R028, R030)")
    print(f"  - 贷款: 多头查询 / 突击申请 / 团伙 / 收入不符 / 放款即转 (R012, R015, R020, R033, R035)")
    print(f"  - 信用卡: 养卡套现 (R022)")
    print(f"\n下一步: python init_db.py --reset --yes 然后 python gen_test_data.py")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="银行风控系统 - 测试数据生成 (一次性, 跑完即结束)"
    )
    parser.add_argument("--users", type=int, default=50, help="用户数 (默认 50)")
    parser.add_argument("--min-cards", type=int, default=1, help="每用户最少卡数 (默认 1)")
    parser.add_argument("--max-cards", type=int, default=4, help="每用户最多卡数 (默认 4)")
    parser.add_argument("--batch", type=int, default=200, help="批量 insert 批次大小 (默认 200)")
    args = parser.parse_args()

    asyncio.run(gen_test_data(
        n_user=args.users,
        min_cards_per_user=args.min_cards,
        max_cards_per_user=args.max_cards,
        batch_size=args.batch,
    ))
