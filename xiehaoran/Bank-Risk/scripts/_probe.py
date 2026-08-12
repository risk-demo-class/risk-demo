import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.engine.decision import run_risk_check

req = RiskCheckRequest(
    event_type="transfer", source_id="T999", user_id="C200001",
    event_data={"amount": 260000, "counterparty_acct_cnt": 12, "geo_deviation": 1,
                "txn_time": "2026-05-03 03:20:00"},
)

async def main():
    async with AsyncSessionLocal() as db:
        r = await run_risk_check(db, req)
        print("DECISION", r.decision, "SCORE", r.final_score, "RULES", r.rule_count)

asyncio.run(main())
