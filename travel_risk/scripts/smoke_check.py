"""
端到端冒烟验证: 真实 DB 跑风控决策流水线.
用法: python scripts/smoke_check.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas import RiskCheckRequest
from app.service.event import process_event


async def main():
    async with AsyncSessionLocal() as db:
        # 1. RISK002 大额订单 → 应触发 R002 一票否决
        row = (await db.execute(
            text("SELECT booking_id FROM booking_info WHERE user_id='RISK002' ORDER BY booking_id LIMIT 1")
        )).first()
        bid = row[0]
        resp = await process_event(db, RiskCheckRequest(
            event_type="下单", source_id=bid, user_id="RISK002",
            event_data={"booking_id": bid},
        ))
        print(f"[RISK002 下单] {bid}")
        print(f"  评分={resp.final_score} 等级={resp.risk_level} 决策={resp.decision} 命中={resp.rule_count}")
        for r in resp.triggered_rules[:5]:
            print(f"    {r.rule_id} {r.rule_name} [{r.risk_level}/{r.risk_score}] -> {r.action}")
        print(f"  message: {resp.message}")
        assert resp.decision == "拒绝", "RISK002 应被拒绝"

        # 2. U003 正常用户已完成订单 → 应通过/标记
        row2 = (await db.execute(
            text("SELECT booking_id FROM booking_info WHERE user_id='U003' AND booking_status='已完成' ORDER BY booking_id LIMIT 1")
        )).first()
        bid2 = row2[0]
        resp2 = await process_event(db, RiskCheckRequest(
            event_type="下单", source_id=bid2, user_id="U003",
            event_data={"booking_id": bid2},
        ))
        print(f"[U003 下单] {bid2}")
        print(f"  评分={resp2.final_score} 等级={resp2.risk_level} 决策={resp2.decision} 命中={resp2.rule_count}")
        for r in resp2.triggered_rules[:5]:
            print(f"    {r.rule_id} {r.rule_name} [{r.risk_level}/{r.risk_score}] -> {r.action}")
        assert resp2.decision in ("通过", "标记"), "U003 应低风险放行"

        # 3. 撞黑名单: 给 U003 加黑名单再检查 → 直接拒绝且不写评估
        from app.models import RiskBlacklist
        from sqlalchemy import select
        existing = (await db.execute(
            select(RiskBlacklist).where(
                RiskBlacklist.blacklist_type == "用户",
                RiskBlacklist.blacklist_value == "U003",
                RiskBlacklist.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if not existing:
            db.add(RiskBlacklist(blacklist_type="用户", blacklist_value="U003", reason="冒烟测试"))
            await db.commit()
        resp3 = await process_event(db, RiskCheckRequest(
            event_type="下单", source_id=bid2, user_id="U003",
            event_data={"booking_id": bid2},
        ))
        print(f"[U003 撞黑] 决策={resp3.decision} blocked_by={resp3.blocked_by}")
        assert resp3.blocked_by == "用户" and resp3.decision == "拒绝"
        # 清理测试黑名单
        await db.execute(text("DELETE FROM risk_blacklist WHERE blacklist_value='U003' AND blacklist_type='用户'"))
        await db.commit()

        print("\n冒烟验证通过 ✔ (一票否决 / 正常放行 / 撞黑拦截 三场景)")


if __name__ == "__main__":
    asyncio.run(main())
