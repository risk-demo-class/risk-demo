"""
旅游风控系统 - 行业高风险用户与业务数据生成

实现复用 scripts/gen_business_data.py (单一数据源):
  - 40 个用户里内置 7 个 RISK 高风险画像用户 (RISK001-RISK007)
  - 保证演示时至少 6 条规则 + 黑名单拦截可命中

用法:
  python scripts/gen_risky_users.py                  # 直连 MySQL 生成
  python scripts/gen_risky_users.py --count 60       # 更多用户
  python scripts/gen_risky_users.py --export-sql     # 只导出 SQL 快照
"""
import argparse
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.gen_business_data import build_rows, export_sql, insert_rows  # noqa: E402


def _summary(rows: dict[str, list[dict]]) -> None:
    risk_users = [u for u in rows["user_info"] if u["user_id"].startswith("RISK")]
    risk_order_ids = {
        o["order_id"] for o in rows["order_info"] if o["user_id"].startswith("RISK")
    }
    risk_passengers = sum(1 for p in rows["passenger_info"] if p["order_id"] in risk_order_ids)
    print("=" * 60)
    print(f"高风险用户: {len(risk_users)} 个 (RISK001-RISK007)")
    print(f"  RISK001 新用户大单 / RISK002 拒签刷签 / RISK003 黄牛囤票")
    print(f"  RISK004 0点突击下单 / RISK005 盗用证件代订 / RISK006 高频退订 / RISK007 黑护照乘客")
    print(f"  关联订单 {len(risk_order_ids)} 条, 乘客 {risk_passengers} 人")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="旅游风控系统 - 高风险用户生成")
    parser.add_argument("--count", type=int, default=40, help="用户数 (默认 40, 含 7 个 RISK 用户)")
    parser.add_argument("--export-sql", action="store_true",
                        help="只导出 sql/init_business_data.sql, 不连数据库")
    args = parser.parse_args()

    rows = build_rows(args.count)
    _summary(rows)
    if args.export_sql:
        export_sql(rows, os.path.join(ROOT, "sql", "init_business_data.sql"))
        return
    asyncio.run(insert_rows(rows))


if __name__ == "__main__":
    main()
