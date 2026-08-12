"""
制造业风控系统 - 教学场景 XGBoost 演示模型训练 (P4-L4 2026-08-08)

【目的】
  不依赖 DB, 纯 numpy 合成 2000 样本, 训练一个针对 16 条制造业规则 + 25 特征的合理 XGBoost 模型.
  训完保存到 app/engine/xgb_model.json, run_app.py 启动时直接加载.

【8 种制造业高风险模式】
  1. 跨区串货 (cross_report_count 高 + 跨区发货)
  2. 保修期外高频保修 (out_warranty + warranty_30d)
  3. 大额囤货 (order_quantity > 100)
  4. 套保嫌疑 (warranty_90d >= 2)
  5. 新经销商大单 (contract_age < 30 + quantity > 50)
  6. 维修费用异常 (repair_cost_ratio > 0.6)
  7. 资质过期 (contract_expired = 1)
  8. 综合黑经销商 (多特征偏高)

【用法】
  python scripts/train_demo_model.py                    # 默认 2000 样本
  python scripts/train_demo_model.py --n 5000
"""
import argparse
import os
import random
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import numpy as np

from app.engine.ml_model import FEATURE_COLUMNS, train_and_save

N_FEATURES = len(FEATURE_COLUMNS)
assert N_FEATURES == 25, f"必须是 25 维特征, 实际 {N_FEATURES}"


def _base(rng: random.Random) -> dict:
    """25 维基础特征 dict (低风险), 供风险模式覆盖."""
    return {
        "user_total_orders": rng.uniform(2, 8),
        "user_orders_30d": rng.uniform(0, 2),
        "user_orders_7d": rng.uniform(0, 1),
        "user_total_amount": rng.uniform(20000, 80000),
        "user_avg_order_amount": rng.uniform(2000, 10000),
        "user_max_order_amount": rng.uniform(3000, 15000),
        "user_warranty_count": rng.uniform(0, 2),
        "user_warranty_rate": rng.uniform(0, 0.2),
        "user_repair_cost_total": rng.uniform(0, 5000),
        "user_out_warranty_count": rng.uniform(0, 1),
        "user_cross_report_count": rng.uniform(0, 1),
        "user_contract_age_days": rng.uniform(90, 800),
        "order_total_amount": rng.uniform(10000, 80000),
        "order_quantity": rng.uniform(1, 30),
        "order_unit_price": rng.uniform(3000, 8000),
        "order_is_night": 0.0 if rng.random() < 0.9 else 1.0,
        "order_is_cross_region": 0.0,
        "order_contract_expired": 0.0,
        "order_warranty_30d": rng.uniform(0, 1),
        "order_warranty_90d": rng.uniform(0, 1),
        "order_repair_cost_ratio": rng.uniform(0, 0.2),
        "order_cross_report_count": rng.uniform(0, 1),
        "addr_ship_region_count": rng.uniform(1, 3),
        "addr_dealer_region_count": 1.0,
        "addr_ship_is_new": 0.0 if rng.random() < 0.8 else 1.0,
    }


def _to_array(f: dict) -> np.ndarray:
    """按 FEATURE_COLUMNS 固定顺序转 25 维数组 (训练/推理对齐)."""
    return np.array([f[col] for col in FEATURE_COLUMNS], dtype=np.float32)


def _gen_cross_region(rng: random.Random) -> np.ndarray:
    """模式 1: 跨区串货"""
    f = _base(rng)
    f["user_cross_report_count"] = rng.uniform(2, 5)
    f["order_is_cross_region"] = 1.0
    f["order_cross_report_count"] = rng.uniform(1, 3)
    f["addr_ship_region_count"] = rng.uniform(3, 6)
    return _to_array(f)


def _gen_out_warranty(rng: random.Random) -> np.ndarray:
    """模式 2: 保修期外高频保修"""
    f = _base(rng)
    f["user_out_warranty_count"] = rng.uniform(1, 3)
    f["order_warranty_30d"] = rng.uniform(2, 4)
    f["user_warranty_count"] = rng.uniform(3, 8)
    return _to_array(f)


def _gen_bulk_order(rng: random.Random) -> np.ndarray:
    """模式 3: 大额囤货"""
    f = _base(rng)
    qty = rng.uniform(110, 200)
    f["order_quantity"] = qty
    f["order_total_amount"] = qty * rng.uniform(3000, 6000)
    f["order_unit_price"] = f["order_total_amount"] / qty
    return _to_array(f)


