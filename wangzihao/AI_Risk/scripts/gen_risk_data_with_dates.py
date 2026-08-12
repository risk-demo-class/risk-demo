"""Compatibility CLI for the manufacturing Step 6 event generator.

Business timestamps already live on PurchaseOrder/WarrantyClaim/CrossRegionReport.
This wrapper therefore delegates to gen_risk_data and does not rewrite historical
risk snapshots after assessment.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from scripts.gen_risk_data import generate_risk_data


def main() -> None:
    parser = argparse.ArgumentParser(description="兼容入口：生成制造业风险事件快照")
    parser.add_argument("--days", type=int, default=30, help="兼容参数；业务日期由源表决定")
    parser.add_argument("--per-day", type=int, default=50)
    parser.add_argument("--max-per-day", type=int)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--balance-pos", action="store_true", help="兼容参数；标签由规则确定")
    parser.add_argument("--target-pos-ratio", type=float, help="兼容参数；不随机改写弱标签")
    parser.add_argument("--force-pos-ratio", type=float, help="兼容参数；不随机改写弱标签")
    parser.add_argument("--db", default=settings.DB_NAME)
    args = parser.parse_args()
    requested = args.days * args.per_day
    limit = min(requested, args.max_per_day * args.days) if args.max_per_day else requested
    asyncio.run(generate_risk_data(db_name=args.db, reset=args.clean, limit=limit))


if __name__ == "__main__":
    main()
