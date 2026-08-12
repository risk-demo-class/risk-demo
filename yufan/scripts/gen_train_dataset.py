"""生成可重复的教育风控 XGBoost 训练集（25 维 + label）。"""

import argparse
import csv
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.engine.ml_model import FEATURE_COLUMNS  # noqa: E402


def _normal_sample(rng: random.Random) -> dict[str, float]:
    total_orders = rng.randint(1, 12)
    refunds = rng.choices([0, 1, 2], weights=[75, 22, 3])[0]
    total_amount = round(rng.uniform(300, 15000), 2)
    discount = round(rng.uniform(0, 300), 2)
    return {
        "user_total_orders": total_orders,
        "user_orders_30d": rng.randint(0, min(total_orders, 3)),
        "user_orders_7d": rng.randint(0, min(total_orders, 2)),
        "user_total_amount": total_amount,
        "user_avg_order_amount": round(total_amount / total_orders, 2),
        "user_max_order_amount": round(rng.uniform(300, min(8000, total_amount + 300)), 2),
        "user_refund_count": refunds,
        "user_postsale_count": 0 if refunds == 0 else rng.randint(0, refunds),
        "user_refund_rate": round(refunds / total_orders, 4),
        "user_postsale_rate": 0 if refunds == 0 else round(rng.uniform(0, 0.5), 4),
        "user_refund_amount": round(refunds * rng.uniform(100, 2500), 2),
        "user_cancel_count": rng.randint(0, 1),
        "user_complaint_count": 0,
        "user_address_count": rng.randint(1, 2),
        "order_total_amount": round(rng.uniform(99, 4999), 2),
        "order_item_count": 1,
        "order_sku_count": round(rng.uniform(1, 3000), 2),
        "order_discount_amount": discount,
        "order_discount_rate": round(rng.uniform(0, 0.25), 4),
        "order_pay_interval_sec": round(rng.uniform(0, 70), 2),
        "order_is_night": 1 if rng.random() < 0.08 else 0,
        "order_category_count": 1,
        "addr_total_count": rng.randint(1, 2),
        "addr_province_count": rng.randint(1, 2),
        "addr_is_new": 1 if rng.random() < 0.2 else 0,
    }


def _risk_sample(rng: random.Random) -> dict[str, float]:
    sample = _normal_sample(rng)
    pattern = rng.choice(("refund", "device", "reward", "big", "night", "proxy"))
    if pattern == "refund":
        sample.update(
            user_total_orders=rng.randint(3, 6),
            user_refund_count=rng.randint(3, 6),
            user_postsale_count=rng.randint(3, 6),
            user_refund_rate=round(rng.uniform(0.75, 1.0), 4),
            user_postsale_rate=round(rng.uniform(0.75, 1.0), 4),
            user_refund_amount=round(rng.uniform(20000, 60000), 2),
            order_sku_count=rng.randint(0, 5),
            order_discount_rate=round(rng.uniform(0.8, 1.0), 4),
        )
    elif pattern == "device":
        sample.update(
            addr_total_count=rng.randint(5, 15),
            addr_province_count=rng.randint(5, 15),
        )
    elif pattern == "reward":
        sample.update(
            user_complaint_count=rng.randint(1, 4),
            order_total_amount=round(rng.uniform(1000, 10000), 2),
        )
    elif pattern == "big":
        sample.update(
            user_orders_7d=rng.randint(4, 8),
            user_orders_30d=rng.randint(4, 12),
            user_total_amount=round(rng.uniform(30000, 90000), 2),
            user_max_order_amount=round(rng.uniform(10000, 25000), 2),
            order_total_amount=round(rng.uniform(10000, 25000), 2),
        )
    elif pattern == "night":
        sample.update(
            order_is_night=1,
            order_total_amount=round(rng.uniform(3000, 15000), 2),
        )
    else:
        sample.update(
            addr_total_count=rng.randint(5, 15),
            addr_province_count=rng.randint(4, 12),
            order_pay_interval_sec=round(rng.uniform(75, 100), 2),
            order_sku_count=round(rng.uniform(500, 3000), 2),
        )
    return sample


def generate_dataset(
    output: Path, samples: int = 2500, positive_ratio: float = 0.4, seed: int = 20260811
) -> tuple[int, int]:
    if samples < 100:
        raise ValueError("训练样本不能少于 100 条")
    if not 0.1 <= positive_ratio <= 0.9:
        raise ValueError("positive_ratio 必须在 0.1 到 0.9 之间")
    rng = random.Random(seed)
    rows = []
    positives = 0
    for _ in range(samples):
        label = 1 if rng.random() < positive_ratio else 0
        features = _risk_sample(rng) if label else _normal_sample(rng)
        # 少量标签噪声模拟真实审核差异，避免模型只记住机械阈值。
        if rng.random() < 0.02:
            label = 1 - label
        positives += label
        rows.append([features[name] for name in FEATURE_COLUMNS] + [label])
    rng.shuffle(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(FEATURE_COLUMNS + ["label"])
        writer.writerows(rows)
    return samples, positives


def main() -> None:
    parser = argparse.ArgumentParser(description="生成教育风控 25 维训练集")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "education_train_dataset.csv")
    parser.add_argument("--samples", type=int, default=2500)
    parser.add_argument("--positive-ratio", type=float, default=0.4)
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--reset", action="store_true", help="兼容旧命令；CSV 每次都会覆盖生成")
    args = parser.parse_args()
    total, positives = generate_dataset(args.output, args.samples, args.positive_ratio, args.seed)
    print(f"训练集已生成: {args.output}")
    print(f"样本={total}, 正例={positives} ({positives / total:.1%}), 负例={total - positives}")
    print(f"特征维度={len(FEATURE_COLUMNS)}, 标签列=label, seed={args.seed}")
    print("下一步: python scripts/train_xgb_model.py")


if __name__ == "__main__":
    main()
