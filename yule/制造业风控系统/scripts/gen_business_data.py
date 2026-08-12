"""
制造业风控系统 - 业务数据生成脚本 (7 张业务表)

生成一套可复现的制造业渠道业务数据:
  - 12 个产品 (机床/注塑机/空压机等, 含 MSRP + 保修期)
  - 30 个经销商 (含档案/合同, 部分合同到期 / 新签约)
  - 300+ 张订货订单 (数量 1-130 台, 含大额囤货 / 跨区发货样本)
  - 120+ 条设备保修记录 (含保修期外 / 同 SN 高频 / 维修费虚高样本)
  - 20+ 条跨区串货举报记录
  - 若干业务黑名单扩展条目 (设备SN / 经销商ID / 维修工)

用法:
  python scripts/gen_business_data.py                 # 增量插入
  python scripts/gen_business_data.py --reset         # 先清空业务表再生成
  python scripts/gen_business_data.py --emit-sql sql/init_business_data.sql  # 同时生成 SQL 数据文件
"""
import argparse
import asyncio
import os
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


# ============================================================
# 基础字典数据
# ============================================================

PRODUCTS = [
    # (product_id, name, model, category, msrp, warranty_months)
    ("P001", "数控机床", "CNC-500", "机床", 680000, 24),
    ("P002", "注塑机", "IM-260", "注塑设备", 520000, 18),
    ("P003", "螺杆空压机", "AC-75", "空压机", 138000, 24),
    ("P004", "冲压机床", "ST-160", "机床", 260000, 12),
    ("P005", "工业机械臂", "RB-6", "自动化", 180000, 12),
    ("P006", "激光切割机", "LC-3015", "激光设备", 880000, 24),
    ("P007", "冷却塔", "CT-100", "配套设备", 96000, 18),
    ("P008", "包装线", "PK-60", "自动化", 320000, 12),
    ("P009", "数控车床", "LC-360", "机床", 420000, 24),
    ("P010", "折弯机", "WC-160", "机床", 360000, 12),
    ("P011", "注塑机", "IM-90", "注塑设备", 190000, 18),
    ("P012", "空压机", "AC-45", "空压机", 76000, 24),
]

REGIONS = ["广东", "江苏", "浙江", "山东", "上海", "北京", "福建", "安徽", "湖南", "四川"]

BRANDS = ["精工机械", "恒力制造", "东华重工", "瑞丰机床", "北方装备"]

TECHNICIANS = [f"T{str(i).zfill(3)}" for i in range(1, 11)]

INTERNAL_USERS = [f"E{str(i).zfill(3)}" for i in range(1, 6)]


def _dt(days_ago: int, hour: int = 10, minute: int = 0, rng: random.Random | None = None) -> datetime:
    """生成 days_ago 天前的某个时间点 (可带随机分钟)."""
    if rng is not None:
        minute = rng.randint(0, 59)
        hour = rng.randint(8, 20) if hour == 10 else hour
    base = datetime.now().replace(minute=minute, second=0, microsecond=0) - timedelta(days=days_ago)
    return base.replace(hour=hour)


# ============================================================
# 数据生成
# ============================================================

