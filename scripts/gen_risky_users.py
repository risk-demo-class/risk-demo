"""
制造业风控系统 - RISK 高风险经销商生成 (可重复运行)

5 种风险模式轮换生成 (跟规则一一对应):
  模式 1: 高保修率     (10 单 + 9 保修, 保修率 90% → R015)
  模式 2: 30天高频订货 (35 单 → R007)
  模式 3: 套保+维修费  (同一 SN 90 天 2 次维修 + 费用>60%MSRP → R008/R018)
  模式 4: 跨区串货     (一单被举报 3 次 + 跨区大单 → R001/R026)
  模式 5: 新经销商大单 (签约<30 天 + 首单 50万/100万 → R012/R005)

实现: 委托 scripts/gen_business_data.py 的 build_risk_sql (同一份数据源, 保证幂等).

用法:
  python scripts/gen_risky_users.py                # 默认 5 个 (RISK001-005)
  python scripts/gen_risky_users.py --count 30     # 30 个 (6 套 × 5 模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 数据再生成
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from scripts.gen_business_data import build_risk_sql


async def gen_risky_users(count: int = 5, reset: bool = False):
    """生成 N 个 RISK 高风险经销商 (5 种模式轮换)."""
    if count < 1:
        raise ValueError(f"--count 必须 >= 1, 当前 {count}")

    db_url = settings.get_database_url_async()
    engine = create_async_engine(db_url)
    async with engine.connect() as conn:
        if reset:
            print("[reset] 删旧 RISK 经销商 + 关联数据...")
            for tbl in ("cross_region_report", "warranty_record", "order_info",
                        "dealer_info", "user_info"):
                await conn.execute(
                    text(f"DELETE FROM {tbl} WHERE dealer_id LIKE 'RISK%' OR user_id LIKE 'RISK%'")
                )
            print("  清理完成")

        stmts = build_risk_sql(count)
        print(f"[generate] 生成 {count} 个 RISK 高风险经销商 (5 模式轮换)...")
        for stmt in stmts:
            await conn.execute(text(stmt))
        await conn.commit()

        r = await conn.execute(text("SELECT COUNT(*) FROM user_info WHERE user_id LIKE 'RISK%'"))
        total_users = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM order_info WHERE dealer_id LIKE 'RISK%'"))
        total_orders = r.scalar()
        r = await conn.execute(text("""
            SELECT COUNT(*) FROM warranty_record w
            JOIN order_info oi ON w.order_id = oi.order_id
            WHERE oi.dealer_id LIKE 'RISK%'
        """))
        total_warranty = r.scalar()
        r = await conn.execute(text("SELECT COUNT(*) FROM cross_region_report WHERE dealer_id LIKE 'RISK%'"))
        total_report = r.scalar()

        print(f"\n[完成] RISK 高风险经销商数据生成完成!")
        print(f"  RISK 用户:   {total_users} 个")
        print(f"  RISK 订单:   {total_orders} 个")
        print(f"  RISK 工单:   {total_warranty} 条")
        print(f"  RISK 举报:   {total_report} 条")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="造 RISK 高风险经销商 + 订单/保修/举报. 默认 5 个, --count 指定数量.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python scripts/gen_risky_users.py                # 5 个 (RISK001-005, 一套)
  python scripts/gen_risky_users.py --count 30     # 30 个 (6 套 × 5 模式)
  python scripts/gen_risky_users.py --reset        # 先删旧 RISK 数据再生成
        """,
    )
    parser.add_argument("--count", type=int, default=5, help="生成 RISK 经销商数 (默认 5)")
    parser.add_argument("--reset", action="store_true", help="先删旧 RISK 数据")
    args = parser.parse_args()
    asyncio.run(gen_risky_users(count=args.count, reset=args.reset))
