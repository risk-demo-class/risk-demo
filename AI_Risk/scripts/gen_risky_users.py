"""
物流行业风控系统 - 生成有风险行为的用户测试数据 (异步).
【P4-L3 2026-08-08 第二轮】支持 --count 指定生成用户数 (默认 5).

5 种风险模式轮换生成 (跟 5 个 RISK 用户一一对应):
  模式 1: 高退款率  -> 高取消率 (10 张运单, 9 张已取消)
  模式 2: 高频下单  -> 高频寄件 (30 天 20+ 张运单)
  模式 3: 高退款金额-> 高申报价值 (3 张大额运单)
  模式 4: 多地址    -> 多地址 (7 个目的地址)
  模式 5: 有投诉    -> 有投诉 (2 张运单 + 2 条投诉)

示例:
  python scripts/gen_risky_users.py                # 默认 5 个 (RISK001-005)
  python scripts/gen_risky_users.py --count 30     # 30 个 (RISK001-030, 6 套 × 5 模式)
  python scripts/gen_risky_users.py --count 1      # 只 1 个 (RISK001, 高取消率模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 数据再生成
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


# 5 种风险模式 (模式名 用户前缀数字起点)
RISK_MODES = ["高退款率", "高频下单", "高退款金额", "多地址", "有投诉"]


async def _gen_high_refund_user(conn, user_id: str):
    """模式 1: 高取消率用户 (10 张运单, 9 张已取消)"""
    for i in range(1, 11):
        day_offset = max(1, 30 - i * 3)
        status = "已取消" if i < 10 else "已签收"
        await conn.execute(text("""
            INSERT INTO shipment (shipment_id, sender_id, receiver_name, receiver_phone,
            shipment_type, declared_value, actual_weight, cod_amount,
            origin_address_id, dest_address_id, create_time, status)
            VALUES (:sid, :uid, '张三', '13800138000', '普快',
            :val, 1.00, 0.00, 'ADDR_10000', 'ADDR_10001',
            DATE_SUB(NOW(), INTERVAL :d DAY), :status)
        """), {"sid": f"SHIP_{user_id}_{i:02d}", "uid": user_id,
               "val": 1000, "d": day_offset, "status": status})
        await conn.execute(text("""
            INSERT INTO shipment_item (item_id, shipment_id, item_name, item_category, quantity, is_dangerous)
            VALUES (:iid, :sid, '测试物品', '电子产品', 1, 0)
        """), {"iid": f"ITEM_{user_id}_{i:02d}", "sid": f"SHIP_{user_id}_{i:02d}"})


async def _gen_high_freq_user(conn, user_id: str):
    """模式 2: 高频寄件用户 (25 张运单, 30 天内)"""
    base_date = datetime.now() - timedelta(days=25)
    for i in range(25):
        order_dt = base_date + timedelta(days=i % 25)
        await conn.execute(text("""
            INSERT INTO shipment (shipment_id, sender_id, receiver_name, receiver_phone,
            shipment_type, declared_value, actual_weight, cod_amount,
            origin_address_id, dest_address_id, create_time, status)
            VALUES (:sid, :uid, '李四', '13800138002', '特快',
            :val, 1.00, 0.00, 'ADDR_10000', 'ADDR_10002', :dt, '已签收')
        """), {"sid": f"SHIP_{user_id}_{i:02d}", "uid": user_id,
               "val": 500, "dt": order_dt})
        await conn.execute(text("""
            INSERT INTO shipment_item (item_id, shipment_id, item_name, item_category, quantity, is_dangerous)
            VALUES (:iid, :sid, '测试物品', '服装', 1, 0)
        """), {"iid": f"ITEM_{user_id}_{i:02d}", "sid": f"SHIP_{user_id}_{i:02d}"})


async def _gen_high_amount_user(conn, user_id: str):
    """模式 3: 高申报价值用户 (3 张大额运单)"""
    for i, (day, val) in enumerate([(15, 8000), (10, 12000), (5, 18000)], 1):
        await conn.execute(text("""
            INSERT INTO shipment (shipment_id, sender_id, receiver_name, receiver_phone,
            shipment_type, declared_value, actual_weight, cod_amount,
            origin_address_id, dest_address_id, create_time, status)
            VALUES (:sid, :uid, '王五', '13800138003', '跨境',
            :val, 5.00, 0.00, 'ADDR_10000', 'ADDR_10003',
            DATE_SUB(NOW(), INTERVAL :d DAY), '已签收')
        """), {"sid": f"SHIP_{user_id}_{i:02d}", "uid": user_id,
               "val": val, "d": day})
        await conn.execute(text("""
            INSERT INTO shipment_item (item_id, shipment_id, item_name, item_category, quantity, is_dangerous)
            VALUES (:iid, :sid, '大额物品', '电子产品', 1, 0)
        """), {"iid": f"ITEM_{user_id}_{i:02d}", "sid": f"SHIP_{user_id}_{i:02d}"})


async def _gen_multi_addr_user(conn, user_id: str):
    """模式 4: 多地址用户 (7 个目的地址)"""
    provinces = ["北京", "上海", "广东", "浙江", "江苏", "四川", "湖北"]
    cities = ["北京市", "上海市", "广州市", "杭州市", "南京市", "成都市", "武汉市"]
    districts = ["朝阳区", "浦东新区", "天河区", "西湖区", "鼓楼区", "锦江区", "武昌区"]
    for i, prov in enumerate(provinces):
        addr_id = f"ADDR_RISK_{user_id}_{i}"
        await conn.execute(text("""
            INSERT INTO address (address_id, province, city, district, detail, is_temporary)
            VALUES (:aid, :prov, :city, :dist, :detail, 0)
        """), {"aid": addr_id, "prov": prov, "city": cities[i],
               "dist": districts[i], "detail": f"测试地址{i}号"})
        await conn.execute(text("""
            INSERT INTO shipment (shipment_id, sender_id, receiver_name, receiver_phone,
            shipment_type, declared_value, actual_weight, cod_amount,
            origin_address_id, dest_address_id, create_time, status)
            VALUES (:sid, :uid, :name, :phone, '普快',
            500, 1.00, 0.00, 'ADDR_10000', :aid,
            DATE_SUB(NOW(), INTERVAL :d DAY), '已签收')
        """), {"sid": f"SHIP_{user_id}_{i:02d}", "uid": user_id,
               "name": f"收件人{i}", "phone": f"1390013900{i}",
               "aid": addr_id, "d": 30 - i * 3})
        await conn.execute(text("""
            INSERT INTO shipment_item (item_id, shipment_id, item_name, item_category, quantity, is_dangerous)
            VALUES (:iid, :sid, '测试物品', '生活用品', 1, 0)
        """), {"iid": f"ITEM_{user_id}_{i:02d}", "sid": f"SHIP_{user_id}_{i:02d}"})


async def _gen_complaint_user(conn, user_id: str):
    """模式 5: 有投诉用户 (2 张运单 + 2 条投诉)"""
    for i, day in enumerate([10, 7], 1):
        await conn.execute(text("""
            INSERT INTO shipment (shipment_id, sender_id, receiver_name, receiver_phone,
            shipment_type, declared_value, actual_weight, cod_amount,
            origin_address_id, dest_address_id, create_time, status)
            VALUES (:sid, :uid, '赵六', '13800138005', '普快',
            800, 1.00, 0.00, 'ADDR_10000', 'ADDR_10004',
            DATE_SUB(NOW(), INTERVAL :d DAY), '已签收')
        """), {"sid": f"SHIP_{user_id}_{i:02d}", "uid": user_id, "d": day})
        await conn.execute(text("""
            INSERT INTO shipment_item (item_id, shipment_id, item_name, item_category, quantity, is_dangerous)
            VALUES (:iid, :sid, '测试物品', '食品', 1, 0)
        """), {"iid": f"ITEM_{user_id}_{i:02d}", "sid": f"SHIP_{user_id}_{i:02d}"})
        await conn.execute(text("""
            INSERT INTO shipment_complaint (shipment_id, user_id, complaint_type, content, create_time)
            VALUES (:sid, :uid, '物流延迟', '运输延迟投诉', DATE_SUB(NOW(), INTERVAL :d DAY))
        """), {"sid": f"SHIP_{user_id}_{i:02d}", "uid": user_id, "d": max(1, day - 1)})


# 5 种模式生成器
MODE_GENERATORS = [
    _gen_high_refund_user,    # 模式 0: 高退款率 (高取消率)
    _gen_high_freq_user,      # 模式 1: 高频下单 (高频寄件)
    _gen_high_amount_user,    # 模式 2: 高退款金额 (高申报价值)
    _gen_multi_addr_user,     # 模式 3: 多地址
    _gen_complaint_user,      # 模式 4: 有投诉
]


async def gen_risky_users(count: int = 5, reset: bool = False):
    """生成 N 个 RISK 高风险用户 (5 种模式轮换).

    Args:
        count: 生成用户数 (默认 5). 例: count=30 -> RISK001-RISK030 (6 套 × 5 模式).
        reset: 是否先删除 RISK 用户 + 关联数据 (默认 False, 用 INSERT 增量插入).
    """
    if count < 1:
        raise ValueError(f"--count 必须 >= 1, 当前 {count}")

    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        if reset:
            print("[reset] 删除旧 RISK 用户 + 关联数据...")
            delete_rules = [
                ("shipment_complaint", "user_id"),
                ("shipment_item", "shipment_id"),
                ("shipment", "sender_id"),
                ("address", "address_id"),
                ("user_info", "user_id"),
            ]
            for tbl, col in delete_rules:
                like_value = f"RISK%" if col in ("user_id", "sender_id") else f"SHIP_RISK%"
                if col == "address_id":
                    like_value = f"ADDR_RISK%"
                await conn.execute(text(f"DELETE FROM {tbl} WHERE {col} LIKE :pat"), {"pat": like_value})
            print("  清理完成")

        # 生成 N 个 RISK 用户 (5 种模式轮换)
        print(f"[generate] 生成 {count} 个 RISK 高风险用户 (5 模式轮换)...")
        user_ids = [f"RISK{i:03d}" for i in range(1, count + 1)]
        for idx, user_id in enumerate(user_ids):
            mode_idx = idx % 5
            mode_name = RISK_MODES[mode_idx]
            print(f"  [{idx+1}/{count}] {user_id} (模式 {mode_idx+1}: {mode_name})")
            await conn.execute(text("""
                INSERT INTO user_info (user_id, name, phone, id_card_hash, real_name_verified, account_age_days)
                VALUES (:uid, :name, :phone, :hash, :verified, :age)
            """), {"uid": user_id, "name": f"风险用户{idx+1}",
                   "phone": f"1380000{mode_idx}{idx:03d}",
                   "hash": f"ID_{user_id}", "verified": 0,
                   "age": random_age(idx)})
            await MODE_GENERATORS[mode_idx](conn, user_id)

        await conn.commit()

        # 统计
        r = await conn.execute(text("SELECT COUNT(*) FROM user_info WHERE user_id LIKE 'RISK%'"))
        total_users = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM shipment WHERE sender_id LIKE 'RISK%'"))
        total_shipments = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM shipment_complaint WHERE user_id LIKE 'RISK%'"))
        total_complaints = r.scalar()

        print(f"\n[完成] 高风险用户数据生成完成")
        print(f"  RISK 用户:     {total_users} 个")
        print(f"  RISK 运单:     {total_shipments} 张")
        print(f"  RISK 投诉:     {total_complaints} 条")

    await engine.dispose()


def random_age(idx: int) -> int:
    """账号年龄 (天): 新号偏多, 供实名风险规则参考."""
    return max(1, 30 - idx)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="生成 RISK 高风险用户 + 运单/投诉. 默认 5 个, --count 指定数量.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/gen_risky_users.py                # 5 个 (RISK001-005, 一套)
  python scripts/gen_risky_users.py --count 30     # 30 个 (RISK001-030, 6 套 × 5 模式)
  python scripts/gen_risky_users.py --count 1      # 1 个 (RISK001, 高取消率模式)
  python scripts/gen_risky_users.py --reset        # 先删除 RISK 数据再生成
        """,
    )
    parser.add_argument("--count", type=int, default=5, help="生成 RISK 用户数 (默认 5)")
    parser.add_argument("--reset", action="store_true", help="先删除 RISK 用户 + 关联数据")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))
