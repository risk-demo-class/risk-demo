# -*- coding: utf-8 -*-
"""临时: loan_info 表列 + gen_risky_users.py 全部 INSERT"""
import io, sys, asyncio, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

async def main():
    from sqlalchemy import text
    from app.database import AsyncSessionLocal, async_engine
    try:
        async with AsyncSessionLocal() as db:
            r = await db.execute(text("SHOW COLUMNS FROM loan_info"))
            print("=== loan_info 列 ===")
            for row in r.fetchall():
                print(f"  {row[0]:<24} {row[1]}")
    finally:
        await async_engine.dispose()

asyncio.run(main())

with open("scripts/gen_risky_users.py", encoding="utf-8") as f:
    content = f.read()
print("\n=== gen_risky_users.py 所有 INSERT INTO loan_info 段 ===")
for m in re.finditer(r"INSERT IGNORE INTO loan_info(.*?);", content, re.S):
    print(m.group(1)[:600])
    print("-" * 40)
