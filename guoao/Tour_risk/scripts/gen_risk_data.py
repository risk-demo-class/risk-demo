"""
物流风控系统 - 模拟风控评估数据生成 (条数模式, 兼容基线用法)

从运单抽样跑 process_event 生成评估记录, 用于填充案件/评估历史 + 训练数据.
本质是 gen_risk_data_with_dates.py 的"只造今天 N 条"薄封装.

用法:
  python scripts/gen_risk_data.py                         # 今天 100 条
  python scripts/gen_risk_data.py --count 200 --balance-pos   # 200 条 + 拉高正例
  python scripts/gen_risk_data.py --count 200 --clean         # 先清空再造
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.gen_risk_data_with_dates import run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="物流风控 - 造 N 条评估数据 (今天)")
    parser.add_argument("--count", type=int, default=100, help="生成条数 (默认 100)")
    parser.add_argument("--clean", action="store_true", help="先清空风控评估表")
    parser.add_argument("--balance-pos", action="store_true",
                        help="优先抽 RISK 高风险用户, 拉高正例比例 (训练用)")
    parser.add_argument("--target-pos-ratio", type=float, default=None,
                        help="兼容参数: 目标正例比例 (balance-pos 已覆盖, 此参数仅记录)")
    args = parser.parse_args()
    import asyncio
    asyncio.run(run(days=1, per_day=args.count, clean=args.clean,
                    balance_pos=args.balance_pos, live=True,
                    start=None, end=None))


if __name__ == "__main__":
    main()