def _gen_warranty_abuse(rng: random.Random) -> np.ndarray:
    """模式 4: 套保嫌疑"""
    f = _base(rng)
    f["order_warranty_90d"] = rng.uniform(2, 5)
    f["user_warranty_count"] = rng.uniform(3, 8)
    f["user_warranty_rate"] = rng.uniform(0.4, 0.8)
    return _to_array(f)


def _gen_new_dealer(rng: random.Random) -> np.ndarray:
    """模式 5: 新经销商大单"""
    f = _base(rng)
    f["user_total_orders"] = rng.uniform(1, 2)
    f["user_contract_age_days"] = rng.uniform(3, 25)
    qty = rng.uniform(60, 100)
    f["order_quantity"] = qty
    f["order_total_amount"] = qty * rng.uniform(3000, 6000)
    f["order_unit_price"] = f["order_total_amount"] / qty
    return _to_array(f)


def _gen_repair_cost(rng: random.Random) -> np.ndarray:
    """模式 6: 维修费用异常"""
    f = _base(rng)
    f["order_repair_cost_ratio"] = rng.uniform(0.65, 0.9)
    f["user_repair_cost_total"] = rng.uniform(80000, 300000)
    return _to_array(f)


def _gen_contract_expired(rng: random.Random) -> np.ndarray:
    """模式 7: 资质过期"""
    f = _base(rng)
    f["order_contract_expired"] = 1.0
    f["user_contract_age_days"] = rng.uniform(400, 700)
    return _to_array(f)


def _gen_mixed_black(rng: random.Random) -> np.ndarray:
    """模式 8: 综合黑经销商"""
    f = _base(rng)
    f["user_cross_report_count"] = rng.uniform(3, 6)
    f["user_total_orders"] = rng.uniform(5, 20)
    f["order_is_cross_region"] = 1.0
    f["order_contract_expired"] = 1.0
    f["addr_ship_region_count"] = rng.uniform(4, 8)
    return _to_array(f)


def _gen_normal(rng: random.Random) -> np.ndarray:
    """正常经销商 (低风险)."""
    f = _base(rng)
    f["user_total_orders"] = rng.uniform(3, 10)
    f["order_total_amount"] = rng.uniform(20000, 80000)
    f["order_quantity"] = rng.uniform(1, 20)
    return _to_array(f)


POSITIVE_PATTERNS = [
    _gen_cross_region, _gen_out_warranty, _gen_bulk_order, _gen_warranty_abuse,
    _gen_new_dealer, _gen_repair_cost, _gen_contract_expired, _gen_mixed_black,
]
NEGATIVE_PATTERN = _gen_normal


def gen_synthetic_dataset(n: int = 2000, pos_ratio: float = 0.5, seed: int = 42):
    rng = random.Random(seed)
    np.random.seed(seed)

    n_pos = int(n * pos_ratio)
    n_neg = n - n_pos
    X = np.zeros((n, N_FEATURES), dtype=np.float32)
    y = np.zeros(n, dtype=np.int32)

    for i in range(n_pos):
        X[i] = POSITIVE_PATTERNS[i % len(POSITIVE_PATTERNS)](rng)
        y[i] = 1
    for i in range(n_neg):
        X[n_pos + i] = NEGATIVE_PATTERN(rng)

    perm = np.random.permutation(n)
    return X[perm], y[perm]


def main():
    parser = argparse.ArgumentParser(description="制造业风控 - 合成数据训练演示模型")
    parser.add_argument("--n", type=int, default=2000, help="样本数 (默认 2000)")
    parser.add_argument("--pos-ratio", type=float, default=0.5, help="正例比例 (默认 0.5)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print("=" * 60)
    print("制造业风控 - 合成数据训练 XGBoost 演示模型")
    print(f"样本数: {args.n}, 正例比例: {args.pos_ratio:.0%}")
    print("=" * 60)

    X, y = gen_synthetic_dataset(n=args.n, pos_ratio=args.pos_ratio, seed=args.seed)
    print(f"特征维度: {X.shape[1]} (跟 FEATURE_COLUMNS 一致: {N_FEATURES})")

    metrics, booster = train_and_save(
        X, y,
        model_path=os.path.join(PROJECT_ROOT, "app/engine/xgb_model.json"),
        num_boost_round=200,
        return_model=True,
    )

    print("=" * 60)
    print("训练完成! 指标:")
    for k, v in metrics.items():
        print(f"  {k:<16} {v}")
    print(f"模型已保存: {os.path.join(PROJECT_ROOT, 'app/engine/xgb_model.json')}")


if __name__ == "__main__":
    main()
