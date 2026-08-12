"""
制造业风控系统 - 生成有风险行为的经销商测试数据 (异步).
【P4-L3 2026-08-08 第二轮】支持 --count 指定生成经销商数 (默认 5).

8 种制造业风险模式轮换生成 (跟 8 条核心规则一一对应):
  模式 1: 跨区串货被举报 (2-3 张订单各被举报 2+ 次 → R001/R030)
  模式 2: 保修期外高频保修 (已过保修 + 30 天同 SN 保修 2 次 → R002)
  模式 3: 大额经销商囤货 (单笔订货 110-130 台 → R005)
  模式 4: 套保嫌疑 (同 SN 90 天 2 次保修 → R008)
  模式 5: 新经销商大单 (签约<30 天 + 首单 60-90 台 → R012)
  模式 6: 维修费用异常 (单次维修费 > MSRP 60% → R018)
  模式 7: 资质过期仍订货 (合同到期 + 新订单 → R025)
  模式 8: 黑经销商 (dealer 进 risk_blacklist, 前置拦截)

例:
  python scripts/gen_risky_users.py                # 默认 8 个 (RISK001-008)
  python scripts/gen_risky_users.py --count 16     # 16 个 (2 套 × 8 模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 经销商再生成
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


RISK_MODES = [
    "跨区串货举报", "保修期外高频保修", "大额囤货", "套保嫌疑",
    "新经销商大单", "维修费用异常", "资质过期", "黑经销商",
]

PRODUCTS = [
    ("P001", "数控机床", "CNC-500", 680000, 24),
    ("P002", "注塑机", "IM-260", 520000, 18),
    ("P003", "螺杆空压机", "AC-75", 138000, 24),
    ("P005", "工业机械臂", "RB-6", 180000, 12),
    ("P009", "数控车床", "LC-360", 420000, 24),
]
REGIONS = ["广东", "江苏", "浙江", "山东", "上海", "北京", "福建", "安徽"]
TECHNICIANS = [f"T{str(i).zfill(3)}" for i in range(1, 11)]


async def _insert_user_dealer(conn, user_id: str, region: str, contract_start, contract_end):
    await conn.execute(text("""
        INSERT IGNORE INTO user_info (user_id, name, role, dealer_level, region, register_at)
        VALUES (:uid, :name, '经销商', '普通经销商', :region, :register_at)
    """), {"uid": user_id, "name": f"风险经销商{user_id[4:]}", "region": region,
           "register_at": contract_start})
    await conn.execute(text("""
        INSERT IGNORE INTO dealer_info (dealer_id, dealer_name, region, authorized_brands,
        contract_start, contract_end)
        VALUES (:did, :name, :region, '精工机械,恒力制造', :cs, :ce)
    """), {"did": user_id, "name": f"{region}风险机械{user_id[4:]}", "region": region,
           "cs": contract_start, "ce": contract_end})


async def _insert_order(conn, user_id: str, idx: int, product, quantity, ship_region,
                        create_time, unit_price=None):
    pid, pname, pmodel, msrp, _ = product
    price = unit_price or msrp * 0.9
    total = price * quantity
    oid = f"ORD_{user_id[4:]}_{idx:03d}"
    await conn.execute(text("""
        INSERT IGNORE INTO order_info (order_id, dealer_id, product_id, quantity,
        unit_price, total_amount, ship_to_region, create_time)
        VALUES (:oid, :uid, :pid, :qty, :price, :total, :region, :ct)
    """), {"oid": oid, "uid": user_id, "pid": pid, "qty": quantity,
           "price": price, "total": total, "region": ship_region, "ct": create_time})
    return oid


async def _insert_warranty(conn, warranty_id: str, sn: str, order_id: str,
                           issue_date, repair_cost, issue_type="质量问题",
                           technician_id="T001"):
    await conn.execute(text("""
        INSERT IGNORE INTO warranty_record (warranty_id, product_sn, order_id, issue_date,
        issue_type, repair_cost, technician_id, create_time)
        VALUES (:wid, :sn, :oid, :idate, :itype, :cost, :tid, :idate)
    """), {"wid": warranty_id, "sn": sn, "oid": order_id, "idate": issue_date,
           "itype": issue_type, "cost": repair_cost, "tid": technician_id})


async def _insert_report(conn, report_id: str, order_id: str, dealer_id: str,
                         ship_region: str, dealer_region: str, create_time):
    await conn.execute(text("""
        INSERT IGNORE INTO cross_region_report (report_id, order_id, dealer_id,
        ship_to_region, dealer_region, reporter_id, create_time)
        VALUES (:rid, :oid, :did, :sr, :dr, 'E001', :ct)
    """), {"rid": report_id, "oid": order_id, "did": dealer_id,
           "sr": ship_region, "dr": dealer_region, "ct": create_time})


# ============================================================
# 8 种风险模式生成器
# ============================================================

async def _gen_cross_region(conn, user_id: str):
    """模式 1: 跨区串货被举报 (3 张跨区订单各被举报 2 次)"""
    region = REGIONS[0]
    cs = datetime.now() - timedelta(days=200)
    await _insert_user_dealer(conn, user_id, region, cs, cs + timedelta(days=365))
    for i in range(3):
        oid = await _insert_order(
            conn, user_id, i + 1, PRODUCTS[1], 8, REGIONS[1],
            datetime.now() - timedelta(days=30 - i * 5),
        )
        for k in range(2):
            await _insert_report(
                conn, f"CR_{oid}_{k}", oid, user_id, REGIONS[1], region,
                datetime.now() - timedelta(days=28 - i * 5 + k),
            )


async def _gen_out_warranty(conn, user_id: str):
    """模式 2: 保修期外高频保修 (设备过保 + 近 30 天同 SN 保修 2 次)"""
    region = REGIONS[1]
    cs = datetime.now() - timedelta(days=500)
    await _insert_user_dealer(conn, user_id, region, cs, cs + timedelta(days=365))
    old_order_date = datetime.now() - timedelta(days=400)   # 已过保修期 (24 个月)
    oid = await _insert_order(conn, user_id, 1, PRODUCTS[0], 2, region, old_order_date)
    for i in range(2):
        await _insert_warranty(
            conn, f"WR_{user_id[4:]}_{i+1:02d}", f"SNOW{user_id[4:]}", oid,
            datetime.now() - timedelta(days=10 - i * 3),
            repair_cost=20000,
        )


async def _gen_bulk_order(conn, user_id: str):
    """模式 3: 大额经销商囤货 (单笔订货 110-130 台)"""
    region = REGIONS[2]
    cs = datetime.now() - timedelta(days=150)
    await _insert_user_dealer(conn, user_id, region, cs, cs + timedelta(days=365))
    await _insert_order(
        conn, user_id, 1, PRODUCTS[4], 120, region,
        datetime.now() - timedelta(days=3),
    )
    await _insert_order(
        conn, user_id, 2, PRODUCTS[4], 10, region,
        datetime.now() - timedelta(days=10),
    )


async def _gen_warranty_abuse(conn, user_id: str):
    """模式 4: 套保嫌疑 (同 SN 90 天内 2 次保修)"""
    region = REGIONS[3]
    cs = datetime.now() - timedelta(days=100)
    await _insert_user_dealer(conn, user_id, region, cs, cs + timedelta(days=365))
    oid = await _insert_order(
        conn, user_id, 1, PRODUCTS[2], 3, region,
        datetime.now() - timedelta(days=80),
    )
    for i in range(2):
        await _insert_warranty(
            conn, f"WR_{user_id[4:]}_{i+1:02d}", f"SNAB{user_id[4:]}", oid,
            datetime.now() - timedelta(days=60 - i * 20),
            repair_cost=8000,
        )


async def _gen_new_dealer(conn, user_id: str):
    """模式 5: 新经销商大单 (签约<30 天 + 首单 60-90 台)"""
    region = REGIONS[4]
    cs = datetime.now() - timedelta(days=10)
    await _insert_user_dealer(conn, user_id, region, cs, cs + timedelta(days=365))
    await _insert_order(
        conn, user_id, 1, PRODUCTS[3], 70, region,
        datetime.now() - timedelta(days=2),
    )


async def _gen_repair_cost(conn, user_id: str):
    """模式 6: 维修费用异常 (单次维修费 > MSRP 60%)"""
    region = REGIONS[5]
    cs = datetime.now() - timedelta(days=300)
    await _insert_user_dealer(conn, user_id, region, cs, cs + timedelta(days=365))
    oid = await _insert_order(
        conn, user_id, 1, PRODUCTS[0], 2, region,
        datetime.now() - timedelta(days=30),
    )
    await _insert_warranty(
        conn, f"WR_{user_id[4:]}_01", f"SNRC{user_id[4:]}", oid,
        datetime.now() - timedelta(days=5),
        repair_cost=450000,      # > 68万 MSRP 的 60%
        technician_id="T007",
    )


async def _gen_contract_expired(conn, user_id: str):
    """模式 7: 资质过期仍订货 (合同到期 + 新订单)"""
    region = REGIONS[6]
    cs = datetime.now() - timedelta(days=400)
    await _insert_user_dealer(conn, user_id, region, cs, cs + timedelta(days=365))  # 35 天前已到期
    await _insert_order(
        conn, user_id, 1, PRODUCTS[3], 20, region,
        datetime.now() - timedelta(days=1),
    )


async def _gen_black_dealer(conn, user_id: str):
    """模式 8: 黑经销商 (dealer 进 risk_blacklist, 前置拦截)"""
    region = REGIONS[7]
    cs = datetime.now() - timedelta(days=120)
    await _insert_user_dealer(conn, user_id, region, cs, cs + timedelta(days=365))
    await _insert_order(
        conn, user_id, 1, PRODUCTS[1], 5, region,
        datetime.now() - timedelta(days=1),
    )
    await conn.execute(text("""
        INSERT IGNORE INTO risk_blacklist (blacklist_type, blacklist_value, reason)
        VALUES ('经销商', :did, '黑名单经销商拦截 (演示)')
    """), {"did": user_id})


MODE_GENERATORS = [
    _gen_cross_region,      # 模式 0
    _gen_out_warranty,      # 模式 1
    _gen_bulk_order,        # 模式 2
    _gen_warranty_abuse,    # 模式 3
    _gen_new_dealer,        # 模式 4
    _gen_repair_cost,       # 模式 5
    _gen_contract_expired,  # 模式 6
    _gen_black_dealer,      # 模式 7
]


async def gen_risky_users(count: int = 8, reset: bool = False):
    """生成 N 个 RISK 高风险经销商 (8 种模式轮换)."""
    if count < 1:
        raise ValueError(f"--count 必须 >= 1, 当前 {count}")

    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        if reset:
            print("[reset] 删旧 RISK 经销商 + 关联数据...")
            for tbl in ("cross_region_report", "warranty_record", "order_info",
                        "dealer_info", "user_info"):
                await conn.execute(text(
                    f"DELETE FROM {tbl} WHERE dealer_id LIKE 'RISK%' OR user_id LIKE 'RISK%'"
                ))
            await conn.execute(text(
                "DELETE FROM risk_blacklist WHERE blacklist_value LIKE 'RISK%' AND blacklist_type='经销商'"
            ))
            print("  清理完成")

        print(f"[generate] 生成 {count} 个 RISK 高风险经销商 (8 模式轮换)...")
        user_ids = [f"RISK{i:03d}" for i in range(1, count + 1)]
        for idx, user_id in enumerate(user_ids):
            mode_idx = idx % len(MODE_GENERATORS)
            mode_name = RISK_MODES[mode_idx]
            print(f"  [{idx+1}/{count}] {user_id} (模式 {mode_idx+1}: {mode_name})")
            await MODE_GENERATORS[mode_idx](conn, user_id)

        await conn.commit()

        r = await conn.execute(text("SELECT COUNT(*) FROM dealer_info WHERE dealer_id LIKE 'RISK%'"))
        total_dealers = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM order_info WHERE dealer_id LIKE 'RISK%'"))
        total_orders = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM warranty_record w JOIN order_info oi ON w.order_id=oi.order_id WHERE oi.dealer_id LIKE 'RISK%'"))
        total_warranty = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM cross_region_report WHERE dealer_id LIKE 'RISK%'"))
        total_reports = r.scalar()

        print(f"\n[完成] 高风险经销商数据生成完成!")
        print(f"  RISK 经销商:  {total_dealers} 家")
        print(f"  RISK 订单:    {total_orders} 张")
        print(f"  RISK 保修:    {total_warranty} 条")
        print(f"  RISK 串货举报: {total_reports} 条")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="造 RISK 高风险经销商 + 订货/保修/举报数据. 默认 8 个, --count 指定数量.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""例:
  python scripts/gen_risky_users.py                # 8 个 (RISK001-008, 一套)
  python scripts/gen_risky_users.py --count 16     # 16 个 (2 套 × 8 模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 数据再生成
        """,
    )
    parser.add_argument("--count", type=int, default=8, help="生成 RISK 经销商数 (默认 8)")
    parser.add_argument("--reset", action="store_true", help="先删旧 RISK 经销商 + 关联数据")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))
