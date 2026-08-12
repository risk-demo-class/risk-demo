"""从物流业务表生成风控评估、特征快照和案件。"""
import argparse, asyncio, random, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models_business import CustomsDeclaration, DeliveryResult, Shipment
from app.schemas import RiskCheckRequest
from app.service.event import process_event

async def generate(count:int=60, seed:int=42):
    rng=random.Random(seed)
    async with AsyncSessionLocal() as db:
        shipments=(await db.execute(select(Shipment))).scalars().all()
        declarations=(await db.execute(select(CustomsDeclaration))).scalars().all()
        deliveries=(await db.execute(select(DeliveryResult))).scalars().all()
        if not shipments:
            raise RuntimeError("没有物流业务数据，请先运行 scripts/gen_business_data.py")
        plans=[]
        for s in shipments:
            plans.append(("安检申报" if s.shipment_id.endswith("0") else "寄件下单",s.shipment_id,s.sender_user_id))
            if s.payment_type=="货到付款": plans.append(("代收货款结算",s.shipment_id,s.sender_user_id))
        by_ship={s.shipment_id:s for s in shipments}
        for d in declarations:
            s=by_ship.get(d.shipment_id)
            if s: plans.append(("跨境申报",d.declaration_id,s.sender_user_id))
        for d in deliveries:
            s=by_ship.get(d.shipment_id)
            if s: plans.append(("签收处理",d.delivery_id,s.sender_user_id))
        rng.shuffle(plans); ok=failed=0
        for event_type,source_id,user_id in plans[:count]:
            try:
                result=await process_event(db,RiskCheckRequest(event_type=event_type,source_id=source_id,user_id=user_id,event_data={"generator":"logistics"}))
                await db.commit(); ok+=1
                print(f"[{ok}] {event_type} {source_id}: {result.decision} score={result.final_score}")
            except Exception as exc:
                await db.rollback(); failed+=1; print(f"[失败] {event_type} {source_id}: {exc}")
        print(f"完成: 成功{ok}, 失败{failed}")

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--count",type=int,default=60); p.add_argument("--seed",type=int,default=42)
    a=p.parse_args(); asyncio.run(generate(a.count,a.seed))