def _build_dataset(rng: random.Random):
    """生成全部业务行 (内存中), 返回各表行列表."""
    users = []
    dealers = []
    orders = []
    warranties = []
    reports = []
    blacklist_extra = []

    # 内部员工 + 终端用户
    for i, uid in enumerate(INTERNAL_USERS, 1):
        users.append((uid, f"员工{i}", "内部员工", None, REGIONS[i % len(REGIONS)],
                      _dt(rng.randint(200, 800))))
    for i in range(1, 6):
        users.append((f"TU{i:03d}", f"终端客户{i}", "终端用户", None,
                      REGIONS[i % len(REGIONS)], _dt(rng.randint(100, 500))))

    # 30 个经销商: 前 6 个带风险特征 (给 gen_risk_data --balance-pos 用), 其余正常
    for i in range(1, 31):
        uid = f"D{i:03d}"
        region = REGIONS[i % len(REGIONS)]
        register_days = rng.randint(30, 900)
        # 合同: D025-D027 合同已过期 (少量, 用于 R025 演示, 不影响整体通过率)
        if 25 <= i <= 27:
            contract_start = _dt(rng.randint(30, 90), rng=rng)
            contract_end = _dt(rng.randint(1, 60), rng=rng)    # 到期日在过去 1-60 天
        else:
            contract_start = _dt(rng.randint(60, 800), rng=rng)
            contract_end = contract_start + timedelta(days=365)
        dealer_level = ["核心经销商", "授权经销商", "普通经销商"][i % 3]
        users.append((uid, f"经销商{i}", "经销商", dealer_level, region, _dt(register_days, rng=rng)))
        dealers.append((uid, f"{region}xx机械有限公司{i}", region,
                        ",".join(rng.sample(BRANDS, 2)),
                        contract_start, contract_end))

        # 每个经销商 6-18 张订单
        n_orders = rng.randint(6, 18)
        order_time = _dt(rng.randint(5, 90), rng=rng)
        for j in range(n_orders):
            order_id = f"ORD_{uid}_{j+1:03d}"
            product = rng.choice(PRODUCTS)
            # 80% 授权区域, 20% 跨区 (D025-D030 已过期经销商跨区比例更高)
            cross_ratio = 0.45 if 25 <= i <= 30 else 0.2
            ship_region = region if rng.random() > cross_ratio else rng.choice(REGIONS)
            if i == 3 and j == n_orders - 1:
                quantity = rng.randint(110, 130)      # D003: 大额囤货
            elif i == 8 and j == 0:
                quantity = rng.randint(60, 90)        # D008: 新经销商大单
            else:
                # 正常订单以中小批量为主 (85% 为 1-8 台), 避免"大额规则"全量误伤
                r = rng.random()
                if r < 0.85:
                    quantity = rng.randint(1, 8)
                elif r < 0.97:
                    quantity = rng.randint(9, 30)
                else:
                    quantity = rng.randint(31, 60)
            discount = rng.uniform(0.85, 1.0)
            unit_price = Decimal(str(round(product[4] * discount, 2)))
            total = unit_price * quantity
            orders.append((
                order_id, uid, product[0], quantity, unit_price, total,
                ship_region, order_time + timedelta(days=j),
            ))

            # 保修记录: 约 35% 订单有 1 条; 6% 概率同一订单第二台设备(不同SN)报修
            # 正常数据不再生成"同SN 90天内重复保修", 避免误触 R008 套保
            if rng.random() < 0.35:
                sn = f"SN{uid[1:]}{product[0][1:]}{j+1:03d}"
                issue_days = rng.randint(0, 100)
                issue_date = order_time + timedelta(days=j + issue_days)
                issue_type = rng.choice(["质量问题", "质量问题", "人为损坏", "正常保养", "以旧换新"])
                # 维修费用: 正常 2%-35% MSRP; 偶发 65%-85% (维修费虚高 R018 演示)
                ratio = rng.uniform(0.02, 0.35)
                if rng.random() < 0.06:
                    ratio = rng.uniform(0.65, 0.85)
                repair_cost = Decimal(str(round(product[4] * ratio, 2)))
                warranties.append((
                    f"WR_{order_id}_01", sn, order_id,
                    issue_date, issue_type, repair_cost,
                    rng.choice(TECHNICIANS), issue_date,
                ))
                # 同订单第二台设备 (不同SN), 不触发同SN套保
                if rng.random() < 0.06:
                    sn2 = sn + "B"
                    issue_date2 = issue_date + timedelta(days=rng.randint(1, 40))
                    warranties.append((
                        f"WR_{order_id}_02", sn2, order_id,
                        issue_date2, rng.choice(["质量问题", "正常保养"]),
                        Decimal(str(round(product[4] * rng.uniform(0.02, 0.2), 2))),
                        rng.choice(TECHNICIANS), issue_date2,
                    ))

            # 跨区串货举报: 跨区订单约 50% 被举报
            if ship_region != region and rng.random() < 0.5:
                reports.append((
                    f"CR_{order_id}", order_id, uid, ship_region, region,
                    rng.choice(INTERNAL_USERS), order_time + timedelta(days=j + 2),
                ))

    # 业务黑名单扩展: 5 个设备SN + 3 个经销商 + 2 个维修工
    for idx, sn in enumerate([f"SN{i:03d}SN" for i in range(1, 6)]):
        blacklist_extra.append((sn, "设备SN", "疑似翻新机串货", None))
    for idx, d in enumerate(["D002", "D012", "D022"]):
        blacklist_extra.append((d, "经销商ID", "历史串货违规", None))
    blacklist_extra.append(("T007", "维修工", "虚报维修费用", None))
    blacklist_extra.append(("T009", "维修工", "与经销商合谋套保", None))

    return users, dealers, orders, warranties, reports, blacklist_extra


