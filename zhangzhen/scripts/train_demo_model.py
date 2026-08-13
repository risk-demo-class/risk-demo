"""不依赖数据库的教学兜底模型；正式展示优先使用 train_xgb_model.py。"""

import argparse
import random
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.engine.feature import FEATURE_COLUMNS  # noqa: E402
from app.engine.ml_model import DEFAULT_MODEL_PATH  # noqa: E402
from app.engine.training import TrainingSample, train_xgboost_model  # noqa: E402


def synthetic_samples(count: int, seed: int) -> list[TrainingSample]:
    rng = random.Random(seed)
    start = datetime(2026, 1, 1)
    samples: list[TrainingSample] = []
    for index in range(count):
        positive = rng.random() < 0.28
        values = {name: 0.0 for name in FEATURE_COLUMNS}
        values.update(
            user_account_age_days=rng.randint(30, 2500),
            user_credit_score=rng.randint(420, 600) if positive else rng.randint(650, 830),
            user_kyc_level=1.0 if positive and rng.random() < 0.5 else 2.0,
            user_txn_count_30d=rng.randint(1, 80),
            user_txn_amount_30d=rng.randint(500, 300000),
            user_avg_txn_amount_30d=rng.randint(200, 8000),
            txn_amount=rng.randint(30000, 100000) if positive else rng.randint(20, 8000),
            txn_amount_vs_avg_ratio=rng.uniform(5, 15) if positive else rng.uniform(0.1, 3),
            txn_count_1h=rng.randint(3, 8) if positive and rng.random() < 0.4 else rng.randint(0, 2),
            txn_is_night=float(positive and rng.random() < 0.35),
            txn_is_new_beneficiary=float(positive and rng.random() < 0.55),
            txn_cross_city=float(positive and rng.random() < 0.55),
            device_age_days=rng.randint(0, 5) if positive else rng.randint(30, 1200),
            device_is_new=float(positive),
            ip_is_proxy=float(positive and rng.random() < 0.35),
            ip_is_tor=float(positive and rng.random() < 0.10),
            loan_debt_ratio=rng.uniform(0.7, 0.95) if positive else rng.uniform(0.05, 0.55),
        )
        samples.append(
            TrainingSample(
                assessment_id=f"DEMOA{index:06d}", event_id=f"DEMOE{index:06d}",
                user_id=f"DEMOU{index:06d}",
                event_time=start + timedelta(hours=index),
                features=tuple(float(values[name]) for name in FEATURE_COLUMNS),
                label=int(positive),
            )
        )
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="训练不依赖数据库的教学 XGBoost 模型")
    parser.add_argument("--samples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()
    if args.samples < 100:
        raise SystemExit("演示样本至少 100 条")
    metrics = train_xgboost_model(
        synthetic_samples(args.samples, args.seed), model_path=args.model_path, seed=args.seed
    )
    print("教学兜底模型训练完成（不代表真实银行效果）：")
    for name, value in asdict(metrics).items():
        print(f"  {name}: {value}")


if __name__ == "__main__":
    main()
