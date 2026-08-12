"""生成可解释的教育风控训练样本并训练 XGBoost 模型。

标签约定与 ml_model.py 一致：0=通过/标记，1=人工审核/拒绝。
脚本不依赖 MySQL，固定随机种子时 CSV、标签分布和模型训练输入可复现。
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.engine.feature import FEATURE_NAMES
from app.engine.ml_model import train_and_save


SCENARIO_WEIGHTS: tuple[tuple[str, float], ...] = (
    ("正常报名", 0.42),
    ("正常学历认证", 0.08),
    ("正常退费", 0.08),
    ("凌晨大额标记", 0.08),
    ("零学时大额退费", 0.07),
    ("连环退费", 0.07),
    ("极高退费率", 0.06),
    ("同设备多账号", 0.05),
    ("新设备大额报名", 0.04),
    ("身份连续认证失败", 0.03),
    ("超高金额报名", 0.02),
)

POSITIVE_SCENARIOS = {
    "零学时大额退费",
    "连环退费",
    "极高退费率",
    "同设备多账号",
    "新设备大额报名",
    "身份连续认证失败",
    "超高金额报名",
}


def _pick_scenario(rng: random.Random) -> str:
    point = rng.random()
    cumulative = 0.0
    for scenario, weight in SCENARIO_WEIGHTS:
        cumulative += weight
        if point <= cumulative:
            return scenario
    return SCENARIO_WEIGHTS[-1][0]


def _base_features(rng: random.Random) -> dict[str, float]:
    total_orders = rng.randint(1, 12)
    orders_30d = rng.randint(0, min(total_orders, 5))
    orders_7d = rng.randint(0, min(orders_30d, 2))
    average_amount = rng.uniform(300, 3500)
    total_amount = average_amount * total_orders
    refund_count = 1 if total_orders >= 4 and rng.random() < 0.08 else 0
    refund_apply_count = refund_count + (1 if rng.random() < 0.05 else 0)
    order_amount = rng.uniform(300, 4500)
    discount_rate = rng.uniform(0, 0.18)
    discount_amount = order_amount * discount_rate
    categories = rng.randint(1, min(total_orders, 5))
    device_count = rng.randint(1, 3)

    return {
        "user_total_orders": float(total_orders),
        "user_orders_30d": float(orders_30d),
        "user_orders_7d": float(orders_7d),
        "user_total_amount": round(total_amount, 2),
        "user_avg_order_amount": round(average_amount, 2),
        "user_max_order_amount": round(max(order_amount, average_amount * rng.uniform(1.0, 2.2)), 2),
        "user_refund_count": float(refund_count),
        "user_postsale_count": float(refund_apply_count),
        "user_refund_rate": round(refund_count / total_orders, 4),
        "user_postsale_rate": round(min(refund_apply_count / total_orders, 1.0), 4),
        "user_refund_amount": round(refund_count * rng.uniform(300, 3000), 2),
        "user_cancel_count": float(1 if rng.random() < 0.12 else 0),
        "user_complaint_count": 0.0,
        "user_address_count": float(device_count),
        "order_total_amount": round(order_amount, 2),
        "order_item_count": 1.0,
        "order_sku_count": 1.0,
        "order_discount_amount": round(discount_amount, 2),
        "order_discount_rate": round(discount_rate, 4),
        "order_pay_interval_sec": round(rng.uniform(30, 2400), 2),
        "order_is_night": 1.0 if rng.random() < 0.04 else 0.0,
        "order_category_count": float(categories),
        "addr_total_count": float(device_count),
        "addr_province_count": float(rng.randint(1, 2)),
        "addr_is_new": 1.0 if rng.random() < 0.12 else 0.0,
    }


def _apply_scenario(features: dict[str, float], scenario: str, rng: random.Random) -> None:
    if scenario == "正常学历认证":
        features["user_complaint_count"] = 0.0
        for key in (
            "order_total_amount", "order_item_count", "order_sku_count",
            "order_discount_amount", "order_discount_rate", "order_pay_interval_sec",
        ):
            features[key] = 0.0

    elif scenario == "正常退费":
        features["user_postsale_count"] = max(features["user_postsale_count"], 1.0)
        features["order_pay_interval_sec"] = rng.uniform(120, 1800)
        features["order_total_amount"] = rng.uniform(500, 3500)

    elif scenario == "凌晨大额标记":
        features["order_is_night"] = 1.0
        features["order_total_amount"] = rng.uniform(5000, 9500)

    elif scenario == "零学时大额退费":
        features["order_pay_interval_sec"] = rng.uniform(0, 4.8)
        features["order_total_amount"] = rng.uniform(1000, 12000)
        features["user_postsale_count"] = max(features["user_postsale_count"], 1.0)

    elif scenario == "连环退费":
        total_orders = rng.randint(4, 15)
        successful = rng.randint(3, min(total_orders, 7))
        features["user_total_orders"] = float(total_orders)
        features["user_postsale_count"] = float(rng.randint(3, max(3, total_orders)))
        features["user_refund_count"] = float(successful)
        features["user_refund_amount"] = rng.uniform(10000, 35000)
        features["user_refund_rate"] = round(successful / total_orders, 4)
        features["user_postsale_rate"] = round(min(features["user_postsale_count"] / total_orders, 1), 4)

    elif scenario == "极高退费率":
        total_orders = rng.randint(3, 12)
        successful = rng.randint((total_orders + 1) // 2, total_orders)
        features["user_total_orders"] = float(total_orders)
        features["user_refund_count"] = float(successful)
        features["user_postsale_count"] = float(max(successful, int(features["user_postsale_count"])))
        features["user_refund_rate"] = round(successful / total_orders, 4)
        features["user_postsale_rate"] = round(min(features["user_postsale_count"] / total_orders, 1), 4)
        features["user_refund_amount"] = max(features["user_refund_amount"], rng.uniform(5000, 30000))

    elif scenario == "同设备多账号":
        features["addr_province_count"] = float(rng.randint(5, 15))
        features["addr_is_new"] = float(rng.randint(0, 1))

    elif scenario == "新设备大额报名":
        features["addr_is_new"] = 1.0
        features["order_total_amount"] = rng.uniform(10000, 28000)
        features["addr_province_count"] = float(rng.randint(1, 3))

    elif scenario == "身份连续认证失败":
        features["user_complaint_count"] = float(rng.randint(2, 6))
        # 学历认证事件通常没有当前订单。
        for key in (
            "order_total_amount", "order_item_count", "order_sku_count",
            "order_discount_amount", "order_discount_rate", "order_pay_interval_sec",
        ):
            features[key] = 0.0

    elif scenario == "超高金额报名":
        features["order_total_amount"] = rng.uniform(30000, 60000)
        features["user_max_order_amount"] = max(
            features["user_max_order_amount"], features["order_total_amount"]
        )


def generate_training_set(
    rows: int = 2500,
    seed: int = 20260811,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """生成 25 维训练矩阵、二分类标签和场景名称。"""
    if rows < 100:
        raise ValueError("训练样本至少需要 100 条")
    rng = random.Random(seed)
    samples: list[list[float]] = []
    labels: list[int] = []
    scenarios: list[str] = []

    for _ in range(rows):
        scenario = _pick_scenario(rng)
        features = _base_features(rng)
        _apply_scenario(features, scenario, rng)
        label = 1 if scenario in POSITIVE_SCENARIOS else 0
        # 2% 审核噪声，避免教学模型得到不真实的完美边界。
        if rng.random() < 0.02:
            label = 1 - label
        samples.append([float(features[name]) for name in FEATURE_NAMES])
        labels.append(label)
        scenarios.append(scenario)

    X = np.asarray(samples, dtype=np.float32)
    y = np.asarray(labels, dtype=np.int32)
    if X.shape != (rows, 25) or len(np.unique(y)) != 2:
        raise ValueError(f"训练数据形状或标签异常: X={X.shape}, labels={np.unique(y)}")
    return X, y, scenarios


def write_csv(path: Path, X: np.ndarray, y: np.ndarray, scenarios: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([*FEATURE_NAMES, "label", "scenario"])
        for vector, label, scenario in zip(X, y, scenarios):
            writer.writerow([*[f"{float(value):.4f}" for value in vector], int(label), scenario])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="训练教育行业 XGBoost 风控模型")
    parser.add_argument("--rows", type=int, default=2500, help="样本数，默认2500")
    parser.add_argument("--seed", type=int, default=20260811, help="随机种子")
    parser.add_argument("--rounds", type=int, default=200, help="最大训练轮数")
    parser.add_argument("--csv", type=Path, default=PROJECT_ROOT / "data" / "education_training_data.csv")
    parser.add_argument("--model", type=Path, default=PROJECT_ROOT / "app" / "engine" / "xgb_model.json")
    parser.add_argument("--metrics", type=Path, default=PROJECT_ROOT / "data" / "education_model_metrics.json")
    parser.add_argument("--dry-run", action="store_true", help="只生成并检查，不写文件、不训练")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    X, y, scenarios = generate_training_set(rows=args.rows, seed=args.seed)
    scenario_counts = Counter(scenarios)
    print(f"训练数据: X={X.shape}, 正例={int(y.sum())}/{len(y)} ({100 * y.mean():.1f}%)")
    for scenario, count in scenario_counts.most_common():
        print(f"  {scenario:<16} {count:>4} 条")

    if args.dry_run:
        return 0

    write_csv(args.csv, X, y, scenarios)
    args.model.parent.mkdir(parents=True, exist_ok=True)
    metrics, model = train_and_save(
        X,
        y,
        model_path=str(args.model),
        num_boost_round=args.rounds,
        early_stopping_rounds=10,
        return_model=True,
    )
    importance = model.get_score(importance_type="gain") if model is not None else {}
    metrics["feature_count"] = len(FEATURE_NAMES)
    metrics["seed"] = args.seed
    metrics["scenario_counts"] = dict(sorted(scenario_counts.items()))
    metrics["top_features"] = [
        {"feature": name, "gain": round(float(gain), 4)}
        for name, gain in sorted(importance.items(), key=lambda item: -item[1])[:10]
    ]
    args.metrics.parent.mkdir(parents=True, exist_ok=True)
    args.metrics.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        "模型完成: "
        f"val_auc={metrics.get('val_auc', 0):.4f}, "
        f"val_f1={metrics.get('val_f1', 0):.4f}, "
        f"model={args.model}"
    )
    print(f"训练CSV: {args.csv}")
    print(f"指标文件: {args.metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
