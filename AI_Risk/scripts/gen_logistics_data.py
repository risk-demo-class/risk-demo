"""
物流行业风控系统 - 业务测试数据生成脚本
造 100+ 条物流业务数据: 用户、地址、运单、物品明细
"""
import asyncio
import os
import random
import sys
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

# 将项目根目录加入 Python 路径 (直接运行 scripts/gen_logistics_data.py 时可用)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiomysql
from app.config import settings

# 配置
USER_COUNT = 50
ADDRESS_COUNT = 100
SHIPMENT_COUNT = 150

PROVINCES = ["广东省", "北京市", "上海市", "四川省", "浙江省"]
CITIES = {
    "广东省": ["深圳市", "广州市", "东莞市"],
    "北京市": ["北京市"],
    "上海市": ["上海市"],
    "四川省": ["成都市", "绵阳市"],
    "浙江省": ["杭州市", "宁波市"],
}
DISTRICTS = ["南山区", "朝阳区", "浦东新区", "武侯区", "西湖区", "海淀区", "宝安区"]

CATEGORIES = ["电子产品", "服装", "食品", "化妆品", "生活用品", "化学品"]
SHIPMENT_TYPES = ["普快", "特快", "跨境", "代收货款"]
STATUSES = ["待揽收", "运输中", "派送中", "已签收", "异常", "已取消"]


async def clear_data(conn):
    """清理旧数据"""
    async with conn.cursor() as cur:
        await cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in ["user_info", "address", "shipment", "shipment_item", "logistics_status_update", "shipment_complaint"]:
            await cur.execute(f"TRUNCATE TABLE `{table}`")
        await cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    print("  旧业务数据已清理")


async def generate_users(conn):
    """生成用户数据"""
    users = []
    for i in range(USER_COUNT):
        user_id = f"USR_{10000 + i}"
        name = f"用户_{i}"
        phone = f"13{random.randint(0, 9)}{random.randint(10000000, 99999999)}"
        id_card = f"ID_{uuid.uuid4().hex[:18]}"
        verified = random.choice([True, False])
        age = random.randint(1, 1000)
        users.append((user_id, name, phone, id_card, verified, age))

    async with conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO user_info (user_id, name, phone, id_card_hash, real_name_verified, account_age_days) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            users
        )
    print(f"  已生成 {USER_COUNT} 个用户")
    return [u[0] for u in users]


async def generate_addresses(conn):
    """生成地址数据"""
    addresses = []
    for i in range(ADDRESS_COUNT):
        address_id = f"ADDR_{10000 + i}"
        province = random.choice(PROVINCES)
        city = random.choice(CITIES[province])
        district = random.choice(DISTRICTS)
        detail = f"某某路 {random.randint(1, 999)} 号"
        is_temp = random.random() < 0.1
        addresses.append((address_id, province, city, district, detail, is_temp))

    async with conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO address (address_id, province, city, district, detail, is_temporary) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            addresses
        )
    print(f"  已生成 {ADDRESS_COUNT} 个地址")
    return [a[0] for a in addresses]


async def generate_shipments(conn, user_ids, address_ids):
    """生成运单及明细"""
    shipments = []
    items = []
    complaints = []
    COMPLAINT_TYPES = ["物流延迟", "商品破损", "服务态度", "虚假签收"]
    
    for i in range(SHIPMENT_COUNT):
        shipment_id = f"SHIP_{20260812000 + i}"
        sender_id = random.choice(user_ids)
        receiver_name = f"收件人_{i}"
        receiver_phone = f"15{random.randint(0, 9)}{random.randint(10000000, 99999999)}"
        s_type = random.choice(SHIPMENT_TYPES)
        val = Decimal(random.uniform(10, 20000)).quantize(Decimal("0.00"))
        weight = Decimal(random.uniform(0.5, 50)).quantize(Decimal("0.00"))
        cod = val if s_type == "代收货款" else Decimal("0.00")
        
        origin = random.choice(address_ids)
        dest = random.choice(address_ids)
        while dest == origin:
            dest = random.choice(address_ids)
            
        create_time = datetime.now() - timedelta(days=random.randint(0, 30))
        status = random.choice(STATUSES)
        
        shipments.append((
            shipment_id, sender_id, receiver_name, receiver_phone, 
            s_type, val, weight, cod, origin, dest, create_time, status
        ))
        
        # 物品明细 (1-3个)
        for j in range(random.randint(1, 3)):
            item_id = f"ITEM_{shipment_id}_{j}"
            item_name = f"物品_{i}_{j}"
            cat = random.choice(CATEGORIES)
            qty = random.randint(1, 5)
            is_dang = (cat == "化学品" and random.random() < 0.3)
            items.append((item_id, shipment_id, item_name, cat, qty, is_dang))

        # 约 12% 的运单产生一条投诉 (供投诉规则 / 投诉特征使用)
        if random.random() < 0.12:
            complaints.append((
                shipment_id, sender_id,
                random.choice(COMPLAINT_TYPES),
                f"投诉: 运单 {shipment_id} 运输体验异常",
                create_time + timedelta(hours=random.randint(1, 24)),
            ))

    async with conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO shipment (shipment_id, sender_id, receiver_name, receiver_phone, "
            "shipment_type, declared_value, actual_weight, cod_amount, origin_address_id, "
            "dest_address_id, create_time, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            shipments
        )
        await cur.executemany(
            "INSERT INTO shipment_item (item_id, shipment_id, item_name, item_category, quantity, is_dangerous) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            items
        )
        if complaints:
            await cur.executemany(
                "INSERT INTO shipment_complaint (shipment_id, user_id, complaint_type, content, create_time) "
                "VALUES (%s, %s, %s, %s, %s)",
                complaints
            )
    print(f"  已生成 {SHIPMENT_COUNT} 张运单及明细")


async def main():
    print("=" * 60)
    print("物流行业 - 业务测试数据生成")
    print("=" * 60)
    
    conn = await aiomysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_NAME,
        charset="utf8mb4",
        autocommit=True,
    )
    
    try:
        await clear_data(conn)
        user_ids = await generate_users(conn)
        address_ids = await generate_addresses(conn)
        await generate_shipments(conn, user_ids, address_ids)
        print("\n数据生成完成!")
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(main())
