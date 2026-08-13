"""银行风控评估数据生成入口；风险模式来自业务 source，不反向伪造标签。"""

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import async_engine  # noqa: E402
from scripts.gen_train_dataset import gen_train_dataset


async def generate_risk_data(
    count: int = 200,
    balance_pos: bool = False,
    target_pos_ratio: float | None = None,
    seed: int = 20260812,
):
    """兼容旧参数；正例比例仅作结果观察，不据此改写 source 或标签。"""
    result = await gen_train_dataset(count=count, seed=seed, clean=False)
    if target_pos_ratio is not None and result["positive_ratio"] < target_pos_ratio:
        print(
            f"提示：实际正例比例 {result['positive_ratio']:.1%} 低于目标 "
            f"{target_pos_ratio:.1%}；请扩充可解释风险 source，不修改标签。"
        )
    return result


async def _runner() -> int:
    parser = argparse.ArgumentParser(description="生成银行风控评估数据")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--balance-pos", action="store_true", help="兼容参数；不操纵标签")
    parser.add_argument("--target-pos-ratio", type=float, default=None)
    args = parser.parse_args()
    try:
        result = await generate_risk_data(
            args.count, args.balance_pos, args.target_pos_ratio, args.seed
        )
        print(result)
        return 0
    finally:
        # 在事件循环关闭前释放全局引擎连接池，避免解释器退出时
        # aiomysql 在已关闭的 loop 上 close() 报 "Event loop is closed"
        await async_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_runner()))
