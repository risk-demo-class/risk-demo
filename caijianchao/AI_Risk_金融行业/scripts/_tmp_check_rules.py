# -*- coding: utf-8 -*-
"""规则明细 + 条件字段"""
import asyncio
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app.database import AsyncSessionLocal

async def main():
    db = AsyncSessionLocal()
    try:
        rs = await db.execute(text("""
            SELECT rule_id, rule_name, event_type, rule_category, risk_level, risk_score, action, priority, rule_condition
            FROM risk_rule
            ORDER BY event_type, rule_id
        """))
        for r in rs:
            m = dict(r._mapping)
            cond = (m.get('rule_condition') or '')[:200]
            print(f"{m['rule_id']} | evt={m['event_type']} | cat={m['rule_category']} | {m['rule_name']} | score={m['risk_score']} | {m['action']}")
            print(f"      cond: {cond}")
    finally:
        await db.close()

asyncio.run(main())