async def gen_business_data(reset: bool = False, seed: int = 42, emit_sql: str | None = None):
    """生成制造业业务数据并入库 (可选同时产出 SQL 文件)."""
    rng = random.Random(seed)
    users, dealers, orders, warranties, reports, blacklist_extra = _build_dataset(rng)

    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)

    async with engine.connect() as conn:
        if reset:
            print("[reset] 清空 7 张业务表...")
            for tbl in ("blacklist_extra", "cross_region_report", "warranty_record",
                        "order_info", "dealer_info", "product", "user_info"):
                await conn.execute(text(f"DELETE FROM {tbl}"))
            print("  清理完成")

        print(f"[generate] 产品 {len(PRODUCTS)} 个 / 经销商 {len(dealers)} 家 / 订单 {len(orders)} 张")
        print(f"          保修 {len(warranties)} 条 / 串货举报 {len(reports)} 条 / 黑名单扩展 {len(blacklist_extra)} 条")

        # 产品
        await conn.execute(text("""
            INSERT IGNORE INTO product (product_id, name, model, category, msrp, warranty_months)
            VALUES (:product_id, :name, :model, :category, :msrp, :warranty_months)
        """), [dict(product_id=p[0], name=p[1], model=p[2], category=p[3],
                    msrp=p[4], warranty_months=p[5]) for p in PRODUCTS])

        # 用户
        await conn.execute(text("""
            INSERT IGNORE INTO user_info (user_id, name, role, dealer_level, region, register_at)
            VALUES (:user_id, :name, :role, :dealer_level, :region, :register_at)
        """), [dict(user_id=u[0], name=u[1], role=u[2], dealer_level=u[3],
                    region=u[4], register_at=u[5]) for u in users])

        # 经销商档案
        await conn.execute(text("""
            INSERT IGNORE INTO dealer_info (dealer_id, dealer_name, region, authorized_brands,
            contract_start, contract_end)
            VALUES (:dealer_id, :dealer_name, :region, :authorized_brands,
            :contract_start, :contract_end)
        """), [dict(dealer_id=d[0], dealer_name=d[1], region=d[2], authorized_brands=d[3],
                    contract_start=d[4], contract_end=d[5]) for d in dealers])

        # 订单
        await conn.execute(text("""
            INSERT IGNORE INTO order_info (order_id, dealer_id, product_id, quantity,
            unit_price, total_amount, ship_to_region, create_time)
            VALUES (:order_id, :dealer_id, :product_id, :quantity,
            :unit_price, :total_amount, :ship_to_region, :create_time)
        """), [dict(order_id=o[0], dealer_id=o[1], product_id=o[2], quantity=o[3],
                    unit_price=o[4], total_amount=o[5], ship_to_region=o[6],
                    create_time=o[7]) for o in orders])

        # 保修
        await conn.execute(text("""
            INSERT IGNORE INTO warranty_record (warranty_id, product_sn, order_id, issue_date,
            issue_type, repair_cost, technician_id, create_time)
            VALUES (:warranty_id, :product_sn, :order_id, :issue_date,
            :issue_type, :repair_cost, :technician_id, :create_time)
        """), [dict(warranty_id=w[0], product_sn=w[1], order_id=w[2], issue_date=w[3],
                    issue_type=w[4], repair_cost=w[5], technician_id=w[6],
                    create_time=w[7]) for w in warranties])

        # 串货举报
        await conn.execute(text("""
            INSERT IGNORE INTO cross_region_report (report_id, order_id, dealer_id,
            ship_to_region, dealer_region, reporter_id, create_time)
            VALUES (:report_id, :order_id, :dealer_id,
            :ship_to_region, :dealer_region, :reporter_id, :create_time)
        """), [dict(report_id=r[0], order_id=r[1], dealer_id=r[2],
                    ship_to_region=r[3], dealer_region=r[4], reporter_id=r[5],
                    create_time=r[6]) for r in reports])

        # 业务黑名单扩展
        await conn.execute(text("""
            INSERT IGNORE INTO blacklist_extra (type, value, reason, expire_at)
            VALUES (:type, :value, :reason, :expire_at)
        """), [dict(type=b[1], value=b[0], reason=b[2], expire_at=b[3]) for b in blacklist_extra])

        await conn.commit()

        # 统计
        for tbl in ("product", "user_info", "dealer_info", "order_info",
                    "warranty_record", "cross_region_report", "blacklist_extra"):
            r = await conn.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
            print(f"  {tbl:<24} {r.scalar()} 行")

    await engine.dispose()

    # 可选: 生成 init_business_data.sql (init_db.py 流程用)
    if emit_sql:
        _emit_sql(emit_sql, users, dealers, orders, warranties, reports, blacklist_extra)
        print(f"\n[SQL] 已生成: {emit_sql}")


