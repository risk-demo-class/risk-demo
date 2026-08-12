"""
生成有风险行为的用户测试数据 (异步) — 银行风控版.
【P4-L3 2026-08-11 迁移】从电商模型改为银行风控模型.

5 种风险模式轮换生成:
  模式 1: 洗钱快进快出 (频繁小额转账, 转入即转出)
  模式 2: 结构化交易 (35 笔拆分, 每笔略低於大额阈值)
  模式 3: 多头借贷 (大额贷款 + 多平台 + 高负债率)
  模式 4: 异地登录/IP跳变 (7 城 IP, 新设备, 代理)
  模式 5: 欺诈关联 (关联案件 + 可疑交易报告)

例:
  python scripts/gen_risky_users.py                # 默认 5 个 (RISK001-005)
  python scripts/gen_risky_users.py --count 30     # 30 个 (6 套 x 5 模式)
  python scripts/gen_risky_users.py --count 1      # 只 1 个 (RISK001, 洗钱)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 数据再生成
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

RISK_MODES = ["洗钱快进快出", "结构化交易", "多头借贷", "IP多地跳变", "欺诈关联"]


def _card_id(uid: str, idx: int) -> str:
    return f"6222{uid[4:]}00{idx:02d}"


def _txn_id(uid: str, idx: int) -> str:
    return f"TXN_{uid[4:]}_{idx:03d}"


def _app_id(uid: str, idx: int) -> str:
    return f"APP_{uid[4:]}_{idx:02d}"


async def _mode1_money_launder(conn, user_id: str):
    """模式 1: 洗钱快进快出 — 低KYC, 频繁小额转账, 转入即转出."""
    now = datetime.now()
    await conn.execute(text("""
        INSERT IGNORE INTO user_info (user_id, name_hash, id_card_hash, phone_hash, email,
            kyc_level, credit_score, reg_date, status, reg_ip, reg_city, create_time)
        VALUES (:uid, :name, :idc, :ph, :em, 'L1', 400, :rd, '正常', '10.0.0.1', '深圳', NOW())
    """), {
        "uid": user_id,
        "name": f"HASH_NAME_{user_id}",
        "idc": f"HASH_ID_{user_id}",
        "ph": f"HASH_PHONE_{user_id}",
        "em": f"{user_id.lower()}@test.com",
        "rd": (now - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S"),
    })

    # 2 张卡
    for i in [1, 2]:
        await conn.execute(text("""
            INSERT IGNORE INTO bank_card (card_id, user_id, card_number_hash, card_type,
                bank_name, credit_limit, available_limit, open_date, card_status, is_virtual, create_time)
            VALUES (:cid, :uid, :cn, '借记卡', :bn, NULL, NULL, :od, '正常', 0, NOW())
        """), {
            "cid": _card_id(user_id, i),
            "uid": user_id,
            "cn": f"HASH_CARD_{user_id}_{i}",
            "bn": ["招商银行", "建设银行"][i - 1],
            "od": (now - timedelta(days=180)).strftime("%Y-%m-%d"),
        })

    # 20 笔转入→转出 (快进快出)
    for i in range(1, 21):
        day_offset = max(1, 30 - i)
        t = now - timedelta(days=day_offset)
        txn_time = t.strftime("%Y-%m-%d %H:%M:%S")
        # 转入
        await conn.execute(text("""
            INSERT IGNORE INTO transaction (txn_id, from_card, to_card, user_id, amount,
                txn_type, channel, txn_time, txn_status, ip, city, device_id, remark, is_international, create_time)
            VALUES (:tid, :f, :t, :uid, :amt, '转账', '手机银行', :tt, '成功', :ip, :city, :did, :rm, 0, NOW())
        """), {
            "tid": _txn_id(user_id, i * 2 - 1),
            "f": "FOREIGN_CARD_001",
            "t": _card_id(user_id, 1),
            "uid": user_id,
            "amt": 1000.00 + (i % 10) * 500.00,
            "tt": txn_time,
            "ip": f"192.168.{i}.1",
            "city": "深圳",
            "did": f"DEV_{user_id}",
            "rm": "测试转入",
        })
        # 立即转出 (快进快出)
        t2 = t + timedelta(minutes=5)
        await conn.execute(text("""
            INSERT IGNORE INTO transaction (txn_id, from_card, to_card, user_id, amount,
                txn_type, channel, txn_time, txn_status, ip, city, device_id, remark, is_international, create_time)
            VALUES (:tid, :f, :t, :uid, :amt, '转账', '手机银行', :tt, '成功', :ip, :city, :did, :rm, 0, NOW())
        """), {
            "tid": _txn_id(user_id, i * 2),
            "f": _card_id(user_id, 1),
            "t": "FOREIGN_CARD_002",
            "uid": user_id,
            "amt": 950.00 + (i % 10) * 480.00,
            "tt": t2.strftime("%Y-%m-%d %H:%M:%S"),
            "ip": f"192.168.{i}.1",
            "city": "深圳",
            "did": f"DEV_{user_id}",
            "rm": "快速转出-洗钱特征",
        })


async def _mode2_struct_txn(conn, user_id: str):
    """模式 2: 结构化交易 — 35 笔, 每笔刚好低於大额报告阈值."""
    now = datetime.now()
    await conn.execute(text("""
        INSERT IGNORE INTO user_info (user_id, name_hash, id_card_hash, phone_hash, email,
            kyc_level, credit_score, reg_date, status, reg_ip, reg_city, create_time)
        VALUES (:uid, :name, :idc, :ph, :em, 'L2', 550, :rd, '正常', '10.0.0.2', '上海', NOW())
    """), {
        "uid": user_id,
        "name": f"HASH_NAME_{user_id}",
        "idc": f"HASH_ID_{user_id}",
        "ph": f"HASH_PHONE_{user_id}",
        "em": f"{user_id.lower()}@test.com",
        "rd": (now - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S"),
    })

    for i in [1]:
        await conn.execute(text("""
            INSERT IGNORE INTO bank_card (card_id, user_id, card_number_hash, card_type,
                bank_name, credit_limit, available_limit, open_date, card_status, is_virtual, create_time)
            VALUES (:cid, :uid, :cn, '借记卡', :bn, NULL, NULL, :od, '正常', 0, NOW())
        """), {
            "cid": _card_id(user_id, i),
            "uid": user_id,
            "cn": f"HASH_CARD_{user_id}_{i}",
            "bn": "工商银行",
            "od": (now - timedelta(days=90)).strftime("%Y-%m-%d"),
        })

    # 35 笔, 每笔 49000 (略低於 5 万大额报告线)
    for i in range(1, 36):
        day_offset = max(1, 25 - (i * 25) // 35)
        t = now - timedelta(days=day_offset, hours=i % 12)
        await conn.execute(text("""
            INSERT IGNORE INTO transaction (txn_id, from_card, to_card, user_id, amount,
                txn_type, channel, txn_time, txn_status, ip, city, device_id, remark, is_international, create_time)
            VALUES (:tid, :f, :t, :uid, :amt, '转账', '网银', :tt, '成功', :ip, :city, :did, :rm, 0, NOW())
        """), {
            "tid": _txn_id(user_id, i),
            "f": _card_id(user_id, 1),
            "t": f"TO_ACC_{(i % 10):03d}",
            "uid": user_id,
            "amt": 49000.00,
            "tt": t.strftime("%Y-%m-%d %H:%M:%S"),
            "ip": "10.0.0.2",
            "city": "上海",
            "did": f"DEV_{user_id}",
            "rm": f"结构化拆分-第{i}笔",
        })


async def _mode3_multi_loan(conn, user_id: str):
    """模式 3: 多头借贷 — 大额贷款 + 多平台 + 高负债率."""
    now = datetime.now()
    await conn.execute(text("""
        INSERT IGNORE INTO user_info (user_id, name_hash, id_card_hash, phone_hash, email,
            kyc_level, credit_score, reg_date, status, reg_ip, reg_city, create_time)
        VALUES (:uid, :name, :idc, :ph, :em, 'L3', 350, :rd, '正常', '10.0.0.3', '北京', NOW())
    """), {
        "uid": user_id,
        "name": f"HASH_NAME_{user_id}",
        "idc": f"HASH_ID_{user_id}",
        "ph": f"HASH_PHONE_{user_id}",
        "em": f"{user_id.lower()}@test.com",
        "rd": (now - timedelta(days=120)).strftime("%Y-%m-%d %H:%M:%S"),
    })

    # 3 笔大额贷款
    loans = [
        ("个人消费贷", 500000.00, 24, "装修", 0.75, 8000.00),
        ("个人经营贷", 1000000.00, 36, "企业经营周转", 0.85, 8000.00),
        ("信用卡分期", 200000.00, 12, "购物消费", 0.70, 8000.00),
    ]
    for i, (lt, amt, term, purpose, debt, income) in enumerate(loans, 1):
        t = now - timedelta(days=30 - i * 8)
        await conn.execute(text("""
            INSERT IGNORE INTO loan_application (application_id, user_id, loan_type,
                apply_amount, term_months, purpose, debt_ratio, monthly_income,
                credit_score, is_entrusted, apply_status, apply_time, update_time)
            VALUES (:aid, :uid, :lt, :amt, :term, :pur, :dr, :mi, 350, 1, '待审核', :at, NOW())
        """), {
            "aid": _app_id(user_id, i),
            "uid": user_id,
            "lt": lt,
            "amt": amt,
            "term": term,
            "pur": purpose,
            "dr": debt,
            "mi": income,
            "at": t.strftime("%Y-%m-%d %H:%M:%S"),
        })

    # 多平台借贷记录
    for i, (plat, amt, day) in enumerate([
        ("借呗", 80000.00, 25),
        ("微粒贷", 120000.00, 20),
        ("京东金条", 60000.00, 15),
        ("度小满", 100000.00, 10),
    ], 1):
        t = now - timedelta(days=day)
        await conn.execute(text("""
            INSERT IGNORE INTO loan_multi_platform (user_id, institution_name, loan_amount,
                loan_date, loan_status, report_source, create_time)
            VALUES (:uid, :plat, :amt, :ld, '授信中', '征信查询', NOW())
        """), {
            "uid": user_id,
            "plat": plat,
            "amt": amt,
            "ld": t.strftime("%Y-%m-%d"),
        })


async def _mode4_ip_hopping(conn, user_id: str):
    """模式 4: IP多地跳变 — 7 城登录, 新设备, 代理IP."""
    now = datetime.now()
    await conn.execute(text("""
        INSERT IGNORE INTO user_info (user_id, name_hash, id_card_hash, phone_hash, email,
            kyc_level, credit_score, reg_date, status, reg_ip, reg_city, create_time)
        VALUES (:uid, :name, :idc, :ph, :em, 'L2', 500, :rd, '正常', '10.0.0.4', '广州', NOW())
    """), {
        "uid": user_id,
        "name": f"HASH_NAME_{user_id}",
        "idc": f"HASH_ID_{user_id}",
        "ph": f"HASH_PHONE_{user_id}",
        "em": f"{user_id.lower()}@test.com",
        "rd": (now - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S"),
    })

    cities = [
        ("北京", "1.2.3.4", False, False),
        ("上海", "2.3.4.5", False, True),
        ("广州", "3.4.5.6", False, False),
        ("深圳", "4.5.6.7", True, False),
        ("成都", "5.6.7.8", False, True),
        ("杭州", "6.7.8.9", True, False),
        ("武汉", "7.8.9.10", False, False),
    ]
    for i, (city, ip, is_new, is_proxy) in enumerate(cities, 1):
        t = now - timedelta(days=7 - i)
        await conn.execute(text("""
            INSERT IGNORE INTO login_log (login_id, user_id, login_time, login_ip, login_city,
                login_device_id, login_result, fail_reason, is_new_device, is_proxy_ip, session_id)
            VALUES (:lid, :uid, :lt, :ip, :city, :did, '成功', NULL, :nd, :proxy, :sid)
        """), {
            "lid": int(f"{user_id[4:]}{i:02d}"),
            "uid": user_id,
            "lt": t.strftime("%Y-%m-%d %H:%M:%S"),
            "ip": ip,
            "city": city,
            "did": f"DEV_{user_id}_{i % 3}" if not is_new else f"DEV_NEW_{i}",
            "nd": 1 if is_new else 0,
            "proxy": 1 if is_proxy else 0,
            "sid": f"SESS_{user_id[4:]}_{i:02d}",
        })


async def _mode5_fraud_linked(conn, user_id: str):
    """模式 5: 欺诈关联 — 案件 + 可疑交易报告 + 黑名单对手方."""
    now = datetime.now()
    await conn.execute(text("""
        INSERT IGNORE INTO user_info (user_id, name_hash, id_card_hash, phone_hash, email,
            kyc_level, credit_score, reg_date, status, reg_ip, reg_city, create_time)
        VALUES (:uid, :name, :idc, :ph, :em, 'L1', 200, :rd, '冻结', '10.0.0.5', '武汉', NOW())
    """), {
        "uid": user_id,
        "name": f"HASH_NAME_{user_id}",
        "idc": f"HASH_ID_{user_id}",
        "ph": f"HASH_PHONE_{user_id}",
        "em": f"{user_id.lower()}@test.com",
        "rd": (now - timedelta(days=200)).strftime("%Y-%m-%d %H:%M:%S"),
    })

    # 卡
    for i in [1]:
        await conn.execute(text("""
            INSERT IGNORE INTO bank_card (card_id, user_id, card_number_hash, card_type,
                bank_name, credit_limit, available_limit, open_date, card_status, is_virtual, create_time)
            VALUES (:cid, :uid, :cn, '借记卡', :bn, NULL, NULL, :od, '冻结', 0, NOW())
        """), {
            "cid": _card_id(user_id, i),
            "uid": user_id,
            "cn": f"HASH_CARD_{user_id}_{i}",
            "bn": "农业银行",
            "od": (now - timedelta(days=300)).strftime("%Y-%m-%d"),
        })

    # 2 笔可疑交易
    for i, (amt, day) in enumerate([(150000.00, 15), (80000.00, 7)], 1):
        t = now - timedelta(days=day)
        tid = _txn_id(user_id, i)
        await conn.execute(text("""
            INSERT IGNORE INTO transaction (txn_id, from_card, to_card, user_id, amount,
                txn_type, channel, txn_time, txn_status, ip, city, device_id, remark, is_international, create_time)
            VALUES (:tid, :f, :t, :uid, :amt, '转账', '柜面', :tt, '成功', :ip, :city, :did, :rm, 0, NOW())
        """), {
            "tid": tid,
            "f": _card_id(user_id, 1),
            "t": "BLACK_ACCOUNT_001",
            "uid": user_id,
            "amt": amt,
            "tt": t.strftime("%Y-%m-%d %H:%M:%S"),
            "ip": "10.0.0.5",
            "city": "武汉",
            "did": f"DEV_{user_id}",
            "rm": "涉嫌电信诈骗",
        })
        await conn.execute(text("""
            INSERT IGNORE INTO txn_suspicious_report (report_id, txn_id, user_id, report_type,
                amount, trigger_rule, report_status, create_time, submit_time)
            VALUES (:rid, :tid, :uid, '可疑', :amt, :rule, '已上报', NOW(), :st)
        """), {
            "rid": int(f"{user_id[4:]}{i:02d}"),
            "tid": tid,
            "uid": user_id,
            "amt": amt,
            "rule": f"R0{i + 28}",
            "st": t.strftime("%Y-%m-%d %H:%M:%S"),
        })

    # 2 个欺诈案件
    for i, (scenario, amt, source, day) in enumerate([
        ("F1", 150000.00, "公安通报", 10),
        ("F3", 80000.00, "内部风控", 5),
    ], 1):
        t = now - timedelta(days=day)
        await conn.execute(text("""
            INSERT IGNORE INTO fraud_case_record (fraud_case_id, fraud_scenario, user_id,
                involved_amount, report_source, report_time, case_status, remark, create_time)
            VALUES (:fid, :fs, :uid, :amt, :rs, :rt, '调查中', :rm, NOW())
        """), {
            "fid": int(f"{user_id[4:]}{i:02d}"),
            "fs": scenario,
            "uid": user_id,
            "amt": amt,
            "rs": source,
            "rt": t.strftime("%Y-%m-%d"),
            "rm": f"涉嫌{scenario}类诈骗",
        })


MODE_GENERATORS = [
    _mode1_money_launder,   # 模式 0: 洗钱快进快出
    _mode2_struct_txn,      # 模式 1: 结构化交易
    _mode3_multi_loan,      # 模式 2: 多头借贷
    _mode4_ip_hopping,      # 模式 3: IP多地跳变
    _mode5_fraud_linked,    # 模式 4: 欺诈关联
]


async def gen_risky_users(count: int = 5, reset: bool = False):
    """生成 N 个 RISK 高风险用户 (5 种模式轮换)."""
    if count < 1:
        raise ValueError(f"--count 必须 >= 1, 当前 {count}")

    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        if reset:
            print("[reset] 删旧 RISK 用户 + 关联数据...")
            await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for tbl in ("txn_suspicious_report", "fraud_case_record",
                        "loan_multi_platform", "loan_approval", "loan_contract",
                        "loan_repayment", "loan_application",
                        "transaction", "login_log", "session_tracking",
                        "bank_card", "user_info"):
                await conn.execute(text(
                    f"DELETE FROM {tbl} WHERE user_id LIKE 'RISK%'"))
            await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            print("  清理完成")

        user_ids = [f"RISK{i:03d}" for i in range(1, count + 1)]

        print(f"[generate] 生成 {count} 个 RISK 高风险用户 (5 模式轮换)...")
        for idx, user_id in enumerate(user_ids):
            mode_idx = idx % 5
            mode_name = RISK_MODES[mode_idx]
            print(f"  [{idx+1}/{count}] {user_id} (模式 {mode_idx+1}: {mode_name})")
            await MODE_GENERATORS[mode_idx](conn, user_id)

        await conn.commit()

        # 统计
        r = await conn.execute(text("SELECT COUNT(*) FROM user_info WHERE user_id LIKE 'RISK%'"))
        total_users = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM transaction WHERE user_id LIKE 'RISK%'"))
        total_txn = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM loan_application WHERE user_id LIKE 'RISK%'"))
        total_loan = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM login_log WHERE user_id LIKE 'RISK%'"))
        total_login = r.scalar()

        print(f"\n[完成] 高风险用户数据生成完成!")
        print(f"  RISK 用户:     {total_users} 个")
        print(f"  RISK 交易:     {total_txn} 笔")
        print(f"  RISK 贷款:     {total_loan} 笔")
        print(f"  RISK 登录:     {total_login} 条")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="造 RISK 高风险用户 — 银行风控版.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python scripts/gen_risky_users.py                # 5 个 (RISK001-005, 一套)
  python scripts/gen_risky_users.py --count 30     # 30 个 (RISK001-030, 6 套 x 5 模式)
  python scripts/gen_risky_users.py --count 1      # 1 个 (RISK001, 洗钱)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 数据再生成
""",
    )
    parser.add_argument("--count", type=int, default=5, help="生成 RISK 用户数 (默认 5)")
    parser.add_argument("--reset", action="store_true", help="先删旧 RISK 用户 + 关联数据")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))
