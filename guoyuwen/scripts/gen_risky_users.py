"""生成含银行风险模式的虚构客户与四类 source。"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from scripts.gen_business_data import build_business_data, write_business_data
from scripts._console import banner, footer, summary

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RISK_MODES = ["异地大额", "凌晨密集", "新设备大额", "多头借贷", "设备多人共用"]


async def gen_risky_users(
    count: int = 5,
    reset: bool = False,
    *,
    seed: int = 20260812,
    db_name: str | None = None,
) -> dict:
    if count < 1:
        raise ValueError("--count 必须 >= 1")
    if reset:
        raise ValueError("本脚本不清库；请仅对专用库运行 init_db.py --reset --yes")
    data = build_business_data(count=max(80, count * 4), seed=seed)
    await write_business_data(data, db_name or settings.DB_NAME)
    return {
        "seed": seed,
        "requested_users": count,
        "generated_users": len(data["user_info"]),
        "risk_patterns": data["risk_patterns"],
    }


def _print_result(result: dict) -> None:
    print()
    summary(
        [
            ("seed", result["seed"]),
            ("请求用户", result["requested_users"]),
            ("生成用户", result["generated_users"]),
        ],
        title="生成结果",
    )
    summary(
        [(k, v) for k, v in result["risk_patterns"].items()],
        title="风险模式分布",
    )


async def _runner() -> int:
    parser = argparse.ArgumentParser(description="生成银行风险模式客户（default 5）")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--db", default=settings.DB_NAME)
    parser.add_argument("--reset", action="store_true", help="安全保留参数；不会在本脚本清库")
    args = parser.parse_args()
    banner("银行风险模式客户生成", f"seed={args.seed} | 目标 {args.count} 个虚构用户")
    result = await gen_risky_users(
        args.count, args.reset, seed=args.seed, db_name=args.db
    )
    _print_result(result)
    footer("生成完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_runner()))
