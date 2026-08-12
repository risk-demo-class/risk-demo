"""
构造极端数据触发 8 条规则, 然后调风控接口验证.
"""
import httpx
import pymysql
from datetime import datetime, timedelta

BASE = "http://localhost:8002"
conn = pymysql.connect(host="localhost", port=3306, user="root",
                       password="123321", database="bank_risk", charset="utf8mb4", autocommit=True)
cur = conn.cursor()

now = datetime.now()
last_hour = now - timedelta(hours=1)
yesterday = now - timedelta(days=2)

print("=" * 60)
print("构造极端数据 (8 条规则触发场景)")
print("=" * 60)

# ============================================================
# R001 异地大额转账: U10001 常用地=湖北/武汉, 交易地=广东/深圳, 金额=80000
# ============================================================
cur.execute("""INSERT IGNORE INTO transaction (txn_id, from_card, to_card, user_id, amount, channel, txn_type, device_id, ip, geo, status, txn_at, create_time)
VALUES ('EXT001', 'C20002', 'C20009', 'U10001', 80000, 'online', 'transfer', 'D1001', '15.251.218.204', '广东/深圳', 'success', %s, NOW())""", (now,))
print("[R001] 异地大额转账: txn_id=EXT001, user=U10001, amount=80000, geo=广东/深圳")

# ============================================================
# R002 凌晨密集操作: 3 笔交易在凌晨 2 点, 1 小时内
# ============================================================
night_time = now.replace(hour=2, minute=0, second=0, microsecond=0)
if night_time > now:
    night_time = night_time - timedelta(days=1)
for i, t in enumerate([night_time, night_time + timedelta(minutes=15), night_time + timedelta(minutes=30)]):
    cur.execute("""INSERT IGNORE INTO transaction (txn_id, from_card, to_card, user_id, amount, channel, txn_type, device_id, ip, geo, status, txn_at, create_time)
    VALUES (%s, 'C20002', NULL, 'U10001', 1000, 'mobile', 'transfer', 'D1001', '15.251.218.204', '湖北/武汉', 'success', %s, NOW())""",
    (f'EXT002{i+1}', t))
print(f"[R002] 凌晨密集操作: 3 笔交易 (EXT0021-3), user=U10001, 时间=02:00/02:15/02:30")

# ============================================================
# R005 新设备大额: 新设备 first_seen=昨天, 金额=50000
# ============================================================
cur.execute("""INSERT IGNORE INTO device_fingerprint (device_id, user_id, fingerprint_hash, first_seen, last_seen, os, browser, risk_score)
VALUES ('DEV_NEW01', 'U10001', 'newhash001', %s, %s, 'Android', 'Chrome', 50)""", (yesterday, now))
cur.execute("""INSERT IGNORE INTO transaction (txn_id, from_card, to_card, user_id, amount, channel, txn_type, device_id, ip, geo, status, txn_at, create_time)
VALUES ('EXT003', 'C20002', NULL, 'U10001', 50000, 'mobile', 'transfer', 'DEV_NEW01', '15.251.218.204', '湖北/武汉', 'success', %s, NOW())""", (now,))
print("[R005] 新设备大额: txn_id=EXT003, device=DEV_NEW01 (2天前注册), amount=50000")

# ============================================================
# R008 多卡归集: 3 笔交易从不同卡转入同一卡, 1 小时内
# ============================================================
target_card = 'C20099'
cur.execute("""INSERT IGNORE INTO bank_card (card_id, user_id, card_no_hash, bank_code, card_type, credit_limit, balance, status, create_time)
VALUES ('C20099', 'U10005', 'targethash', 'ICBC', 'debit', NULL, 500000, 'active', NOW())""")
for i in range(3):
    cur.execute("""INSERT IGNORE INTO transaction (txn_id, from_card, to_card, user_id, amount, channel, txn_type, device_id, ip, geo, status, txn_at, create_time)
    VALUES (%s, %s, %s, 'U10005', 20000, 'online', 'transfer', 'D1005', '203.61.7.130', '上海/上海', 'success', %s, NOW())""",
    (f'EXT004{i+1}', f'C2000{6+i}', target_card, now - timedelta(minutes=20-i*5)))
print(f"[R008] 多卡归集: 3 笔转入卡 C20099 (EXT0041-3), 1小时内")

# ============================================================
# R012 信贷申请突击: 给 U10002 插 3 条贷款申请 (6个月内)
# ============================================================
for i in range(3):
    cur.execute("""INSERT IGNORE INTO loan_application (loan_id, user_id, amount, term_months, purpose, monthly_income, debt_ratio, status, apply_at, create_time)
    VALUES (%s, 'U10002', 100000, 12, '购车', 15000, 0.3, 'pending', %s, NOW())""",
    (f'L_EXT{i+1}', now - timedelta(days=30*i)))
print("[R012] 信贷申请突击: U10002 近6个月3笔贷款申请 (L_EXT1-3)")

# ============================================================
# R018 设备多人共用: 设备 DEV_SHARED 关联 5+ 个用户
# ============================================================
for i, uid in enumerate(['U10010', 'U10011', 'U10012', 'U10013', 'U10014']):
    # 确保用户存在
    cur.execute("SELECT COUNT(*) FROM user_info WHERE user_id=%s", (uid,))
    if cur.fetchone()[0] == 0:
        cur.execute("""INSERT INTO user_info (user_id, name, id_card_hash, credit_score, register_at, kyc_level, phone, email, status)
        VALUES (%s, %s, %s, 600, %s, 1, %s, %s, 'active')""",
        (uid, f'极端用户{i+1}', f'hash{uid}', yesterday, f'1{i}0000000', f'{uid}@test.com'))
    cur.execute("""INSERT IGNORE INTO device_fingerprint (device_id, user_id, fingerprint_hash, first_seen, last_seen, os, browser, risk_score)
    VALUES ('DEV_SHARED', %s, 'sharedhash', %s, %s, 'Windows', 'Chrome', 30)""",
    (uid, yesterday, now))
