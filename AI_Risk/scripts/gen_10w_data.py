# Bank risk control - generate additional transaction data
"""Generate additional banking transaction records for stress testing."""
import asyncio, os, random, sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import AsyncSessionLocal
from sqlalchemy import text

N_USERS = 50
TXNS_PER_USER = 50
LARGE_AMOUNT_MIN = 50000
LARGE_AMOUNT_MAX = 500000
SMALL_AMOUNT_MIN = 100
SMALL_AMOUNT_MAX = 50000

async def gen_additional_txs(count: int = 2500):
    async with AsyncSessionLocal() as db:
        # Get existing user_ids
        r = await db.execute(text("SELECT user_id FROM user_info LIMIT :n"), {"n": N_USERS})
        users = [row.user_id for row in r.fetchall()]
        if not users:
            print("No users found - run init_db.py first")
            return

        # Get existing card_ids
        r = await db.execute(text("SELECT card_id, user_id FROM bank_card LIMIT 500"))
        cards = [(row.card_id, row.user_id) for row in r.fetchall()]
        if not cards:
            print("No cards found - run init_db.py first")
            return

        cards_by_user = {}
        for cid, uid in cards:
            cards_by_user.setdefault(uid, []).append(cid)

        channels = ["网银", "手机银行", "快捷支付", "柜面", "ATM", "POS"]
        txn_types = ["转账", "消费", "取现", "还款", "退款"]

        txn_id_counter = 100000
        now = datetime.now()
        inserted = 0

        for i in range(count):
            uid = random.choice(users)
            user_cards = cards_by_user.get(uid, [])
            if len(user_cards) < 1:
                continue
            from_card = random.choice(user_cards)
            # to_card: randomly any card or a specific one from another user
            other_cards = [(c, u) for c, u in cards if u != uid]
            to_card = random.choice(other_cards)[0] if other_cards else from_card

            amount = round(random.uniform(SMALL_AMOUNT_MIN, LARGE_AMOUNT_MAX), 2)
            if random.random() < 0.1:  # 10% large transactions
                amount = round(random.uniform(LARGE_AMOUNT_MIN, LARGE_AMOUNT_MAX), 2)

            txn_time = now - timedelta(
                days=random.randint(0, 90),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )
            txn_id = f"TXN{txn_id_counter:010d}"
            txn_id_counter += 1

            await db.execute(text("""
                INSERT IGNORE INTO transaction
                (txn_id, from_card, to_card, user_id, amount, txn_type, channel, txn_time, txn_status, ip, city, device_id, remark)
                VALUES (:txn_id, :from_card, :to_card, :user_id, :amount, :txn_type, :channel, :txn_time, :txn_status, :ip, :city, :device_id, :remark)
            """), {
                "txn_id": txn_id, "from_card": from_card, "to_card": to_card,
                "user_id": uid, "amount": amount,
                "txn_type": random.choice(txn_types),
                "channel": random.choice(channels),
                "txn_time": txn_time, "txn_status": "成功",
                "ip": f"10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(0,255)}",
                "city": random.choice(["北京", "上海", "深圳", "广州", "杭州", "成都", "武汉", "南京"]),
                "device_id": f"DEV{random.randint(1, 50):04d}",
                "remark": "banking transaction"
            })
            inserted += 1

        await db.commit()
        from app.database import async_engine
        await async_engine.dispose()
    print(f"Generated {inserted} banking transactions")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Generate banking transaction data")
    p.add_argument("--count", type=int, default=2500, help="Number of transactions (default 2500)")
    args = p.parse_args()
    asyncio.run(gen_additional_txs(args.count))
