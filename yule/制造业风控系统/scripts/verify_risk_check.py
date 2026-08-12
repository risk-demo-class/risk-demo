"""
制造业风控系统 - 风险检查链路冒烟验证脚本
对 3 种业务事件各跑 1 次真实风控检查, 打印评分/等级/决策/命中规则/特征.

用法:
  python scripts/verify_risk_check.py
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
        # 1. 经销商订货: 优先找大额囤货单 (quantity > 100)
        r = await db.execute(text(
            "SELECT order_id, dealer_id FROM order_info WHERE quantity > 100 LIMIT 1"
        ))
        row = r.first()
        if row:
            req = RiskCheckRequest(
                event_type="经销商订货", source_id=row.order_id,
                user_id=row.dealer_id, order_id=row.order_id,
            )
            res = await process_event(db, req)
            print("== 经销商订货 (大额囤货样本) ==")
            print(f"  user={res.user_id} score={res.final_score} level={res.risk_level} decision={res.decision}")
            print(f"  命中规则: {[(h.rule_id, h.rule_name) for h in res.triggered_rules]}")
            print(f"  特征: order_quantity={res.features.get('order_quantity')} "
                  f"order_total_amount={res.features.get('order_total_amount')} "
                  f"user_total_orders={res.features.get('user_total_orders')}")

        # 2. 设备保修: 套保样本 (同 SN 近 90 天 >= 2 次)
        r = await db.execute(text(
            "SELECT w.warranty_id, oi.dealer_id, w.product_sn "
            "FROM warranty_record w JOIN order_info oi ON w.order_id = oi.order_id "
            "WHERE oi.dealer_id LIKE 'RISK%' LIMIT 1"
        ))
        row = r.first()
        if row:
            req = RiskCheckRequest(
                event_type="设备保修", source_id=row.warranty_id,
                user_id=row.dealer_id,
                event_data={"product_sn": row.product_sn},
            )
            res = await process_event(db, req)
            print("\n== 设备保修 (RISK 样本) ==")
            print(f"  user={res.user_id} score={res.final_score} level={res.risk_level} decision={res.decision}")
            print(f"  命中规则: {[(h.rule_id, h.rule_name) for h in res.triggered_rules]}")
            print(f"  特征: order_warranty_90d={res.features.get('order_warranty_90d')} "
                  f"user_warranty_count={res.features.get('user_warranty_count')}")

        # 3. 跨区串货举报: RISK 经销商举报样本
        r = await db.execute(text(
            "SELECT report_id, dealer_id FROM cross_region_report "
            "WHERE dealer_id LIKE 'RISK%' LIMIT 1"
        ))
        row = r.first()
        if row:
            req = RiskCheckRequest(
                event_type="跨区串货举报", source_id=row.report_id, user_id=row.dealer_id,
            )
            res = await process_event(db, req)
            print("\n== 跨区串货举报 (RISK 样本) ==")
            print(f"  user={res.user_id} score={res.final_score} level={res.risk_level} decision={res.decision}")
            print(f"  命中规则: {[(h.rule_id, h.rule_name) for h in res.triggered_rules]}")
            print(f"  特征: user_cross_report_count={res.features.get('user_cross_report_count')}")


if __name__ == "__main__":
    asyncio.run(main())
