# -*- coding: utf-8 -*-
"""临时验证脚本：检查 RISK 账户数据 (异步)"""
import asyncio
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app.database import AsyncSessionLocal

async def main():
    db = AsyncSessionLocal()
    queries = [
        "SELECT account_id, account_status, risk_level FROM account_info WHERE account_id LIKE 'RISK%' ORDER BY account_id LIMIT 5",
        "SELECT account_id, COUNT(*) AS c FROM transaction_order WHERE account_id LIKE 'RISK%' GROUP BY account_id ORDER BY account_id LIMIT 5",
        "SELECT account_id, repay_status, overdue_days FROM loan_info WHERE account_id LIKE 'RISK%' ORDER BY account_id LIMIT 6",
        "SELECT COUNT(*) AS n FROM account_info WHERE account_id LIKE 'RISK%'",
        "SELECT COUNT(*) AS n FROM transaction_order WHERE account_id LIKE 'RISK%'",
        "SELECT COUNT(*) AS n FROM loan_info WHERE account_id LIKE 'RISK%'",
        "SELECT account_id, COUNT(*) AS c FROM user_operation_log WHERE account_id LIKE 'RISK%' GROUP BY account_id ORDER BY account_id LIMIT 5",
    ]
    try:
        for q in queries:
            print('---')
            rs = await db.execute(text(q))
            for r in rs:
                print(dict(r._mapping))
    finally:
        await db.close()

asyncio.run(main())
