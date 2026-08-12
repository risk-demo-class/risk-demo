"""生成教育业务训练数据：所有样本都通过 process_event 获取真实特征和规则标签。"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.gen_business_data import generate_business_data
from app.engine.ml_model import unload_model


async def main() -> int:
    parser = argparse.ArgumentParser(description="生成教育风控训练数据")
    parser.add_argument("--events", type=int, default=500, help="默认500个业务事件")
    parser.add_argument("--seed", type=int, default=20260811)
    # 保留旧命令参数兼容，生成器本身始终只清理 GEN- 前缀数据。
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    # 训练样本必须由纯规则标签产生；即使磁盘上已有旧模型，也要写入 ml_score=NULL。
    unload_model()
    result = await generate_business_data(args.events, args.seed, run_risk=True)
    print("教育训练数据已生成")
    print(f"business_events={result['business_events']}")
    print(f"decisions={result['decisions']}")
    print(f"rule_hits={result['rule_hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