def _emit_sql(path: str, users, dealers, orders, warranties, reports, blacklist_extra):
    """把内存数据写成 SQL 文件 (INSERT IGNORE, init_db.py 可执行)."""
    def _v(v):
        if v is None:
            return "NULL"
        if isinstance(v, datetime):
            return f"'{v.strftime('%Y-%m-%d %H:%M:%S')}'"
        if isinstance(v, bool):
            return "1" if v else "0"
        return f"'{str(v)}'"

    lines = [
        "-- ============================================",
        "-- 制造业风控系统 - 业务测试数据 (由 scripts/gen_business_data.py 生成)",
        "-- ============================================",
        "USE mfg_risk;",
        "SET FOREIGN_KEY_CHECKS = 0;",
    ]
    tables = [
        ("product", ["product_id", "name", "model", "category", "msrp", "warranty_months"], PRODUCTS),
        ("user_info", ["user_id", "name", "role", "dealer_level", "region", "register_at"], users),
        ("dealer_info", ["dealer_id", "dealer_name", "region", "authorized_brands", "contract_start", "contract_end"], dealers),
        ("order_info", ["order_id", "dealer_id", "product_id", "quantity", "unit_price", "total_amount", "ship_to_region", "create_time"], orders),
        ("warranty_record", ["warranty_id", "product_sn", "order_id", "issue_date", "issue_type", "repair_cost", "technician_id", "create_time"], warranties),
        ("cross_region_report", ["report_id", "order_id", "dealer_id", "ship_to_region", "dealer_region", "reporter_id", "create_time"], reports),
    ]
    for tbl, cols, rows in tables:
        for row in rows:
            lines.append(
                f"INSERT IGNORE INTO {tbl} ({', '.join(cols)}) VALUES ({', '.join(_v(x) for x in row)});"
            )
    for row in blacklist_extra:
        lines.append(
            f"INSERT IGNORE INTO blacklist_extra (type, value, reason, expire_at) "
            f"VALUES ({_v(row[1])}, {_v(row[0])}, {_v(row[2])}, {_v(row[3])});"
        )
    lines.append("SET FOREIGN_KEY_CHECKS = 1;")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="制造业风控系统 - 业务数据生成 (7 张业务表, 300+ 订单)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""例:
  python scripts/gen_business_data.py                 # 增量插入
  python scripts/gen_business_data.py --reset         # 先清空业务表
  python scripts/gen_business_data.py --emit-sql sql/init_business_data.sql  # 生成 SQL 文件
        """,
    )
    parser.add_argument("--reset", action="store_true", help="先清空 7 张业务表再生成")
    parser.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42, 保证可复现)")
    parser.add_argument("--emit-sql", type=str, default=None,
                        help="同时生成 init_business_data.sql 文件路径")
    args = parser.parse_args()
    asyncio.run(gen_business_data(reset=args.reset, seed=args.seed, emit_sql=args.emit_sql))
