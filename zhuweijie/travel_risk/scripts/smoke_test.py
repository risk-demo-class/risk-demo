"""端到端冒烟测试: 真实跑一次风控检查 (任务2验收辅助)"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event


async def main():
    async with AsyncSessionLocal() as db:
        req = RiskCheckRequest(
            event_type="机票预订",
            source_id="O101",
            user_id="U001",
            event_data={"device_id": "DEV-001"},
        )
        resp = await process_event(db, req)
        print("=== 风控检查结果 (U001 / O101 黄牛囤票样本) ===")
        print("final_score :", resp.final_score)
        print("risk_level  :", resp.risk_level)
        print("decision    :", resp.decision)
        print("rule_count  :", resp.rule_count)
        print("triggered   :", [(r.rule_id, r.rule_name, r.risk_level) for r in resp.triggered_rules])
        print("ml_score    :", resp.ml_score, "| ml_decision:", resp.ml_decision)
        print("features 数 :", len(resp.features))
        print("event_id    :", resp.event_id, "| assessment_id:", resp.assessment_id)

        req2 = RiskCheckRequest(event_type="酒店预订", source_id="O201", user_id="U010")
        resp2 = await process_event(db, req2)
        print("\n=== 风控检查结果 (U010 / O201 对照) ===")
        print("decision:", resp2.decision, "| score:", resp2.final_score,
              "| rules:", [(r.rule_id, r.rule_name) for r in resp2.triggered_rules])


if __name__ == "__main__":
    asyncio.run(main())