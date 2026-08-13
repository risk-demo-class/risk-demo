"""按数量窗口生成银行风控评估；create_time 可按最近 N 天铺开（供仪表盘演示）。"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import async_engine  # noqa: E402
from scripts.gen_train_dataset import gen_train_dataset  # noqa: E402
from scripts._console import banner, footer, ok, step, summary, warn  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


async def generate_risk_data_with_dates(
    days: int = 30,
    per_day: int = 50,
    *,
    clean: bool = False,
    seed: int = 20260812,
    live: bool = False,
) -> dict:
    return await gen_train_dataset(
        count=days * per_day, seed=seed, clean=clean,
        spread_days=days, live=live,
    )


def _print_result(result: dict) -> None:
    print()
    summary(
        [
            ("seed", result["seed"]),
            ("请求样本", result["requested"]),
            ("成功生成", result["generated"]),
            (
                "正例 (拒绝+人工审核)",
                f"{result['positive']} ({result['positive_ratio']:.1%})",
            ),
            ("教学黑卡拦截 (不入库)", result["blacklist_hits"]),
        ],
        title="生成结果",
    )
    if result["time_min"]:
        summary([("时间范围", f"{result['time_min']} ~ {result['time_max']}")])
    summary(
        [(k, v) for k, v in result["decisions"].items()],
        title="决策分布",
    )
    summary(
        [(k, v) for k, v in result["events"].items()],
        title="事件分布",
    )


async def _runner() -> int:
    parser = argparse.ArgumentParser(description="按业务日期生成银行风控评估")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--per-day", type=int, default=50)
    parser.add_argument("--max-per-day", type=int, default=None, help="兼容上限参数")
    parser.add_argument("--start", default=None, help="兼容展示参数；日期由 --days 决定")
    parser.add_argument("--end", default=None, help="兼容展示参数；日期由 --days 决定")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument(
        "--live",
        action="store_true",
        help="兼容参数：等价于 --days 1（全部按当前时间入库，供仪表盘演示）",
    )
    parser.add_argument("--balance-pos", action="store_true", help="兼容参数；不操纵标签")
    parser.add_argument("--target-pos-ratio", type=float, default=None)
    parser.add_argument("--force-pos-ratio", type=float, default=None, help="已弃用；不允许强改标签")
    parser.add_argument("--seed", type=int, default=20260812)
    args = parser.parse_args()
    try:
        per_day = min(args.per_day, args.max_per_day) if args.max_per_day else args.per_day
        if args.live and args.days > 1:
            warn(
                f"--live 表示全部按当前时间入库，--days={args.days} 的日期铺开被覆盖；"
                "如需最近多天曲线，请去掉 --live 运行。"
            )
        banner(
            "银行风控评估数据生成（按日期铺开）",
            f"seed={args.seed} | --days {args.days} × --per-day {per_day} = "
            f"{args.days * per_day} 条",
        )
        result = await generate_risk_data_with_dates(
            args.days, per_day, clean=args.clean, seed=args.seed, live=args.live
        )
        _print_result(result)
        if result["blacklist_hits"]:
            ok(
                f"教学黑卡前置拦截 {result['blacklist_hits']} 条"
                "（黑名单前置、不入库，符合教学演示预期）"
            )
        requested_ratio = args.target_pos_ratio or args.force_pos_ratio
        if requested_ratio is not None:
            print(
                f"实际正例比例 {result['positive_ratio']:.1%}；目标仅用于观察，"
                "标签仍完全来自规则/决策。"
            )
        footer("生成完成")
        return 0
    finally:
        # 在事件循环关闭前释放全局引擎连接池，避免解释器退出时
        # aiomysql 在已关闭的 loop 上 close() 报 "Event loop is closed"
        await async_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_runner()))
