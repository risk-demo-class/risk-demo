# -*- coding: utf-8 -*-
"""临时: transaction_order/user_operation_log 列 + gen_risky_users 42-100 行"""
import io, sys, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

async def main():
    from sqlalchemy import text
    from app.database import AsyncSessionLocal, async_engine
    try:
        async with AsyncSessionLocal() as db:
            for tbl in ("transaction_order", "user_operation_log"):
                r = await db.execute(text(f"SHOW COLUMNS FROM {tbl}"))
                print(f"=== {tbl} ===")
                for row in r.fetchall():
                    print(f"  {row[0]:<24} {row[1]}")
                print()
            # 现有 txn_type_code / channel_code / op_type 实际值
            for q in (
                "SELECT txn_type_code, COUNT(*) c FROM transaction_order GROUP BY txn_type_code",
                "SELECT channel_code, COUNT(*) c FROM transaction_order GROUP BY channel_code",
                "SELECT op_type, COUNT(*) c FROM user_operation_log GROUP BY op_type",
            ):
                r = await db.execute(text(q))
                print(f"--- {q.split('FROM')[1].strip()} 分布 ---")
                for row in r.all():
                    print(f"  {row[0]}: {row[1]}")
                print()
    finally:
        await async_engine.dispose()

asyncio.run(main())
