"""
生成模拟正负样本 CSV, 供本地训练 XGBoost.

正样本覆盖: 黄牛囤票 / 退改套利 / 跨境大额 / 签证黑产 / 设备多账号 / LLM 暗号.
"""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import settings
from app.engine.feature_registry import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _positive_row(rng: np.random.Generator, uid: str) -> dict:
    """生成一个正样本特征行."""
    noise = rng.normal(0, 0.15)
    return {
        "user_total_orders": rng.integers(2, 30),
        "user_orders_30d": rng.integers(1, 20),
        "user_orders_7d": rng.integers(1, 12),
        "user_total_amount": rng.uniform(6000, 120000),
        "user_avg_order_amount": rng.uniform(2000, 30000),
        "user_max_order_amount": rng.uniform(5000, 80000),
        "user_cancel_count": rng.integers(0, 5),
        "user_refund_count": rng.integers(1, 10),
        "user_refund_rate": max(0.0, min(0.95, rng.uniform(0.15, 0.9) + noise)),
        "user_refund_amount": rng.uniform(800, 60000),
        "user_visa_reject_90d": rng.integers(0, 4),
        "user_visa_countries_30d": rng.integers(1, 5),
        "user_passenger_id_count": rng.integers(2, 20),
        "user_device_count": rng.integers(1, 8),
        "order_total_amount": rng.uniform(6000, 80000),
        "order_passenger_count": rng.integers(2, 8),
        "order_hotel_room_count": rng.integers(1, 8),
        "order_flight_count": rng.integers(1, 4),
        "order_trip_days": rng.integers(2, 14),
        "order_days_to_departure": rng.integers(0, 20),
        "order_is_night": rng.choice([0, 1], p=[0.6, 0.4]),
        "order_dest_risk_score": rng.choice([0, 20, 80], p=[0.7, 0.15, 0.15]),
        "order_preauth_diff": rng.uniform(0, 5000),
        "order_group_member_count": rng.integers(0, 20),
        "device_user_count_7d": rng.integers(1, 10),
        "device_hotel_account_count": rng.integers(0, 8),
        "same_pay_account_1h_orders": rng.integers(2, 12),
        "same_flight_1h_bookings": rng.integers(2, 12),
        "user_consecutive_refund_change": rng.integers(1, 8),
        "passenger_match_rate": max(0.0, min(1.0, rng.uniform(0.0, 0.85) + noise)),
        "remark_llm_score": max(0.0, min(100.0, rng.uniform(50, 100) + noise * 30)),
        "remark_scalper_flag": rng.choice([0, 1], p=[0.45, 0.55]),
        "remark_illegal_group_buy_flag": rng.choice([0, 1], p=[0.55, 0.45]),
        "label": 1,
        "user_id": uid,
        "order_id": f"ORD_POS_{uid}",
        "event_type": "下单",
    }


def _negative_row(rng: np.random.Generator, uid: str) -> dict:
    """生成一个负样本特征行."""
    noise = rng.normal(0, 0.1)
    return {
        "user_total_orders": rng.integers(0, 10),
        "user_orders_30d": rng.integers(0, 5),
        "user_orders_7d": rng.integers(0, 2),
        "user_total_amount": rng.uniform(500, 35000),
        "user_avg_order_amount": rng.uniform(500, 7000),
        "user_max_order_amount": rng.uniform(1000, 15000),
        "user_cancel_count": rng.integers(0, 2),
        "user_refund_count": rng.integers(0, 3),
        "user_refund_rate": max(0.0, min(0.3, rng.uniform(0.0, 0.2) + noise)),
        "user_refund_amount": rng.uniform(0, 4000),
        "user_visa_reject_90d": rng.integers(0, 2),
        "user_visa_countries_30d": rng.integers(0, 2),
        "user_passenger_id_count": rng.integers(1, 6),
        "user_device_count": rng.integers(1, 3),
        "order_total_amount": rng.uniform(500, 10000),
        "order_passenger_count": rng.integers(1, 4),
        "order_hotel_room_count": rng.integers(1, 3),
        "order_flight_count": rng.integers(1, 2),
        "order_trip_days": rng.integers(2, 7),
        "order_days_to_departure": rng.integers(5, 60),
        "order_is_night": rng.choice([0, 1], p=[0.9, 0.1]),
        "order_dest_risk_score": rng.choice([0, 20], p=[0.9, 0.1]),
        "order_preauth_diff": rng.uniform(0, 500),
        "order_group_member_count": rng.integers(0, 5),
        "device_user_count_7d": rng.integers(1, 3),
        "device_hotel_account_count": rng.integers(0, 3),
        "same_pay_account_1h_orders": rng.integers(1, 4),
        "same_flight_1h_bookings": rng.integers(1, 4),
        "user_consecutive_refund_change": rng.integers(0, 3),
        "passenger_match_rate": max(0.0, min(1.0, rng.uniform(0.7, 1.0) + noise)),
        "remark_llm_score": max(0.0, min(50.0, rng.uniform(0, 30) + noise * 20)),
        "remark_scalper_flag": 0,
        "remark_illegal_group_buy_flag": 0,
        "label": 0,
        "user_id": uid,
        "order_id": f"ORD_NEG_{uid}",
        "event_type": "下单",
    }


def gen_train_csv(n: int = 2000, pos_ratio: float = 0.3, seed: int = 42) -> Path:
    """生成训练 CSV."""
    try:
        rng = np.random.default_rng(seed)
        pos_n = int(n * pos_ratio)
        neg_n = n - pos_n
        rows = [
            _positive_row(rng, f"U_POS_{i}")
            for i in range(pos_n)
        ] + [
            _negative_row(rng, f"U_NEG_{i}")
            for i in range(neg_n)
        ]
        rng.shuffle(rows)
        df = pd.DataFrame(rows)
        # 保证列顺序固定
        df = df[["user_id", "order_id", "event_type", "label", *FEATURE_COLUMNS]]
        path = PROJECT_ROOT / settings.TRAIN_CSV_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8")
        logger.info("训练 CSV 生成完成: %s rows=%d pos=%d neg=%d", path, n, pos_n, neg_n)
        return path
    except Exception:
        logger.exception("训练 CSV 生成失败")
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="生成训练 CSV")
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--pos-ratio", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    gen_train_csv(args.n, args.pos_ratio, args.seed)


if __name__ == "__main__":
    main()
