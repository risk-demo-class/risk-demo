"""
物流风控系统 - 高风险寄件人样本生成 (RISK001-RISK005)

5 种高风险画像:
  RISK001 危险品瞒报   (含电池/化学品但未如实申报)
  RISK002 高频寄件     (近 7 天 14 单)
  RISK003 代收拒收     (10 单 COD 中 6 单拒收)
  RISK004 多地址夜猫子 (5 个地址 + 凌晨寄件 + 跨省)
  RISK005 跨境虚报     (申报价值 <= 100 但重量 >= 5kg)

用法:
  python scripts/gen_risky_users.py            # 全量生成 (含其运单/物品)
  python scripts/gen_risky_users.py --count 30 # 兼容参数 (本脚本固定 5 个画像)
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import Address, Shipment, ShipmentItem, UserInfo  # noqa: E402
from scripts.gen_business_data import build_dataset  # noqa: E402


async def insert_risk_users() -> None:
    users, addresses, shipments, items, _ = build_dataset(seed=42)

    risk_uids = {u["user_id"] for u in users if u["user_id"].startswith("RISK")}
    risk_users = [u for u in users if u["user_id"] in risk_uids]
    risk_addr = [a for a in addresses if a["user_id"] in risk_uids]
    risk_ship = [s for s in shipments if s["user_id"] in risk_uids]
    risk_items = [it for it in items if it["shipment_id"] in {s["shipment_id"] for s in risk_ship}]

    async with AsyncSessionLocal() as db:
        # 先清掉旧 RISK 用户数据再插入 (幂等)
        risk_ship_ids = select(Shipment.shipment_id).where(Shipment.user_id.like("RISK%"))
        await db.execute(delete(ShipmentItem).where(ShipmentItem.shipment_id.in_(risk_ship_ids)))
        await db.execute(delete(Shipment).where(Shipment.user_id.like("RISK%")))
        await db.execute(delete(Address).where(Address.user_id.like("RISK%")))
        await db.execute(delete(UserInfo).where(UserInfo.user_id.like("RISK%")))
        db.add_all([UserInfo(**u) for u in risk_users])
        db.add_all([Address(**a) for a in risk_addr])
        db.add_all([Shipment(**s) for s in risk_ship])
        db.add_all([ShipmentItem(**it) for it in risk_items])
        await db.commit()

    print("=" * 60)
    print("高风险寄件人样本已生成:")
    print("  RISK001 危险品瞒报   (8 单, 含电池/化学品未申报)")
    print("  RISK002 高频寄件     (近 7 天 14 单)")
    print("  RISK003 代收拒收     (10 单 COD, 6 单拒收)")
    print("  RISK004 多地址夜猫子 (5 地址 + 凌晨 + 跨省)")
    print("  RISK005 跨境虚报     (低申报 + 高重量)")
    print(f"  用户 {len(risk_users)} / 地址 {len(risk_addr)} / 运单 {len(risk_ship)} / 物品 {len(risk_items)}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="物流风控 - 高风险寄件人样本")
    parser.add_argument("--count", type=int, default=30,
                        help="兼容参数 (本脚本固定 5 个高风险画像)")
    args = parser.parse_args()
    asyncio.run(insert_risk_users())


if __name__ == "__main__":
    main()
