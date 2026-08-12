"""生成银行版风险评估数据。"""
import argparse
import asyncio
import os
import sys
from sqlalchemy import select
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import AsyncSessionLocal
from app.models import BankTransaction, LoanApplication, LoginLog
from app.schemas import RiskCheckRequest
from app.service.event import process_event


async def generate(count: int = 30, balance_pos: bool = False, **_):
    async with AsyncSessionLocal() as db:
        rows = []
        if balance_pos:
            rows.extend(("大额转账", x.txn_id, x.user_id) for x in (await db.execute(select(BankTransaction))).scalars().all())
            rows.extend(("异常登录", x.login_id, x.user_id) for x in (await db.execute(select(LoginLog))).scalars().all())
        else:
            rows.extend(("大额转账", x.txn_id, x.user_id) for x in (await db.execute(select(BankTransaction))).scalars().all())
            rows.extend(("贷款申请", x.loan_id, x.user_id) for x in (await db.execute(select(LoanApplication))).scalars().all())
            rows.extend(("异常登录", x.login_id, x.user_id) for x in (await db.execute(select(LoginLog))).scalars().all())
        if not rows:
            print("没有银行业务数据，请先执行 init_db.py")
            return
        success = 0
        for event_type, source_id, user_id in (rows * max(1, (count + len(rows) - 1) // len(rows)))[:count]:
            try:
                await process_event(db, RiskCheckRequest(event_type=event_type, source_id=source_id, user_id=user_id, event_data={"generated": True}))
                success += 1
            except Exception as exc:
                await db.rollback()
                print(f"跳过 {event_type}/{source_id}: {exc}")
        print(f"已生成银行风控评估 {success} 条")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--balance-pos", action="store_true")
    parser.add_argument("--target-pos-ratio", type=float, default=None)
    args = parser.parse_args()
    asyncio.run(generate(args.count, args.balance_pos, target_pos_ratio=args.target_pos_ratio))
