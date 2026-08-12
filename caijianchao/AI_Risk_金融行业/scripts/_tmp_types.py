# -*- coding: utf-8 -*-
"""临时: txn_type_code 名称映射 + gen_risky_users.py 全文行号"""
import io, sys, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

async def main():
    from sqlalchemy import text
    from app.database import AsyncSessionLocal, async_engine
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(text("SELECT txn_type_code, txn_type_name, is_credit, is_debit, is_cash FROM transaction_type ORDER BY txn_type_code"))
            print("=== transaction_type ===")
            for row in r.all():
                print(f"  {row.txn_type_code}: {row.txn_type_name} (credit={row.is_credit}, debit={row.is_debit}, cash={row.is_cash})")
            r = await db.execute(text("SELECT channel_code, channel_name FROM transaction_channel ORDER BY channel_code"))
            print("\n=== transaction_channel ===")
            for row in r.all():
                print(f"  {row.channel_code}: {row.channel_name}")
    finally:
        await async_engine.dispose()

asyncio.run(main())

print("\n=== gen_risky_users.py 各模式函数结构 ===")
with open("scripts/gen_risky_users.py", encoding="utf-8") as f:
    lines = f.readlines()
for i, line in enumerate(lines, 1):
    if line.startswith("async def") or line.startswith("def ") or line.startswith("MODE_") or line.startswith("# "):
        print(f"{i:4d}| {line.rstrip()}")
