# -*- coding: utf-8 -*-
"""调试：对 RISK 账户逾期贷款直接跑 process_event，看 decision"""
import asyncio
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event

async def main():
    db = AsyncSessionLocal()
    try:
        # 1. 找一条 RISK 逾期贷款
        rs = await db.execute(text("""
            SELECT l.loan_id, l.account_id, l.overdue_days, l.repay_status
            FROM loan_info l
            WHERE l.account_id LIKE 'RISK%' AND l.overdue_days > 0
            LIMIT 3
        """))
        loans = rs.all()
        print("RISK 逾期贷款:", [dict(r._mapping) for r in loans])

        # 2. 找 RISK 大额交易
        rs = await db.execute(text("""
            SELECT txn_id, account_id, txn_amount FROM transaction_order
            WHERE account_id LIKE 'RISK%' AND txn_amount >= 50000
            LIMIT 3
        """))
        big = rs.all()
        print("RISK 大额交易(>=5w):", [dict(r._mapping) for r in big])

        if loans:
            loan_id, account_id = loans[0].loan_id, loans[0].account_id
            req = RiskCheckRequest(
                event_type="贷款申请", source_id=loan_id,
                user_id=account_id, account_id=account_id, loan_id=loan_id,
            )
            print(f"\n>>> 跑 process_event: 贷款 {loan_id} ({account_id})")
            result = await process_event(db, req)
            print(">>> 返回结果:", result)
            await db.commit()

            # 查最新 assessment
            rs = await db.execute(text("""
                SELECT assessment_id, decision, risk_score, risk_level, user_id
                FROM risk_assessment
                WHERE user_id = :uid
                ORDER BY create_time DESC LIMIT 3
            """), {"uid": account_id})
            print(">>> 该用户最近评估:", [dict(r._mapping) for r in rs.all()])

            # 查最新 event
            rs = await db.execute(text("""
                SELECT event_id, event_type, event_source_id, user_id
                FROM risk_event
                WHERE user_id = :uid
                ORDER BY create_time DESC LIMIT 3
            """), {"uid": account_id})
            print(">>> 该用户最近事件:", [dict(r._mapping) for r in rs.all()])

            # 查 feature 表
            rs = await db.execute(text("""
                SELECT feature_name, feature_value, feature_value_str
                FROM risk_feature
                WHERE event_id = (SELECT event_id FROM risk_event WHERE user_id = :uid ORDER BY create_time DESC LIMIT 1)
                LIMIT 8
            """), {"uid": account_id})
            print(">>> 最近事件的 features:")
            for r in rs:
                print("   ", dict(r._mapping))
    finally:
        await db.close()

asyncio.run(main())
