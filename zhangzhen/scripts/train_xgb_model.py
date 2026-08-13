"""从数据库快照训练 XGBoost，并输出 AUC/F1/Precision/Recall。"""

import argparse
import asyncio
import sys
from dataclasses import asdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import AsyncSessionLocal, async_engine  # noqa: E402
from app.engine.ml_model import DEFAULT_MODEL_PATH, ml_model  # noqa: E402
from app.engine.training import (  # noqa: E402
    load_training_samples,
    train_xgboost_model,
    validate_training_samples,
)


async def load_and_validate(args: argparse.Namespace):
    async with AsyncSessionLocal() as db:
        samples = await load_training_samples(db, limit=args.limit or None)
    validate_training_samples(
        samples,
        min_samples=args.min_samples,
        min_positive_ratio=args.min_positive_ratio,
        max_positive_ratio=args.max_positive_ratio,
        min_span_days=args.min_span_days,
    )
    return samples


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="训练银行风控 XGBoost 模型")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-samples", type=int, default=1250)
    parser.add_argument("--min-positive-ratio", type=float, default=0.15)
    parser.add_argument("--max-positive-ratio", type=float, default=0.60)
    parser.add_argument("--min-span-days", type=int, default=30)
    parser.add_argument("--validation-ratio", type=float, default=0.20)
    parser.add_argument("--rounds", type=int, default=300)
    parser.add_argument("--early-stopping-rounds", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    return parser


async def run(args: argparse.Namespace) -> None:
    try:
        samples = await load_and_validate(args)
        metrics = train_xgboost_model(
            samples,
            model_path=args.model_path,
            validation_ratio=args.validation_ratio,
            rounds=args.rounds,
            early_stopping_rounds=args.early_stopping_rounds,
            seed=args.seed,
        )
        ml_model.reload()
        print("XGBoost 训练完成：")
        for name, value in asdict(metrics).items():
            print(f"  {name}: {value}")
        if metrics.validation_auc < 0.70 or metrics.validation_f1 < 0.50:
            print("警告：指标低于教学参考线（AUC 0.70 / F1 0.50），请检查数据分布。")
        print("模型缺失或加载失败时，系统仍会自动走纯规则决策。")
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(run(build_parser().parse_args()))
