"""
旅游风控系统 - 教学场景模型训练 (无需 DB, 纯 numpy 合成数据)
================
合成 6 种高风险模式 + 1 种正常模式:
  1. 高退改率 (user_refund_rate 高)
  2. 大额订单 (order_total_amount 高)
  3. 夜间下单 (order_is_night=1)
  4. 多出行人囤票 (traveler_* 高)
  5. 理赔骗保 (user_claim_count/rate 高)
  6. 多设备养号 (user_device_count 高)
  7. 正常用户

用法:
  python scripts/train_demo_model.py --n 2000
"""
import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS, train_and_save

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _gen_normal(n: int, rng: np.random.Generator) -> np.ndarray:
    """正常用户: 低退改率 / 小额订单 / 白天下单 / 1-2 设备 / 少出行人"""
    x = np.zeros((n, len(FEATURE_COLUMNS)), dtype=np.float32)
    for i in range(n):
        feats = dict.fromkeys(FEATURE_COLUMNS, 0.0)
        feats["user_total_bookings"] = rng.integers(2, 20)
        feats["user_bookings_7d"] = rng.integers(0, 2)
        feats["user_bookings_30d"] = rng.integers(0, 5)
        feats["user_total_amount"] = rng.uniform(500, 30000)
        feats["user_avg_order_amount"] = rng.uniform(200, 3000)
        feats["user_max_order_amount"] = rng.uniform(500, 8000)
        feats["user_refund_change_count"] = rng.integers(0, 1)
        feats["user_refund_rate"] = rng.uniform(0, 0.1)
        feats["user_refund_amount"] = rng.uniform(0, 1000)
        feats["user_claim_count"] = 0
        feats["user_claim_rate"] = 0
        feats["user_complaint_count"] = rng.integers(0, 1)
        feats["user_traveler_count"] = rng.integers(1, 4)
        feats["user_device_count"] = rng.integers(1, 2)
        feats["user_review_count"] = rng.integers(0, 3)
        feats["user_cancel_count"] = rng.integers(0, 1)
        feats["order_total_amount"] = rng.uniform(200, 8000)
        feats["order_item_count"] = rng.integers(1, 2)
        feats["order_traveler_count"] = rng.integers(1, 3)
        feats["order_discount_rate"] = rng.uniform(0, 0.2)
        feats["order_pay_interval_sec"] = rng.uniform(30, 600)
        feats["order_is_night"] = 0
        feats["order_lead_days"] = rng.uniform(10, 60)
        feats["order_trip_days"] = rng.integers(3, 9)
        feats["order_is_overseas"] = rng.integers(0, 2)
        feats["traveler_total_count"] = feats["order_traveler_count"]
        feats["traveler_phone_count"] = feats["order_traveler_count"]
        feats["traveler_new_count"] = rng.integers(0, 1)
        x[i] = [feats[c] for c in FEATURE_COLUMNS]
    return x


def _gen_high_refund(n: int, rng: np.random.Generator) -> np.ndarray:
    """高退改率"""
    x = _gen_normal(n, rng)
    for i in range(n):
        x[i, FEATURE_COLUMNS.index("user_refund_change_count")] = rng.integers(3, 10)
        x[i, FEATURE_COLUMNS.index("user_refund_rate")] = rng.uniform(0.5, 0.95)
        x[i, FEATURE_COLUMNS.index("user_refund_amount")] = rng.uniform(5000, 30000)
    return x


def _gen_big_order(n: int, rng: np.random.Generator) -> np.ndarray:
    """大额订单"""
    x = _gen_normal(n, rng)
    for i in range(n):
        x[i, FEATURE_COLUMNS.index("order_total_amount")] = rng.uniform(50000, 200000)
        x[i, FEATURE_COLUMNS.index("user_max_order_amount")] = rng.uniform(50000, 200000)
    return x


def _gen_night_order(n: int, rng: np.random.Generator) -> np.ndarray:
    """夜间下单"""
    x = _gen_normal(n, rng)
    for i in range(n):
        x[i, FEATURE_COLUMNS.index("order_is_night")] = 1
        x[i, FEATURE_COLUMNS.index("order_pay_interval_sec")] = rng.uniform(0, 5)
    return x


def _gen_many_travelers(n: int, rng: np.random.Generator) -> np.ndarray:
    """多出行人囤票"""
    x = _gen_normal(n, rng)
    for i in range(n):
        cnt = rng.integers(8, 20)
        x[i, FEATURE_COLUMNS.index("order_traveler_count")] = cnt
        x[i, FEATURE_COLUMNS.index("traveler_total_count")] = cnt
        x[i, FEATURE_COLUMNS.index("traveler_phone_count")] = cnt
        x[i, FEATURE_COLUMNS.index("traveler_new_count")] = cnt
        x[i, FEATURE_COLUMNS.index("user_traveler_count")] = cnt + rng.integers(0, 10)
    return x


def _gen_claim_fraud(n: int, rng: np.random.Generator) -> np.ndarray:
    """理赔骗保"""
    x = _gen_normal(n, rng)
    for i in range(n):
        x[i, FEATURE_COLUMNS.index("user_claim_count")] = rng.integers(3, 8)
        x[i, FEATURE_COLUMNS.index("user_claim_rate")] = rng.uniform(0.3, 0.9)
    return x


def _gen_device_farm(n: int, rng: np.random.Generator) -> np.ndarray:
    """多设备养号"""
    x = _gen_normal(n, rng)
    for i in range(n):
        x[i, FEATURE_COLUMNS.index("user_device_count")] = rng.integers(5, 12)
    return x


def main(n: int = 2000):
    rng = np.random.default_rng(42)
    patterns = [
        (_gen_high_refund, 0.20),
        (_gen_big_order, 0.20),
        (_gen_night_order, 0.15),
        (_gen_many_travelers, 0.15),
        (_gen_claim_fraud, 0.15),
        (_gen_device_farm, 0.15),
    ]
    n_risk = int(n * 0.5)
    X_parts = []
    y_parts = []
    for gen_fn, ratio in patterns:
        cnt = int(n_risk * ratio)
        X_parts.append(gen_fn(cnt, rng))
        y_parts.append(np.ones(cnt, dtype=np.int32))
    n_normal = n - n_risk
    X_parts.append(_gen_normal(n_normal, rng))
    y_parts.append(np.zeros(n_normal, dtype=np.int32))

    X = np.vstack(X_parts).astype(np.float32)
    y = np.concatenate(y_parts)
    logger.info("合成数据: %s, 正例 %.1f%%", X.shape, 100 * y.mean())

    model_path = os.path.join(PROJECT_ROOT, settings.XGB_MODEL_PATH)
    metrics, booster = train_and_save(
        X, y, model_path=model_path, num_boost_round=300, return_model=True,
    )
    print("\n" + "=" * 60)
    print("Demo 模型训练报告:")
    for k, v in metrics.items():
        print(f"  {k:<18} = {v}")
    importance = booster.get_score(importance_type="gain")
    top = sorted(importance.items(), key=lambda kv: kv[1], reverse=True)[:10]
    print("\n特征重要性 Top 10:")
    for fname, gain in top:
        print(f"  {fname:<30} {gain:.2f}")
    print("=" * 60)
    print(f"模型已保存: {model_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="教学场景合成数据训练")
    parser.add_argument("--n", type=int, default=2000)
    args = parser.parse_args()
    main(args.n)
