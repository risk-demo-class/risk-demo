"""可重复生成物流业务数据（默认200票，含可解释风险模板）。"""
import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sqlalchemy import delete
from app.database import AsyncSessionLocal
from app.models_business import Address, CustomsDeclaration, DeliveryResult, Shipment, ShipmentItem, UserInfo

async def generate(count:int=200, seed:int=42):
    rng=random.Random(seed); now=datetime.now()
    async with AsyncSessionLocal() as db:
        for model in (DeliveryResult,CustomsDeclaration,ShipmentItem,Shipment,Address,UserInfo):
            await db.execute(delete(model))
        users=[]; addresses=[]
        for i in range(40):
            risky=i<8
            user=UserInfo(user_id=f"U{i:04d}",name=f"寄件人{i}",id_type="身份证",
                id_number_hash=f"IDHASH{i:04d}",phone=f"1380000{i:04d}",real_name_status=0 if i==0 else 1,
                account_type="个人",register_time=now-timedelta(days=2 if risky else rng.randint(30,900)),
                device_id=f"DEV{0 if risky else i:03d}",usual_city="杭州")
            users.append(user); db.add(user)
        for i in range(100):
            shared=i<5
            addr=Address(address_id=f"A{i:04d}",user_id=f"U{i%40:04d}",contact_name=f"收件人{i}",
                contact_phone=f"1390000{i:04d}",id_number_hash=f"RID{i:04d}",country="中国",province="浙江",
                city="杭州",district="余杭",detail_address=f"测试路{i}号",address_type="临时地址" if shared else "固定地址",
                is_remote_area=1 if i%29==0 else 0,create_time=now-timedelta(days=2 if shared else 100))
            addresses.append(addr); db.add(addr)
        for i in range(count):
            risky=i<count//5; uid=i%8 if risky else rng.randrange(8,40); cross=(i%5==0)
            shipment=Shipment(shipment_id=f"S{i:06d}",sender_user_id=f"U{uid:04d}",
                sender_address_id=f"A{uid:04d}",receiver_address_id=f"A{(i%5 if risky else rng.randrange(5,100)):04d}",
                shipment_type="跨境件" if cross else "普通件",payment_type="货到付款" if i%4==0 else "寄付",
                cod_amount=1200 if i%4==0 else 0,declared_value=120 if risky and cross else rng.randint(200,15000),
                actual_weight=15 if risky and cross else rng.uniform(.2,8),declared_weight=2 if risky and cross else rng.uniform(.2,8),
                destination_country="美国" if cross else "中国",is_cross_border=int(cross),
                create_time=now-timedelta(minutes=i%50) if risky else now-timedelta(days=rng.randint(1,120)),
                shipment_status="拒收" if risky and i%4==0 else "运输中",device_id=f"DEV{0 if risky else uid:03d}")
            db.add(shipment)
            danger=risky and i%3==0
            db.add(ShipmentItem(item_id=f"I{i:06d}",shipment_id=shipment.shipment_id,
                item_name="锂电池" if danger else "服装",item_category="电池" if danger else "普通商品",
                quantity=1,declared_dangerous=0,battery_flag=int(danger),chemical_flag=0,liquid_flag=0,
                security_check_result="疑似危险品" if danger else "通过"))
            if cross:
                db.add(CustomsDeclaration(declaration_id=f"D{i:06d}",shipment_id=shipment.shipment_id,
                    customs_code="TEST",declared_item_name="样品",declared_quantity=1,
                    declared_value=shipment.declared_value,declared_weight=shipment.declared_weight,currency="CNY",
                    origin_country="中国",destination_country=shipment.destination_country,
                    declaration_time=shipment.create_time+timedelta(minutes=10),inspection_result="待查验"))
            if i%4==0:
                db.add(DeliveryResult(delivery_id=f"R{i:06d}",shipment_id=shipment.shipment_id,
                    delivery_status="拒收" if risky else "已签收",receiver_name="测试收件人",
                    receiver_phone="13900000000",refuse_reason="拒付" if risky else None,
                    delivery_time=now-timedelta(days=i%30),cod_amount=shipment.cod_amount,
                    cod_received=0 if risky else 1,courier_id="C001"))
        await db.commit()
        print(f"生成完成: 用户40、地址100、运单{count}，风险运单{count//5}")

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--count",type=int,default=200); p.add_argument("--seed",type=int,default=42)
    a=p.parse_args(); asyncio.run(generate(a.count,a.seed))
