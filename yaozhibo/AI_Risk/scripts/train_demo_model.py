"""使用教育风险模式生成25维合成数据并训练演示模型（不依赖数据库）。"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.engine.ml_model import FEATURE_COLUMNS, train_and_save  # noqa: E402


def _normal(rng: np.random.Generator) -> dict[str, float]:
    return {
        "user_account_age_days": rng.uniform(60, 1000),
        "user_purchase_count_1h": rng.uniform(0, 1),
        "user_purchase_amount_1h": rng.uniform(0, 5000),
        "user_purchase_count_7d": rng.uniform(0, 3),
        "user_purchase_amount_7d": rng.uniform(0, 12000),
        "user_refund_count_90d": rng.uniform(0, 1),
        "user_refund_amount_90d": rng.uniform(0, 1000),
        "user_refund_rate_90d": rng.uniform(0, 0.1),
        "user_learning_minutes_30d": rng.uniform(60, 3000),
        "user_avg_completion_rate": rng.uniform(0.3, 1),
        "order_total_amount": rng.uniform(0, 8000),
        "course_price": rng.uniform(500, 8000),
        "current_study_minutes": rng.uniform(30, 1000),
        "current_completion_rate": rng.uniform(0.1, 1),
        "device_distinct_users_30d": rng.uniform(1, 2),
    }


def _risk_pattern(kind: int, rng: np.random.Generator) -> dict[str, float]:
    row = _normal(rng)
    patterns = (
        {"refund_study_minutes": rng.uniform(0, 4), "refund_amount": rng.uniform(1000, 15000)},
        {"user_refund_count_90d": rng.uniform(3, 8), "user_refund_amount_90d": rng.uniform(10001, 50000)},
        {"user_purchase_count_1h": rng.uniform(4, 10), "user_purchase_amount_1h": rng.uniform(30001, 80000)},
        {"device_distinct_users_30d": rng.uniform(5, 15)},
        {"course_new_account_purchase_count_7d": rng.uniform(5, 20)},
        {"user_role_teacher_flag": 1, "course_is_student_only": 1, "student_only_purchase_count_30d": rng.uniform(3, 10)},
        {"student_id_blacklisted": 1, "id_card_blacklisted": 1, "device_id_blacklisted": 1},
    )
    row.update(patterns[kind % len(patterns)])
    return row


def _to_row(values: dict[str, float]) -> np.ndarray:
    return np.asarray([float(values.get(name, 0)) for name in FEATURE_COLUMNS], dtype=np.float32)


def gen_synthetic_dataset(
    n: int = 2000,
    pos_ratio: float = 0.35,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """生成正常样本和7类教育风险样本。"""
    if n < 20:
        raise ValueError("n 至少为20，才能进行分层训练和验证")
    if not 0 < pos_ratio < 1:
        raise ValueError("pos_ratio 必须在0和1之间")
    rng = np.random.default_rng(seed)
    n_pos = int(n * pos_ratio)
    rows = [_to_row(_risk_pattern(i, rng)) for i in range(n_pos)]
    rows.extend(_to_row(_normal(rng)) for _ in range(n - n_pos))
    labels = np.asarray([1] * n_pos + [0] * (n - n_pos), dtype=np.int32)
    order = rng.permutation(n)
    return np.vstack(rows)[order], labels[order]


def main() -> int:
    parser = argparse.ArgumentParser(description="训练教育风控XGBoost演示模型（无需MySQL）")
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--pos-ratio", type=float, default=0.35)
    parser.add_argument("--num-boost-round", type=int, default=120)
    parser.add_argument("--model-path", default=str(ROOT / "app" / "engine" / "xgb_model.json"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    X, y = gen_synthetic_dataset(args.n, args.pos_ratio, args.seed)
    metrics = train_and_save(
        X,
        y,
        model_path=args.model_path,
        num_boost_round=args.num_boost_round,
        early_stopping_rounds=10,
    )
    print(f"samples={len(y)}, positive={int(y.sum())}, positive_ratio={y.mean():.2%}")
    print(f"val_auc={metrics.get('val_auc', 0):.4f}")
    print(f"val_f1={metrics.get('val_f1', 0):.4f}")
    print(f"model={metrics['model_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
