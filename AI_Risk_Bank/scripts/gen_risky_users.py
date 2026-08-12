"""生成银行版高风险客户、设备和 IP 脱敏数据。"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from app.database import AsyncSessionLocal


async def generate(count: int = 20, reset: bool = False):
    async with AsyncSessionLocal() as db:
        if reset:
            await db.execute(text("DELETE FROM bank_user_info WHERE user_id LIKE 'RISK%'") )
        for index in range(1, count + 1):
            user_id = f"RISK{index:04d}"
            device_id = f"RISK_DEV{index:04d}"
            now = datetime.now()
            await db.execute(text("""
                INSERT INTO bank_user_info(user_id,name,id_card_hash,credit_score,register_at,kyc_level,account_status,usual_city)
                VALUES(:uid,:name,:id_hash,:score,:register_at,'基础','关注',:city)
                ON DUPLICATE KEY UPDATE credit_score=:score, account_status='关注'
            """), {"uid": user_id, "name": f"风险客户{index}", "id_hash": f"hash_{user_id}", "score": 450 + index % 80, "register_at": now - timedelta(days=index), "city": "上海" if index % 2 else "北京"})
            await db.execute(text("""
                INSERT INTO device_fingerprint(device_id,user_id,fingerprint_hash,first_seen,last_seen,os,browser,is_emulator)
                VALUES(:device,:uid,:fingerprint,:first_seen,:last_seen,'Android','App',1)
            """), {"device": device_id, "uid": user_id, "fingerprint": f"hash_{device_id}", "first_seen": now - timedelta(days=2), "last_seen": now})
        await db.commit()
        print(f"已生成银行高风险客户 {count} 个")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    asyncio.run(generate(args.count, args.reset))
