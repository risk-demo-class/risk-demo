"""从银行业务数据批量生成可训练的风控评估记录。"""
import argparse
import asyncio
import os
import sys

# Keep direct ``python scripts/...`` execution consistent with existing scripts.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import BankTransaction
from app.schemas import RiskCheckRequest
from app.service.event import process_event


async def generate(count: int) -> tuple[int, int]:
    async with AsyncSessionLocal() as db:
        transactions = list((await db.execute(select(BankTransaction).order_by(BankTransaction.txn_id))).scalars().all())
        if not transactions:
            raise RuntimeError("没有银行交易数据，请先运行 scripts/gen_business_data.py")
        positives = 0
        for index in range(count):
            txn = transactions[index % len(transactions)]
            result = await process_event(db, RiskCheckRequest(event_type=txn.transaction_type, source_id=txn.txn_id, user_id=txn.user_id, event_data={"generated": True}))
            positives += int(result.decision in ("人工审核", "拒绝"))
        return count, positives


def main() -> None:
    parser = argparse.ArgumentParser(description="生成银行风控训练评估数据")
    parser.add_argument("--count", type=int, default=1500)
    args = parser.parse_args()
    total, positives = asyncio.run(generate(args.count))
    print(f"[OK] 已生成 {total} 条银行风控评估")
    print(f"[OK] 正例 {positives} 条，占比 {positives / total:.1%}")


if __name__ == "__main__":
    main()