print("[R018] 设备多人共用: DEV_SHARED 关联 5 个用户 (U10010-U10014)")

# ============================================================
# R025 IP代理秒拨: 插入代理 IP, 然后从该 IP 登录
# ============================================================
proxy_ip = '66.66.66.66'
cur.execute("""INSERT INTO ip_geo_location (ip, country, province, city, isp, is_proxy, is_tor, last_update)
VALUES ('66.66.66.66', '中国', '北京', '北京', '未知', 1, 0, NOW())
ON DUPLICATE KEY UPDATE is_proxy=1""")
cur.execute("""INSERT IGNORE INTO transaction (txn_id, from_card, to_card, user_id, amount, channel, txn_type, device_id, ip, geo, status, txn_at, create_time)
VALUES ('EXT006', 'C20003', NULL, 'U10002', 500, 'online', 'transfer', 'D1002', '66.66.66.66', '北京/北京', 'success', %s, NOW())""", (now,))
print("[R025] IP代理秒拨: ip=66.66.66.66 (is_proxy=1), txn_id=EXT006")

# ============================================================
# R030 黑卡拦截: 收款卡加入黑名单
# ============================================================
black_card = 'C20088'
cur.execute("""INSERT IGNORE INTO bank_card (card_id, user_id, card_no_hash, bank_code, card_type, credit_limit, balance, status, create_time)
VALUES ('C20088', 'U10005', 'blackhash', 'BOC', 'debit', NULL, 0, 'active', NOW())""")
cur.execute("""INSERT IGNORE INTO blacklist_extra (type, value, reason, expire_at)
VALUES ('card', 'C20088', '疑似洗钱黑卡', NULL)""")
cur.execute("""INSERT IGNORE INTO transaction (txn_id, from_card, to_card, user_id, amount, channel, txn_type, device_id, ip, geo, status, txn_at, create_time)
VALUES ('EXT007', 'C20002', 'C20088', 'U10001', 30000, 'online', 'transfer', 'D1001', '15.251.218.204', '湖北/武汉', 'success', %s, NOW())""", (now,))
print("[R030] 黑卡拦截: 收款卡 C20088 在黑名单, txn_id=EXT007")

conn.close()
print("\n极端数据插入完成!\n")

# ============================================================
# 调风控接口
# ============================================================
print("=" * 60)
print("调用风控检查接口")
print("=" * 60)

checks = [
    ("R001", "异地大额转账", {"event_type": "转账", "source_id": "EXT001", "user_id": "U10001", "card_id": "C20002", "device_id": "D1001", "ip": "15.251.218.204", "event_data": {"geo": "广东/深圳"}}),
    ("R002", "凌晨密集操作", {"event_type": "转账", "source_id": "EXT0021", "user_id": "U10001", "card_id": "C20002", "device_id": "D1001", "ip": "15.251.218.204", "event_data": {"geo": "湖北/武汉"}}),
    ("R005", "新设备大额", {"event_type": "转账", "source_id": "EXT003", "user_id": "U10001", "card_id": "C20002", "device_id": "DEV_NEW01", "ip": "15.251.218.204", "event_data": {"geo": "湖北/武汉"}}),
    ("R008", "多卡归集", {"event_type": "转账", "source_id": "EXT0041", "user_id": "U10005", "card_id": "C20006", "device_id": "D1005", "ip": "203.61.7.130", "event_data": {"geo": "上海/上海"}}),
    ("R012", "信贷申请突击", {"event_type": "贷款", "source_id": "L_EXT1", "user_id": "U10002", "event_data": {}}),
    ("R018", "设备多人共用", {"event_type": "登录", "source_id": "", "user_id": "U10010", "device_id": "DEV_SHARED", "ip": "15.251.218.204", "event_data": {}}),
    ("R025", "IP代理秒拨", {"event_type": "登录", "source_id": "", "user_id": "U10002", "device_id": "D1002", "ip": "66.66.66.66", "event_data": {}}),
    ("R030", "黑卡拦截", {"event_type": "转账", "source_id": "EXT007", "user_id": "U10001", "card_id": "C20002", "device_id": "D1001", "ip": "15.251.218.204", "event_data": {"geo": "湖北/武汉"}}),
]

print(f"\n{'规则':<6} {'场景':<14} {'score':>6} {'level':<6} {'decision':<8} {'rules':>5} {'ml_score':>8} {'hit_rules'}")
print("-" * 100)

for rule_id, name, payload in checks:
    r = httpx.post(f"{BASE}/api/risk/check", json=payload, timeout=30)
    if r.status_code == 200:
        d = r.json()
        hit = ", ".join(h["rule_id"] for h in d.get("triggered_rules", [])) or "—"
        ml = f"{d.get('ml_score', 'N/A')}"
        print(f"{rule_id:<6} {name:<14} {d['final_score']:>6} {d['risk_level']:<6} {d['decision']:<8} {d['rule_count']:>5} {ml:>8} {hit}")
    else:
        print(f"{rule_id:<6} {name:<14} ERROR: {r.status_code} {r.text[:150]}")

print("-" * 100)
