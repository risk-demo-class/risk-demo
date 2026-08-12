"""
制造业风控系统 - 10w 条随机业务数据生成 (异步, 一次性压测脚本)
================
生成规模 (默认 ≈ 10w 条, 可调):
  - 用户 (user_info):           N_USER      (默认 8000)
  - 产品 (product):             10 种 (固定目录)
  - 经销商 (dealer_info):       N_DEALER    (默认 1500, 用户里 role=经销商)
  - 订货单 (order_info):        N_ORDER     (默认 40000)
  - 保修工单 (warranty_record): N_ORDER*15% (默认 6000)
  - 串货举报 (cross_region_report): N_ORDER*3% (默认 1200)
  - 总条目:                     ≈ 10w

风险画像 (自动注入, 跟 13 条规则对应):
  - 80% 正常经销商 (中等订货, 低保修率)
  - 15% 中风险 (保修率 30-50% / 跨区发货 / 折扣异常)
  - 5%  高风险 (大额囤货 / 高频订货 / 套保 SN / 被举报串货)

幂等: 重复跑会因主键冲突报错, 用 --drop 先清 (⚠ 危险, 清空业务数据)
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


PRODUCTS = [
    ("P001", "数控机床", "CK6150", "工业母机", 250000, 24),
    ("P002", "注塑机", "HTF120X", "成型设备", 180000, 18),
    ("P003", "工业机器人", "ER6", "自动化", 120000, 24),
    ("P004", "检测设备", "CT-300", "检测仪器", 95000, 12),
    ("P005", "激光切割机", "LC-3015", "切割设备", 320000, 24),
    ("P006", "螺杆空压机", "GA-75", "通用设备", 68000, 12),
    ("P007", "高速电主轴", "DZ-120", "功能部件", 42000, 6),
    ("P008", "伺服电机", "SM-80", "功能部件", 15000, 12),
    ("P009", "PLC控制器", "PLC-300", "自动化", 8000, 12),
    ("P010", "精密减速机", "RV-110", "功能部件", 28000, 18),
]
REGIONS = ["华东", "华南", "华北", "西南", "华中", "西北"]
LEVELS = ["一级", "二级", "三级"]


def _dt(days_ago: int, hour: int = 10) -> str:
    return (datetime.now() - timedelta(days=days_ago)).replace(
        hour=hour, minute=random.randint(0, 59), second=random.randint(0, 59),
    ).strftime("%Y-%m-%d %H:%M:%S")


def _risk_level(rng: random.Random) -> str:
    r = rng.random()
    if r < 0.80:
        return "normal"
    if r < 0.95:
        return "mid"
    return "high"


async def gen_10w_data(n_users: int = 8000, n_dealers: int = 1500, n_orders: int = 40000,
                       drop: bool = False, seed: int = 42):
    rng = random.Random(seed)
    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)
    now = datetime.now()

    async with engine.begin() as conn:
        if drop:
            print("⚠️  --drop: 清空 7 张业务表 (危险操作)...")
            for tbl in ("cross_region_report", "warranty_record", "order_info",
                        "dealer_info", "product", "user_info", "blacklist_extra"):
                await conn.execute(text(f"DELETE FROM {tbl}"))

        # 1. 产品 (固定 10 种)
        print("[1/6] 产品...")
        await conn.execute(text(
            "INSERT IGNORE INTO product (product_id, name, model, category, msrp, warranty_months) VALUES "
            + ",".join(f"('{p}', '{n}', '{m}', '{c}', {msrp}, {wm})" for p, n, m, c, msrp, wm in PRODUCTS)
        ))

        # 2. 用户 + 经销商
        print(f"[2/6] 用户 {n_users} + 经销商 {n_dealers}...")
        user_rows, dealer_rows = [], []
        for i in range(n_users):
            uid = f"U{i:06d}"
            if i < n_dealers:
                role, level, region = "经销商", LEVELS[i % 3], REGIONS[i % 6]
                dealer_rows.append(
                    f"('{uid}', '压测机电{uid}', '{region}', '全品牌', "
                    f"'{_dt(rng.randint(60, 1200))}', '{_dt(-rng.randint(60, 400))}', '合作中')"
                )
            else:
                role, level, region = ("终端用户", "NULL", REGIONS[i % 6])
            level_sql = f"'{level}'" if level != "NULL" else "NULL"
            user_rows.append(
                f"('{uid}', '用户{uid[-4:]}', '{role}', {level_sql}, "
                f"'{region}', '136{i % 100000000:08d}', '{_dt(rng.randint(30, 1500))}')"
            )
        await conn.execute(text(
            "INSERT INTO user_info (user_id, name, role, dealer_level, region, phone, register_at) VALUES "
            + ",\n".join(user_rows)
        ))
        await conn.execute(text(
            "INSERT INTO dealer_info (dealer_id, dealer_name, region, authorized_brands, contract_start, contract_end, status) VALUES "
            + ",\n".join(dealer_rows)
        ))

        # 3. 订货单 (正常/中/高风险画像)
        print(f"[3/6] 订货单 {n_orders}...")
        order_rows = []
        warranty_rows, report_rows = [], []
        order_meta = []  # (order_id, dealer_id, product_id, msrp, warranty_months, ship_region, create_days)
        for i in range(n_orders):
            oid = f"O{i:07d}"
            did = f"U{rng.randrange(n_dealers):06d}"
            pid, name, model, cat, msrp, wm = PRODUCTS[rng.randrange(len(PRODUCTS))]
            level = _risk_level(rng)
            qty = rng.randint(1, 50)
            if level == "high":
                factor = rng.choice([0.45, 0.9, 0.95, 1.0])
                qty = rng.randint(20, 100)
                days_ago = rng.randint(0, 30)
                hour = rng.choice([1, 2, 3, 4, 5, 10, 14])
            elif level == "mid":
                factor = rng.choice([0.5, 0.7, 0.85, 0.9])
                days_ago = rng.randint(0, 90)
                hour = rng.randint(0, 23)
            else:
                factor = rng.uniform(0.85, 1.0)
                days_ago = rng.randint(0, 180)
                hour = rng.randint(8, 18)
            unit_price = round(msrp * factor)
            total = unit_price * qty
            ship = REGIONS[rng.randrange(len(REGIONS))]
            otype = "采购订单" if rng.random() < 0.15 else "经销商订货"
            order_rows.append(
                f"('{oid}', '{otype}', '{did}', '{pid}', {qty}, {unit_price}, {total}, "
                f"'{ship}', '已完成', '{_dt(days_ago, hour)}')"
            )
            order_meta.append((oid, did, pid, msrp, wm, ship, days_ago, level, i))

            # 保修工单 (~15%, 高风险经销商保修率高)
            war_odds = 0.55 if level == "high" else (0.20 if level == "mid" else 0.08)
            if rng.random() < war_odds:
                sn = f"SN-{did}-{rng.randint(1, 5):04d}"
                itype = "维修" if level == "high" and rng.random() < 0.6 else "保修"
                cost_factor = rng.uniform(0.65, 0.9) if level == "high" else rng.uniform(0.02, 0.25)
                cost = round(msrp * cost_factor)
                warranty_rows.append(
                    f"('W{i:07d}', '{sn}', '{oid}', '{_dt(max(0, days_ago - rng.randint(0, 5)), 10)}', "
                    f"'{itype}', {cost}, 'TEC{rng.randint(1, 30):03d}', '压测工单')"
                )
            # 串货举报 (~3%, 高风险经销商被举报多)
            rep_odds = 0.25 if level == "high" else (0.03 if level == "mid" else 0.005)
            if rng.random() < rep_odds:
                report_rows.append(
                    f"('{oid}', '{did}', '{ship}', '{REGIONS[rng.randrange(len(REGIONS))]}', "
                    f"'E001', '待核实', '{_dt(max(0, days_ago - rng.randint(1, 3)), 14)}')"
                )

        # 分批写入 (避免 SQL 太长)
        BATCH = 2000
        for start in range(0, len(order_rows), BATCH):
            await conn.execute(text(
                "INSERT INTO order_info (order_id, order_type, dealer_id, product_id, quantity, unit_price, total_amount, ship_to_region, order_status, create_time) VALUES "
                + ",\n".join(order_rows[start:start + BATCH])
            ))
        print(f"  订单 {len(order_rows)} 行已写入")

        # 4-5. 保修工单 + 串货举报
        print(f"[4/6] 保修工单 {len(warranty_rows)}...")
        for start in range(0, len(warranty_rows), BATCH):
            await conn.execute(text(
                "INSERT INTO warranty_record (warranty_id, product_sn, order_id, issue_date, issue_type, repair_cost, technician_id, description) VALUES "
                + ",\n".join(warranty_rows[start:start + BATCH])
            ))
        print(f"[5/6] 串货举报 {len(report_rows)}...")
        for start in range(0, len(report_rows), BATCH):
            await conn.execute(text(
                "INSERT INTO cross_region_report (order_id, dealer_id, ship_to_region, dealer_region, reporter_id, report_status, create_time) VALUES "
                + ",\n".join(report_rows[start:start + BATCH])
            ))

        # 6. 行业黑名单样例
        print("[6/6] 行业黑名单样例...")
        await conn.execute(text(
            "INSERT IGNORE INTO blacklist_extra (type, value, reason, expire_at, create_time) VALUES "
            f"('经销商', 'U000000', '压测黑名单', NULL, '{now:%Y-%m-%d %H:%M:%S}'), "
            f"('设备SN', 'SN-BLK-0002', '压测黑SN', NULL, '{now:%Y-%m-%d %H:%M:%S}')"
        ))

        print("\n[完成] 统计:")
        for tbl in ("user_info", "product", "dealer_info", "order_info",
                    "warranty_record", "cross_region_report", "blacklist_extra"):
            r = await conn.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
            print(f"  {tbl:<22} {r.scalar()} 行")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="制造业 10w 条随机业务数据生成 (压测)")
    parser.add_argument("--n-users", type=int, default=8000, help="用户数 (默认 8000)")
    parser.add_argument("--n-dealers", type=int, default=1500, help="经销商数 (默认 1500)")
    parser.add_argument("--n-orders", type=int, default=40000, help="订货单数 (默认 40000)")
    parser.add_argument("--drop", action="store_true", help="⚠ 先清空 7 张业务表")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()
    asyncio.run(gen_10w_data(
        n_users=args.n_users, n_dealers=args.n_dealers, n_orders=args.n_orders,
        drop=args.drop, seed=args.seed,
    ))
