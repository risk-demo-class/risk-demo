"""
制造业风控系统 - 一键验收脚本
跑 6 类高风险场景 + 2 类黑名单拦截 + 1 个正常场景, 打印决策结果.

用法:
  python scripts/verify_mfg.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.database import AsyncSessionLocal, async_engine
from app.schemas import RiskCheckRequest
from app.service.event import process_event


CASES = [
    ("高频订货 R007", "经销商订货", "ORD_RISK002_00", "RISK002", None),
    ("串货举报 R001", "串货举报", "1", "D004", None),
    ("套保 R008+R018", "售后维修", "W_RISK003_02", "RISK003", None),
    ("出保高频保修 R002", "保修申请", "W0023", "D010", None),
    ("资质过期 R025", "经销商订货", "ORD0001", "D001", None),
    ("黑经销商拦截", "经销商订货", "ORD0013", "D008", None),
    ("黑设备SN拦截", "售后维修", "W0021", "D010", None),
    ("新经销商大单 R012", "经销商订货", "ORD_RISK005_01", "RISK005", None),
    ("大额采购 R003", "采购订单", "ORD0031", "D002", None),
    ("正常订货(对照)", "经销商订货", "ORD0004", "D002", None),
]


async def run(label: str, event_type: str, source_id: str, user_id: str, order_id: str | None):
    async with AsyncSessionLocal() as db:
        try:
            req = RiskCheckRequest(
                event_type=event_type, source_id=source_id, user_id=user_id, order_id=order_id,
            )
            r = await process_event(db, req)
            print(f"[{label}] {event_type} user={user_id} src={source_id}")
            print(f"   score={r.final_score} level={r.risk_level} decision={r.decision} "
                  f"rules={r.rule_count} blocked_by={r.blocked_by}")
            for h in r.triggered_rules[:4]:
                print(f"     - {h.rule_id} {h.rule_name} ({h.risk_level}/{h.risk_score})")
        except Exception as e:
            await db.rollback()
            print(f"[{label}] FAIL: {e}")


async def main():
    print("=" * 60)
    print("制造业风控系统 - 一键验收 (6 高风险 + 2 黑名单 + 1 正常)")
    print("=" * 60)
    for label, et, sid, uid, oid in CASES:
        await run(label, et, sid, uid, oid)
        print()
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
