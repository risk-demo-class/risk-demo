"""
生成有风险行为的账户测试数据 (异步).
【P4-L3 2026-08-08 第二轮】支持 --count 指定生成账户数 (默认 5).
【P4-L4 2026-08-12】SQL 字段对齐金融风控表 (transaction_order/loan_info/user_operation_log),
  修复电商遗留字段: txn_type_code 用 code (T001/T003), loan_type→loan_purpose,
  loan_status→repay_status, apply_time→approve_time.

5 种金融风险模式轮换生成 (跟原始 5 个 RISK 账户一一对应):
  模式 1: 高频交易 (35 笔交易, 30 天内)
  模式 2: 大额转账 (5 笔大额转账, 单笔 >= 50000)
  模式 3: 多IP登录 (7 个不同 IP 地址)
  模式 4: 贷款逾期 (3 笔贷款 + 逾期记录)
  模式 5: 可疑交易 (5 笔交易被标记为可疑冻结)

例:
  python scripts/gen_risky_users.py                # 默认 5 个 (RISK001-005)
  python scripts/gen_risky_users.py --count 30     # 30 个 (RISK001-030, 6 套 × 5 模式)
  python scripts/gen_risky_users.py --count 1      # 只 1 个 (RISK001, 高频交易模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 账户再生成

风险模式轮换逻辑: idx % 5, 所以 count=30 → 6 套各 5 个 = 30 个; count=7 → 模式 1-5 + 模式 1-2 = 7 个
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


# 5 种金融风险模式: (模式名, 账户前缀数字起点)
RISK_MODES = ["高频交易", "大额转账", "多IP登录", "贷款逾期", "可疑交易"]


async def _gen_high_freq_txn(conn, account_id: str):
    """模式 1: 高频交易账户 (35 笔交易, 30 天内)"""
    # 账户基础信息
    await conn.execute(text("""
        INSERT IGNORE INTO account_info (account_id, user_name, id_card_no, phone_no, account_type,
        register_time, kyc_level, account_status, risk_level, monthly_income, employment_status)
        VALUES (:aid, '高频用户', :idcard, :phone, '个人', NOW(), '基础认证', '正常', '中', 15000.00, '在职')
    """), {"aid": account_id, "idcard": f"11010119900101{account_id[4:]}", "phone": f"1380013{account_id[4:]}"})

    # 35 笔交易 (消费支付 T003)
    base_date = datetime.now() - timedelta(days=25)
    for i in range(35):
        txn_date = base_date + timedelta(days=i % 25)
        txn_dt = txn_date.strftime("%Y-%m-%d %H:%M:%S")
        await conn.execute(text("""
            INSERT IGNORE INTO transaction_order (txn_id, account_id, counterparty_account, counterparty_name,
            txn_type_code, channel_code, txn_amount, txn_currency, txn_time, request_time,
            txn_status, is_overseas, country_code, ip_address, device_id, device_env)
            VALUES (:tid, :aid, 'ACC001', '张伟', 'T003', 'CH005', 5000.00, 'CNY', :dt, :dt,
                    '成功', 0, 'CN', '192.168.1.1', 'DEV001', 'PC')
        """), {"tid": f"TXN_{account_id[4:]}_{i:02d}", "aid": account_id, "dt": txn_dt})


async def _gen_large_transfer(conn, account_id: str):
    """模式 2: 大额转账账户 (5 笔大额转账, 单笔 >= 50000)"""
    # 账户基础信息
    await conn.execute(text("""
        INSERT IGNORE INTO account_info (account_id, user_name, id_card_no, phone_no, account_type,
        register_time, kyc_level, account_status, risk_level, monthly_income, employment_status)
        VALUES (:aid, '大额转账用户', :idcard, :phone, '个人', NOW(), '高级认证', '正常', '高', 80000.00, '在职')
    """), {"aid": account_id, "idcard": f"11010119851215{account_id[4:]}", "phone": f"1390013{account_id[4:]}"})

    # 5 笔大额转账 (T001 转账汇款)
    for i, day in enumerate([15, 10, 5, 3, 1], 1):
        await conn.execute(text("""
            INSERT IGNORE INTO transaction_order (txn_id, account_id, counterparty_account, counterparty_name,
            txn_type_code, channel_code, txn_amount, txn_currency, txn_time, request_time,
            txn_status, is_overseas, country_code, ip_address, device_id, device_env)
            VALUES (:tid, :aid, 'ACC002', '李强', 'T001', 'CH005', 60000.00, 'CNY', DATE_SUB(NOW(), INTERVAL :d DAY), DATE_SUB(NOW(), INTERVAL :d DAY),
                    '成功', 0, 'CN', '192.168.2.1', 'DEV002', 'PC')
        """), {"tid": f"TXN_{account_id[4:]}_{i:02d}", "aid": account_id, "d": day})


async def _gen_multi_ip_login(conn, account_id: str):
    """模式 3: 多IP登录账户 (7 个不同 IP 地址)"""
    # 账户基础信息
    await conn.execute(text("""
        INSERT IGNORE INTO account_info (account_id, user_name, id_card_no, phone_no, account_type,
        register_time, kyc_level, account_status, risk_level, monthly_income, employment_status)
        VALUES (:aid, '多IP登录用户', :idcard, :phone, '个人', NOW(), '基础认证', '正常', '中', 12000.00, '自由职业')
    """), {"aid": account_id, "idcard": f"11010119920520{account_id[4:]}", "phone": f"1370013{account_id[4:]}"})

    # 7 个不同 IP 地址的登录记录
    ip_addresses = ['192.168.1.1', '192.168.2.2', '10.0.0.1', '172.16.0.1', '192.168.100.1', '10.10.10.1', '172.20.0.1']
    for i, ip in enumerate(ip_addresses):
        await conn.execute(text("""
            INSERT IGNORE INTO user_operation_log (account_id, op_type, op_time, ip_address, device_id, op_result)
            VALUES (:aid, '登录', DATE_SUB(NOW(), INTERVAL :d HOUR), :ip, :did, '成功')
        """), {"aid": account_id, "d": i * 2, "ip": ip, "did": f"DEV{i:03d}"})


async def _gen_loan_overdue(conn, account_id: str):
    """模式 4: 贷款逾期账户 (3 笔贷款, 其中 2 笔逾期)

    【P4-L4 2026-08-12】逾期信息直接写在 loan_info.repay_status/overdue_days
    (op_type 枚举没有"贷款逾期", user_operation_log 只记录行为操作).
    """
    # 账户基础信息
    await conn.execute(text("""
        INSERT IGNORE INTO account_info (account_id, user_name, id_card_no, phone_no, account_type,
        register_time, kyc_level, account_status, risk_level, monthly_income, employment_status)
        VALUES (:aid, '贷款逾期用户', :idcard, :phone, '个人', NOW(), '基础认证', '正常', '高', 8000.00, '自由职业')
    """), {"aid": account_id, "idcard": f"11010119880818{account_id[4:]}", "phone": f"1360013{account_id[4:]}"})

    # 3 笔贷款: 第 1 笔已逾期 45 天, 第 2 笔已逾期 15 天, 第 3 笔正常还款中
    loan_specs = [
        (30, 50000.00, '消费贷', '逾期', 45),
        (20, 30000.00, '消费贷', '逾期', 15),
        (10, 20000.00, '教育贷', '正常', 0),
    ]
    for i, (day, amount, purpose, repay_status, overdue_days) in enumerate(loan_specs, 1):
        await conn.execute(text("""
            INSERT IGNORE INTO loan_info (loan_id, account_id, loan_purpose, loan_amount, loan_term,
            annual_rate, approve_time, due_time, repay_status, overdue_days, remaining_principal, lender_org)
            VALUES (:lid, :aid, :purpose, :amount, 12, 0.12, DATE_SUB(NOW(), INTERVAL :d DAY),
                    DATE_ADD(DATE_SUB(NOW(), INTERVAL :d DAY), INTERVAL 12 MONTH),
                    :status, :od, :amount * 0.8, '测试银行')
        """), {
            "lid": f"LOAN_{account_id[4:]}_{i:02d}", "aid": account_id, "purpose": purpose,
            "amount": amount, "d": day, "status": repay_status, "od": overdue_days,
        })


async def _gen_suspicious_txn(conn, account_id: str):
    """模式 5: 可疑交易账户 (5 笔交易被标记为可疑冻结)"""
    # 账户基础信息
    await conn.execute(text("""
        INSERT IGNORE INTO account_info (account_id, user_name, id_card_no, phone_no, account_type,
        register_time, kyc_level, account_status, risk_level, monthly_income, employment_status)
        VALUES (:aid, '可疑交易用户', :idcard, :phone, '个人', NOW(), '未认证', '正常', '高', 5000.00, '学生')
    """), {"aid": account_id, "idcard": f"11010119960722{account_id[4:]}", "phone": f"1350013{account_id[4:]}"})

    # 5 笔可疑交易 (txn_status = '可疑冻结')
    for i, day in enumerate([7, 5, 3, 2, 1], 1):
        await conn.execute(text("""
            INSERT IGNORE INTO transaction_order (txn_id, account_id, counterparty_account, counterparty_name,
            txn_type_code, channel_code, txn_amount, txn_currency, txn_time, request_time,
            txn_status, is_overseas, country_code, ip_address, device_id, device_env)
            VALUES (:tid, :aid, 'ACC012', '褚霞', 'T001', 'CH004', 15000.00, 'CNY', DATE_SUB(NOW(), INTERVAL :d DAY), DATE_SUB(NOW(), INTERVAL :d DAY),
                    '可疑冻结', 1, 'HK', '192.168.100.1', 'DEV100', 'MOBILE')
        """), {"tid": f"TXN_{account_id[4:]}_{i:02d}", "aid": account_id, "d": day})


# 5 种金融风险模式生成器
MODE_GENERATORS = [
    _gen_high_freq_txn,      # 模式 0: 高频交易
    _gen_large_transfer,     # 模式 1: 大额转账
    _gen_multi_ip_login,     # 模式 2: 多IP登录
    _gen_loan_overdue,       # 模式 3: 贷款逾期
    _gen_suspicious_txn,     # 模式 4: 可疑交易
]


async def gen_risky_users(count: int = 5, reset: bool = False):
    """生成 N 个 RISK 高风险账户 (5 种金融风险模式轮换).

    Args:
        count: 生成账户数 (默认 5). 例: count=30 → RISK001-RISK030 (6 套 × 5 模式).
        reset: 是否先删旧 RISK 账户 + 相关数据 (默认 False, 用 INSERT IGNORE 增量插入).
    """
    if count < 1:
        raise ValueError(f"--count 必须 >= 1, 当前 {count}")

    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        if reset:
            print(f"[reset] 删旧 RISK 账户 + 关联数据...")
            # 先删从表 (子表), 再删主表, 避免外键约束
            for tbl in ("aml_suspicious_report", "user_operation_log",
                        "loan_info", "transaction_order", "account_info"):
                await conn.execute(text(f"DELETE FROM {tbl} WHERE account_id LIKE 'RISK%'"))
            print(f"  清理完成")

        # 批量生成 N 个 RISK 账户 (5 种金融风险模式轮换)
        print(f"[generate] 生成 {count} 个 RISK 高风险账户 (5 种金融风险模式轮换)...")
        account_ids = [f"RISK{i:03d}" for i in range(1, count + 1)]

        # 逐个账户按模式生成交易/贷款/登录记录
        for idx, account_id in enumerate(account_ids):
            mode_idx = idx % 5  # 0-4 轮换
            mode_name = RISK_MODES[mode_idx]
            print(f"  [{idx+1}/{count}] {account_id} (模式 {mode_idx+1}: {mode_name})")
            await MODE_GENERATORS[mode_idx](conn, account_id)

        await conn.commit()

        # 统计
        from sqlalchemy import text as _text
        r = await conn.execute(_text("SELECT COUNT(*) FROM account_info WHERE account_id LIKE 'RISK%'"))
        total_accounts = r.scalar()
        r = await conn.execute(_text("SELECT COUNT(*) FROM transaction_order WHERE account_id LIKE 'RISK%'"))
        total_txns = r.scalar()
        r = await conn.execute(_text("SELECT COUNT(*) FROM loan_info WHERE account_id LIKE 'RISK%'"))
        total_loans = r.scalar()

        print(f"\n[完成] 高风险账户数据生成完成!")
        print(f"  RISK 账户:     {total_accounts} 个")
        print(f"  RISK 交易:     {total_txns} 笔")
        print(f"  RISK 贷款:     {total_loans} 笔")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="造 RISK 高风险用户 + 交易/贷款/登录记录. 默认 5 个, --count 指定数量.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python scripts/gen_risky_users.py                # 5 个 (RISK001-005, 一套)
  python scripts/gen_risky_users.py --count 30     # 30 个 (RISK001-030, 6 套 × 5 模式)
  python scripts/gen_risky_users.py --count 1      # 1 个 (RISK001, 高频交易模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 数据再生成
        """,
    )
    parser.add_argument("--count", type=int, default=5, help="生成 RISK 用户数 (默认 5)")
    parser.add_argument("--reset", action="store_true", help="先删旧 RISK 用户 + 关联数据")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))
