"""银行特征 ABI 的纯合成模型冒烟脚本；不作为 Goal 3 最终验收模型。"""

import argparse
import os
import random
import sys
from pathlib import Path

import numpy as np
import xgboost as xgb
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS  # noqa: E402

FEATURE_NAMES = FEATURE_COLUMNS
N_FEATURES = len(FEATURE_NAMES)
assert N_FEATURES == 25


def _normal(rng: random.Random) -> np.ndarray:
    row = np.zeros(N_FEATURES, dtype=np.float32)
    row[0:2] = [rng.randint(0, 3), rng.randint(1, 8)]
    row[2:5] = [rng.uniform(100, 20_000), rng.uniform(100, 3_000), rng.uniform(200, 8_000)]
    row[5:14] = [2, 0, 1, 0, 0, 0.2, 0, 0, rng.randint(90, 1500)]
    row[14:22] = [rng.uniform(0, 10_000), 1, 0, 90, 1, 1, 0, 0]
    return row


def _risk_pattern(rng: random.Random, pattern: int) -> np.ndarray:
    row = _normal(rng)
    if pattern == 0:  # 异地大额
        row[14], row[24] = rng.uniform(50_001, 120_000), 1
    elif pattern == 1:  # 凌晨密集
        row[15], row[16] = rng.randint(3, 8), 1
    elif pattern == 2:  # 新设备大额
        row[14], row[17] = rng.uniform(30_001, 90_000), rng.uniform(0, 6.9)
    elif pattern == 3:  # 多卡归集
        row[19] = rng.randint(3, 8)
    elif pattern == 4:  # 信贷申请突击
        row[20], row[21] = rng.randint(3, 6), rng.uniform(0.5, 0.95)
    else:  # 共享设备 + 代理环境
        row[18], row[22] = rng.randint(5, 12), 1
    return row


def gen_synthetic_dataset(
    n: int = 2000, pos_ratio: float = 0.5, seed: int = 20260812
) -> tuple[np.ndarray, np.ndarray]:
    """仅用于验证 25 维顺序和训练依赖可用。"""
    rng = random.Random(seed)
    n_pos = int(n * pos_ratio)
    rows = [_risk_pattern(rng, i % 6) for i in range(n_pos)]
    rows.extend(_normal(rng) for _ in range(n - n_pos))
    labels = np.array([1] * n_pos + [0] * (n - n_pos), dtype=np.int32)
    order = np.random.default_rng(seed).permutation(n)
    return np.array(rows, dtype=np.float32)[order], labels[order]


def main() -> None:
    parser = argparse.ArgumentParser(description="银行 25 维特征模型冒烟（非最终验收）")
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--num-boost-round", type=int, default=100)
    parser.add_argument(
        "--model-path",
        default=os.path.join(ROOT, "app", "engine", "xgb_model.json"),
    )
    args = parser.parse_args()
    X, y = gen_synthetic_dataset(args.n, seed=args.seed)
    X_train, X_val, y_train, y_val = train_test_split(
        X,
        y,
        test_size=settings.XGB_TEST_SIZE,
        stratify=y,
        random_state=args.seed,
    )
    params = {
        "objective": "binary:logistic",
        "max_depth": 6,
        "learning_rate": 0.1,
        "min_child_weight": 3,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "eval_metric": "auc",
        "seed": args.seed,
    }
    dtrain = xgb.DMatrix(X_train, label=y_train, feature_names=FEATURE_COLUMNS)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_COLUMNS)
    model = xgb.train(
        params,
        dtrain,
        num_boost_round=args.num_boost_round,
        evals=[(dval, "val")],
        verbose_eval=False,
    )
    prob = model.predict(dval)
    print(
        f"smoke val_auc={roc_auc_score(y_val, prob):.4f} "
        f"val_f1={f1_score(y_val, prob >= 0.5):.4f}"
    )
    model.save_model(args.model_path)


if __name__ == "__main__":
    main()
