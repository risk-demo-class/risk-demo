"""
制造业风控系统 - 业务演示数据生成脚本 (动态日期)

每个规则都准备了可触发的样例:
  R001 串货举报 → REP002 (订单 ORD002 被举报 2 次)
  R002 保修期外高频保修 → WAR012 (SN HP2000001, 过保修 + 30 天 3 次申请)
  R005 大额囤货 → ORD003 / ORD007 (单笔 >100 万)
  R008 套保嫌疑 → WAR004 (SN AR3000001, 90 天 3 次维修)
  R012 新经销商大单 → ORD005 (新签约 20 天 + 首单 60 万)
  R018 维修费用异常 → WAR020 (维修费 5 万 = MSRP 62.5%)
  R025 资质过期 → ORD003 (D002 合同已过期仍订货)
  R030 黑经销商拦截 → ORD010 (D007 在业务黑名单)
黑名单拦截 → ORD004 (D003 在风控黑名单, 前置拦截不建案)

用法: python scripts/gen_data.py
依赖: 先跑 python scripts/init_db.py --yes
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

import aiomysql

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 3306
DEFAULT_USER = "root"
DEFAULT_PASSWORD = "Aa666666"
DEFAULT_DB = "manufacturing_risk"

NOW = datetime.now()


def d(days_ago: int) -> str:
    """今天往前 N 天的日期字符串 (YYYY-MM-DD HH:MM:SS)"""
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


# ============================================================
# 数据定义
# ============================================================

USERS = [
    # (user_id, name, role, dealer_level, region, register_at)
    # 经销商用户的 user_id 直接等于 dealer_id (D 前缀), 风控归属校验按 dealer_id 匹配
    ("D001", "华东机械",   "经销商", "一级", "华东", d(500)),
    ("D002", "华南工业",   "经销商", "二级", "华南", d(600)),
    ("D003", "北方重工",   "经销商", "一级", "华北", d(480)),
    ("D004", "新锐贸易",   "经销商", "三级", "华中", d(25)),
    ("D005", "华中设备",   "经销商", "三级", "华中", d(420)),
    ("D006", "东北工贸",   "经销商", "二级", "东北", d(300)),
    ("D007", "西南机电",   "经销商", "二级", "西南", d(360)),
    ("D008", "华东新材",   "经销商", "三级", "华东", d(260)),
    ("U003", "张工",       "终端用户", None, "华东", d(200)),
    ("U004", "李工",       "终端用户", None, "华北", d(150)),
    ("U005", "王经理",     "内部员工", None, "华东", d(400)),
]

DEALERS = [
    # (dealer_id, dealer_name, region, brands, contract_start, contract_end)
    ("D001", "华东机械", "华东", "品牌A,品牌B", d(580), d(-400)),   # 有效合同 (d(负)=未来)
    ("D002", "华南工业", "华南", "品牌A",       d(800), d(40)),      # 已过期 40 天 → R025
    ("D003", "北方重工", "华北", "品牌B,品牌C", d(520), d(-120)),   # 风控黑名单 → 前置拦截
    ("D004", "新锐贸易", "华中", "品牌A",       d(20),  d(-730)),    # 新签约 20 天 → R012
    ("D005", "华中设备", "华中", "品牌B",       d(430), d(-280)),
    ("D006", "东北工贸", "东北", "品牌A,品牌C", d(330), d(-350)),
    ("D007", "西南机电", "西南", "品牌B",       d(490), d(-120)),    # 业务黑名单 → R030
    ("D008", "华东新材", "华东", "品牌A,品牌B", d(220), d(-400)),
]

PRODUCTS = [
    # (product_id, name, model, category, msrp, warranty_months)
    ("P001", "工业机械臂", "AR-300",  "装备制造", 500000, 24),
    ("P002", "数控机床",   "CNC-850", "装备制造", 1500000, 36),
    ("P003", "检测传感器", "SEN-100", "电子元件", 80000, 12),
    ("P004", "液压泵",     "HP-200",  "动力部件", 200000, 18),
]

ORDERS = [
    # (order_id, dealer_id, product_id, qty, unit_price, total_amount, ship_to_region, create_time)
    ("ORD001", "D001", "P001", 1, 480000, 480000, "华东", d(57)),
    ("ORD002", "D001", "P001", 2, 470000, 940000, "华中", d(52)),   # 跨区 + 被举报 2 次 → R001
    ("ORD003", "D002", "P002", 1, 1450000, 1450000, "华北", d(22)),  # 大额 + 资质过期 → R005+R025
    ("ORD004", "D003", "P001", 1, 500000, 500000, "华北", d(6)),     # 风控黑名单 → 前置拦截
    ("ORD005", "D004", "P001", 1, 600000, 600000, "华中", d(10)),    # 新经销商首单大额 → R012
    ("ORD006", "D004", "P004", 2, 190000, 380000, "华中", d(3)),
    ("ORD007", "D005", "P002", 1, 1200000, 1200000, "华中", d(32)),  # 大额 → R005
    ("ORD008", "D005", "P001", 1, 300000, 300000, "华中", d(31)),
    ("ORD009", "D006", "P002", 1, 800000, 800000, "东北", d(52)),
    ("ORD010", "D007", "P003", 2, 75000, 150000, "西南", d(17)),     # 业务黑名单 → R030
    ("ORD011", "D008", "P003", 1, 70000, 70000, "华东", d(93)),      # 维修费用异常演示设备
    ("ORD012", "D001", "P004", 1, 180000, 180000, "华东", d(9)),
    ("ORD013", "D008", "P004", 1, 190000, 190000, "华东", d(578)),   # 已过保修期设备 → R002
]

WARRANTIES = [
    # (warranty_id, product_sn, order_id, issue_date, issue_type, repair_cost, technician_id)
    # --- AR3000001 (ORD001, P001 保修24月, 没过保) ---
    ("WAR001", "AR3000001", "ORD001", d(41), "保修申请", 0, None),
    ("WAR002", "AR3000001", "ORD001", d(37), "维修", 20000, "T001"),
    ("WAR003", "AR3000001", "ORD001", d(22), "维修", 25000, "T002"),
    ("WAR004", "AR3000001", "ORD001", d(10), "维修", 18000, "T001"),  # 90天3次维修 → R008
    # --- HP2000001 (ORD013, P004 保修18月, 已过保) ---
    ("WAR010", "HP2000001", "ORD013", d(19), "保修申请", 0, None),
    ("WAR011", "HP2000001", "ORD013", d(6),  "保修申请", 0, None),
    ("WAR012", "HP2000001", "ORD013", d(1),  "保修申请", 0, None),    # 过保+30天3次 → R002
    # --- SEN1000002 (ORD011, P003 MSRP 8万, 没过保) ---
    ("WAR020", "SEN1000002", "ORD011", d(5), "维修", 50000, "T003"),  # 5万=MSRP 62.5% → R018
    # --- CNC8500001 (ORD003, P002 保修36月, 没过保) ---
    ("WAR021", "CNC8500001", "ORD003", d(20), "保修申请", 0, None),
    ("WAR022", "CNC8500001", "ORD003", d(18), "维修", 150000, "T002"),  # 正常维修 → 通过
]

REPORTS = [
    # (report_id, order_id, dealer_id, ship_to_region, dealer_region, reporter_id, create_time)
    ("REP001", "ORD002", "D001", "华中", "华东", "U005", d(27)),
    ("REP002", "ORD002", "D001", "华南", "华东", "U005", d(24)),   # 第2次举报 → R001
    ("REP003", "ORD003", "D002", "华北", "华南", "U005", d(20)),   # 只1次, 不触发
]

BLACKLIST_EXTRA = [
    # (entry_id, type, value, reason, expire_at)
    ("BE001", "经销商ID", "D007", "历史串货记录", None),
    ("BE002", "设备SN", "SN-BE-999", "套保嫌疑", None),
]

RISK_BLACKLIST = [
    # (blacklist_type, blacklist_value, reason, expire_time)
    ("经销商ID", "D003", "伪造授权书", None),
]


# ============================================================
# 写入逻辑
# ============================================================

async def get_connection(host, port, user, password, db):
    return await aiomysql.connect(
        host=host, port=port, user=user, password=password,
        db=db, charset="utf8mb4", autocommit=True,
    )


async def clear_tables(conn):
    """按外键依赖顺序清空业务表 (先子后父)."""
    async with conn.cursor() as cur:
        await cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for table in [
            "cross_region_report", "warranty_record", "order_info",
            "blacklist_extra", "dealer_info", "product", "user_info",
            "risk_blacklist",
        ]:
            await cur.execute(f"TRUNCATE TABLE `{table}`")
        await cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    print("  已清空 7 张业务表 + risk_blacklist")


async def insert_rows(conn, table, columns, rows):
    async with conn.cursor() as cur:
        cols = ", ".join(f"`{c}`" for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO `{table}` ({cols}) VALUES ({placeholders})"
        await cur.executemany(sql, rows)
    print(f"  {table}: {len(rows)} 行")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="制造业风控系统 - 生成业务演示数据")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--db", default=DEFAULT_DB)
    args = parser.parse_args()

    print("=" * 60)
    print("制造业风控系统 - 业务演示数据生成")
    print(f"目标: {args.user}@{args.host}:{args.port}/{args.db}")
    print("=" * 60)

    try:
        conn = await get_connection(args.host, args.port, args.user, args.password, args.db)
    except aiomysql.Error as e:
        print(f"错误: 无法连接 MySQL - {e}")
        print("检查: 先跑 python scripts/init_db.py --yes 建库建表")
        sys.exit(1)

    try:
        print("\n[1/4] 清空旧数据")
        await clear_tables(conn)

        print("\n[2/4] 写入基础档案 (用户/产品/经销商)")
        await insert_rows(conn, "user_info",
                          ["user_id", "name", "role", "dealer_level", "region", "register_at"],
                          USERS)
        await insert_rows(conn, "product",
                          ["product_id", "name", "model", "category", "msrp", "warranty_months"],
                          PRODUCTS)
        await insert_rows(conn, "dealer_info",
                          ["dealer_id", "dealer_name", "region", "authorized_brands", "contract_start", "contract_end"],
                          DEALERS)

        print("\n[3/4] 写入业务单据 (订货/保修/举报)")
        await insert_rows(conn, "order_info",
                          ["order_id", "dealer_id", "product_id", "quantity", "unit_price",
                           "total_amount", "ship_to_region", "create_time"],
                          ORDERS)
        await insert_rows(conn, "warranty_record",
                          ["warranty_id", "product_sn", "order_id", "issue_date", "issue_type",
                           "repair_cost", "technician_id"],
                          WARRANTIES)
        await insert_rows(conn, "cross_region_report",
                          ["report_id", "order_id", "dealer_id", "ship_to_region", "dealer_region",
                           "reporter_id", "create_time"],
                          REPORTS)

        print("\n[4/4] 写入黑名单 (业务 + 风控)")
        await insert_rows(conn, "blacklist_extra",
                          ["entry_id", "type", "value", "reason", "expire_at"],
                          BLACKLIST_EXTRA)
        await insert_rows(conn, "risk_blacklist",
                          ["blacklist_type", "blacklist_value", "reason", "expire_time"],
                          RISK_BLACKLIST)
    finally:
        await conn.ensure_closed()

    print("\n" + "=" * 60)
    print("造数完成! 演示场景速查:")
    print("  串货举报(拒绝)  : 事件=串货举报  source=REP002  user=U005")
    print("  保修外高频(审核): 事件=保修申请  source=WAR012  user=D008")
    print("  大额囤货(审核)  : 事件=经销商订货 source=ORD003  user=D002")
    print("  套保嫌疑(拒绝)  : 事件=售后维修  source=WAR004  user=D001")
    print("  新经销商大单(标记): 事件=经销商订货 source=ORD005  user=D004")
    print("  维修费用异常(标记): 事件=售后维修  source=WAR020  user=D008")
    print("  资质过期(标记)  : 事件=经销商订货 source=ORD007  user=D005")
    print("  黑经销商(拒绝)  : 事件=经销商订货 source=ORD010  user=D007")
    print("  黑名单前置拦截   : 事件=经销商订货 source=ORD004  user=D003")
    print("  正常通过         : 事件=售后维修  source=WAR022  user=D002")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
