"""
制造业风控系统 - 教学场景 XGBoost 演示模型训练

【目的】
  不依赖 DB, 纯 numpy 合成样本, 训练一个针对制造业规则 + 25 特征的合理 XGBoost 模型.
  训完保存到 app/engine/xgb_model.json, run_app.py 启动时直接加载.

【6 种制造业高风险模式】 (跟 rules 对应)
  1. 高保修率       (保修率 > 0.8, 保修次数 > 5 → R015)
  2. 30天高频订货   (orders_30d >= 30 → R007)
  3. 套保+维修费    (同一 SN 90 天 2 次维修 + 费用 > 60%MSRP → R008/R018)
  4. 跨区串货       (被举报 >= 2 次 + 跨区发货 → R001/R026)
  5. 新经销商大单   (历史订单 <= 2 + 订单 >= 50万 → R012/R005)
  6. 混合高风险     (多种特征都偏高)

【用法】
  python scripts/train_demo_model.py
"""
import argparse
import os
import random
import sys

# UTF-8 stdout
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS


# 25 维特征顺序 (跟 FEATURE_COLUMNS 一致)
FEATURE_NAMES = FEATURE_COLUMNS
N_FEATURES = len(FEATURE_NAMES)
assert N_FEATURES == 25, f"必须是 25 维特征, 实际 {N_FEATURES}"


def _gen_high_warranty_rate(rng: random.Random) -> np.ndarray:
    """模式 1: 高保修率 (触发 R015 保修率>=80% 且 订单>=3)"""
    return np.array([
        rng.uniform(5, 15),       # user_total_orders
        rng.uniform(2, 10),       # user_orders_30d
        rng.uniform(1, 5),        # user_orders_7d
        rng.uniform(300000, 2000000),  # user_total_amount
        rng.uniform(30000, 200000),    # user_avg_order_amount
        rng.uniform(100000, 600000),   # user_max_order_amount
        rng.uniform(6, 15),       # user_warranty_count  ← 高
        rng.uniform(2, 8),        # user_repair_count
        rng.uniform(0.8, 1.0),    # user_warranty_rate   ← 高
        rng.uniform(0, 1),        # user_dealer_contract_expired
        rng.uniform(0, 2),        # user_cancel_count
        rng.uniform(0, 3),        # user_report_count
        rng.uniform(80000, 500000),    # order_total_amount
        rng.uniform(1, 6),        # order_quantity
        rng.uniform(50000, 250000),    # order_unit_price
        rng.uniform(0.7, 1.0),    # order_msrp_ratio
        0.0 if rng.random() < 0.8 else 1.0,  # order_is_night
        1.0,                     # order_ship_region_match
        rng.uniform(0, 1),        # order_sn_repair_count_90d
        rng.uniform(0, 1),        # order_report_count
        rng.uniform(0, 0.3),      # order_repair_cost_ratio
        0.0,                     # order_is_out_of_warranty
        rng.uniform(1, 3),        # addr_region_total
        rng.uniform(0, 1),        # addr_region_cross_count
        0.0 if rng.random() < 0.7 else 1.0,  # addr_is_new_region
    ], dtype=np.float32)


def _gen_high_freq_order(rng: random.Random) -> np.ndarray:
    """模式 2: 30 天高频订货 (触发 R007 orders_30d >= 30)"""
    return np.array([
        rng.uniform(30, 60),      # user_total_orders
        rng.uniform(30, 50),      # user_orders_30d  ← 高
        rng.uniform(8, 20),       # user_orders_7d
        rng.uniform(500000, 3000000),  # user_total_amount
        rng.uniform(15000, 60000),     # user_avg_order_amount
        rng.uniform(80000, 400000),    # user_max_order_amount
        rng.uniform(0, 3),        # user_warranty_count
        rng.uniform(0, 2),        # user_repair_count
        rng.uniform(0, 0.1),      # user_warranty_rate
        0.0,                     # user_dealer_contract_expired
        rng.uniform(0, 3),        # user_cancel_count
        rng.uniform(0, 2),        # user_report_count
        rng.uniform(30000, 150000),    # order_total_amount
        rng.uniform(2, 10),       # order_quantity
        rng.uniform(8000, 80000),      # order_unit_price
        rng.uniform(0.7, 1.0),    # order_msrp_ratio
        rng.uniform(0, 1),        # order_is_night
        1.0,                     # order_ship_region_match
        rng.uniform(0, 1),        # order_sn_repair_count_90d
        rng.uniform(0, 1),        # order_report_count
        rng.uniform(0, 0.2),      # order_repair_cost_ratio
        0.0,                     # order_is_out_of_warranty
        rng.uniform(1, 2),        # addr_region_total
        0.0,                     # addr_region_cross_count
        0.0 if rng.random() < 0.8 else 1.0,  # addr_is_new_region
    ], dtype=np.float32)


def _gen_warranty_fraud(rng: random.Random) -> np.ndarray:
    """模式 3: 套保+维修费用异常 (触发 R008 SN 90 天 2 次维修 / R018 费用>60%MSRP)"""
    return np.array([
        rng.uniform(3, 10),       # user_total_orders
        rng.uniform(1, 5),        # user_orders_30d
        rng.uniform(0, 2),        # user_orders_7d
        rng.uniform(150000, 1000000),  # user_total_amount
        rng.uniform(40000, 150000),    # user_avg_order_amount
        rng.uniform(90000, 300000),    # user_max_order_amount
        rng.uniform(3, 8),        # user_warranty_count
        rng.uniform(2, 6),        # user_repair_count  ← 高
        rng.uniform(0.4, 0.9),    # user_warranty_rate
        rng.uniform(0, 1),        # user_dealer_contract_expired
        rng.uniform(0, 1),        # user_cancel_count
        rng.uniform(0, 2),        # user_report_count
        rng.uniform(90000, 300000),    # order_total_amount
        rng.uniform(1, 3),        # order_quantity
        rng.uniform(80000, 120000),    # order_unit_price
        rng.uniform(0.8, 1.0),    # order_msrp_ratio
        0.0,                     # order_is_night
        1.0,                     # order_ship_region_match
        rng.uniform(2, 5),        # order_sn_repair_count_90d  ← 高
        rng.uniform(0, 1),        # order_report_count
        rng.uniform(0.6, 0.95),   # order_repair_cost_ratio  ← 高
        0.0,                     # order_is_out_of_warranty
        rng.uniform(1, 2),        # addr_region_total
        0.0,                     # addr_region_cross_count
        0.0 if rng.random() < 0.7 else 1.0,  # addr_is_new_region
    ], dtype=np.float32)


def _gen_cross_region(rng: random.Random) -> np.ndarray:
    """模式 4: 跨区串货 (触发 R001 举报>=2 / R026 跨区大单)"""
    return np.array([
        rng.uniform(5, 20),       # user_total_orders
        rng.uniform(2, 8),        # user_orders_30d
        rng.uniform(0, 3),        # user_orders_7d
        rng.uniform(500000, 3000000),  # user_total_amount
        rng.uniform(80000, 250000),    # user_avg_order_amount
        rng.uniform(300000, 1200000),  # user_max_order_amount
        rng.uniform(0, 2),        # user_warranty_count
        rng.uniform(0, 1),        # user_repair_count
        rng.uniform(0, 0.15),     # user_warranty_rate
        0.0,                     # user_dealer_contract_expired
        rng.uniform(0, 2),        # user_cancel_count
        rng.uniform(3, 8),        # user_report_count  ← 高
        rng.uniform(300000, 1000000),  # order_total_amount  ← 高
        rng.uniform(1, 5),        # order_quantity
        rng.uniform(200000, 320000),   # order_unit_price
        rng.uniform(0.8, 1.0),    # order_msrp_ratio
        rng.uniform(0, 1),        # order_is_night
        0.0,                     # order_ship_region_match  ← 跨区
        rng.uniform(0, 1),        # order_sn_repair_count_90d
        rng.uniform(2, 6),        # order_report_count  ← 高
        rng.uniform(0, 0.2),      # order_repair_cost_ratio
        0.0,                     # order_is_out_of_warranty
        rng.uniform(2, 5),        # addr_region_total
        rng.uniform(2, 6),        # addr_region_cross_count  ← 高
        0.0 if rng.random() < 0.5 else 1.0,  # addr_is_new_region
    ], dtype=np.float32)


def _gen_new_dealer_big_order(rng: random.Random) -> np.ndarray:
    """模式 5: 新经销商大单 (触发 R012 订单<=2 + >=50万 / R005 >=100万)"""
    return np.array([
        rng.uniform(1, 2),        # user_total_orders  ← 低 (新)
        rng.uniform(0, 2),        # user_orders_30d
        rng.uniform(0, 1),        # user_orders_7d
        rng.uniform(500000, 2000000),  # user_total_amount
        rng.uniform(400000, 1200000),  # user_avg_order_amount
        rng.uniform(500000, 1500000),  # user_max_order_amount  ← 高
        rng.uniform(0, 1),        # user_warranty_count
        0.0,                     # user_repair_count
        0.0,                     # user_warranty_rate
        0.0,                     # user_dealer_contract_expired
        0.0,                     # user_cancel_count
        0.0,                     # user_report_count
        rng.uniform(600000, 1500000),  # order_total_amount  ← 高
        rng.uniform(3, 8),        # order_quantity
        rng.uniform(150000, 320000),   # order_unit_price
        rng.uniform(0.9, 1.0),    # order_msrp_ratio
        0.0 if rng.random() < 0.7 else 1.0,  # order_is_night
        1.0,                     # order_ship_region_match
        rng.uniform(0, 1),        # order_sn_repair_count_90d
        rng.uniform(0, 1),        # order_report_count
        rng.uniform(0, 0.1),      # order_repair_cost_ratio
        0.0,                     # order_is_out_of_warranty
        rng.uniform(1, 2),        # addr_region_total
        0.0,                     # addr_region_cross_count
        0.5 if rng.random() < 0.5 else 1.0,  # addr_is_new_region  ← 新区域概率高
    ], dtype=np.float32)


def _gen_mixed_high_risk(rng: random.Random) -> np.ndarray:
    """模式 6: 混合高风险 (保修率/维修费/串货/大单 多个信号叠加)"""
    return np.array([
        rng.uniform(10, 30),      # user_total_orders
        rng.uniform(5, 15),       # user_orders_30d
        rng.uniform(2, 8),        # user_orders_7d
        rng.uniform(800000, 4000000),  # user_total_amount
        rng.uniform(50000, 200000),    # user_avg_order_amount
        rng.uniform(300000, 1200000),  # user_max_order_amount
        rng.uniform(4, 12),       # user_warranty_count
        rng.uniform(2, 8),        # user_repair_count
        rng.uniform(0.3, 0.8),    # user_warranty_rate
        rng.uniform(0, 1),        # user_dealer_contract_expired
        rng.uniform(0, 2),        # user_cancel_count
        rng.uniform(1, 5),        # user_report_count
        rng.uniform(200000, 800000),   # order_total_amount
        rng.uniform(1, 5),        # order_quantity
        rng.uniform(60000, 250000),    # order_unit_price
        rng.uniform(0.5, 0.95),   # order_msrp_ratio
        0.3 if rng.random() < 0.6 else 1.0,  # order_is_night
        rng.uniform(0, 1),        # order_ship_region_match
        rng.uniform(1, 3),        # order_sn_repair_count_90d
        rng.uniform(1, 4),        # order_report_count
        rng.uniform(0.3, 0.8),    # order_repair_cost_ratio
        rng.uniform(0, 1),        # order_is_out_of_warranty
        rng.uniform(2, 5),        # addr_region_total
        rng.uniform(1, 4),        # addr_region_cross_count
        0.3 if rng.random() < 0.7 else 1.0,  # addr_is_new_region
    ], dtype=np.float32)


def _gen_normal_dealer(rng: random.Random) -> np.ndarray:
    """正常经销商 (低风险, 通过/标记)."""
    return np.array([
        rng.uniform(1, 6),        # user_total_orders
        rng.uniform(0, 3),        # user_orders_30d
        rng.uniform(0, 1),        # user_orders_7d
        rng.uniform(50000, 500000),    # user_total_amount
        rng.uniform(20000, 100000),    # user_avg_order_amount
        rng.uniform(50000, 200000),    # user_max_order_amount
        rng.uniform(0, 2),        # user_warranty_count  ← 低
        rng.uniform(0, 1),        # user_repair_count
        rng.uniform(0, 0.15),     # user_warranty_rate  ← 低
        0.0,                     # user_dealer_contract_expired
        rng.uniform(0, 1),        # user_cancel_count
        0.0,                     # user_report_count  ← 0
        rng.uniform(30000, 150000),    # order_total_amount
        rng.uniform(1, 4),        # order_quantity
        rng.uniform(20000, 90000),     # order_unit_price
        rng.uniform(0.75, 1.0),   # order_msrp_ratio
        0.0 if rng.random() < 0.85 else 1.0,  # order_is_night  ← 白天
        1.0,                     # order_ship_region_match  ← 本区
        rng.uniform(0, 1),        # order_sn_repair_count_90d
        rng.uniform(0, 1),        # order_report_count
        rng.uniform(0, 0.15),     # order_repair_cost_ratio
        0.0,                     # order_is_out_of_warranty
        rng.uniform(1, 2),        # addr_region_total
        rng.uniform(0, 1),        # addr_region_cross_count
        0.0 if rng.random() < 0.8 else 1.0,  # addr_is_new_region
    ], dtype=np.float32)


# 6 种正例模式 + 1 种负例
POSITIVE_PATTERNS = [
    _gen_high_warranty_rate, _gen_high_freq_order, _gen_warranty_fraud,
    _gen_cross_region, _gen_new_dealer_big_order, _gen_mixed_high_risk,
]
NEGATIVE_PATTERN = _gen_normal_dealer


def gen_synthetic_dataset(n: int = 2000, pos_ratio: float = 0.5, seed: int = 42):
    """生成合成训练数据集."""
    rng = random.Random(seed)
    np.random.seed(seed)

    n_pos = int(n * pos_ratio)
    n_neg = n - n_pos

    X_pos = np.zeros((n_pos, N_FEATURES), dtype=np.float32)
    for i in range(n_pos):
        X_pos[i] = POSITIVE_PATTERNS[i % len(POSITIVE_PATTERNS)](rng)

    X_neg = np.zeros((n_neg, N_FEATURES), dtype=np.float32)
    for i in range(n_neg):
        X_neg[i] = NEGATIVE_PATTERN(rng)

    X = np.vstack([X_pos, X_neg])
    y = np.concatenate([np.ones(n_pos, dtype=np.int32), np.zeros(n_neg, dtype=np.int32)])
    idx = np.random.permutation(n)
    return X[idx], y[idx]


def train_xgboost(X: np.ndarray, y: np.ndarray, num_boost_round: int = 200):
    """训练 XGBoost (跟 ml_model.py 同款超参)."""
    X_tr, X_val, y_tr, y_val = train_test_split(
        X, y, test_size=settings.XGB_TEST_SIZE, stratify=y, random_state=42,
    )
    dtrain = xgb.DMatrix(X_tr, label=y_tr, feature_names=FEATURE_NAMES)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_NAMES)

    params = {
        "objective": "binary:logistic",
        "eval_metric": ["logloss", "auc"],
        "max_depth": 6,
        "learning_rate": 0.1,
        "min_child_weight": 3,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "seed": 42,
        "tree_method": "hist",
    }

    print(f"\n[训练] {len(y_tr)} 训练 / {len(y_val)} 验证 (80/20 stratify)")
    print(f"  正例比例: {y_tr.sum()/len(y_tr):.2%} (训练) / {y_val.sum()/len(y_val):.2%} (验证)")

    booster = xgb.train(
        params, dtrain, num_boost_round=num_boost_round,
        evals=[(dtrain, "train"), (dval, "val")],
        early_stopping_rounds=10, verbose_eval=20,
    )

    y_pred_prob = booster.predict(xgb.DMatrix(X_val, feature_names=FEATURE_NAMES))
    y_pred = (y_pred_prob >= 0.5).astype(int)

    tp = int(np.sum((y_pred == 1) & (y_val == 1)))
    fp = int(np.sum((y_pred == 1) & (y_val == 0)))
    fn = int(np.sum((y_pred == 0) & (y_val == 1)))
    tn = int(np.sum((y_pred == 0) & (y_val == 0)))

    from sklearn.metrics import f1_score, roc_auc_score
    val_auc = roc_auc_score(y_val, y_pred_prob)
    val_f1 = f1_score(y_val, y_pred)
    val_acc = (tp + tn) / len(y_val)

    print(f"\n[验证集]")
    print(f"  AUC = {val_auc:.4f} {'OK' if val_auc > 0.85 else 'WARN (推荐 > 0.85)'}")
    print(f"  F1  = {val_f1:.4f} {'OK' if val_f1 > 0.6 else 'WARN (推荐 > 0.6)'}")
    print(f"  Acc = {val_acc:.4f}")
    print(f"  Confusion: TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  Best iter: {booster.best_iteration}")

    return booster, val_auc, val_f1


def main():
    parser = argparse.ArgumentParser(
        description="教学场景 XGBoost 演示模型训练 (不依赖 DB, 纯合成数据)"
    )
    parser.add_argument("--n", type=int, default=2000, help="合成样本数 (默认 2000)")
    parser.add_argument("--pos-ratio", type=float, default=0.5, help="正例比例 (默认 0.5)")
    parser.add_argument("--num-boost-round", type=int, default=200, help="XGBoost 迭代轮数")
    parser.add_argument("--model-path", type=str,
                        default=os.path.join(PROJECT_ROOT, "app", "engine", "xgb_model.json"),
                        help="模型保存路径")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    print("=" * 70)
    print("教学场景 XGBoost 演示模型训练 (制造业 6 种风险模式)")
    print("=" * 70)
    print(f"样本数: {args.n} (正例 {args.pos_ratio*100:.0f}% / 负例 {(1-args.pos_ratio)*100:.0f}%)")
    print(f"模型保存: {args.model_path}")
    print("=" * 70)

    print(f"\n[1/3] 生成 {args.n} 合成样本 (6 种制造业高风险模式 + 1 种正常模式)...")
    X, y = gen_synthetic_dataset(n=args.n, pos_ratio=args.pos_ratio, seed=args.seed)
    print(f"  X.shape={X.shape}, 正例={int(y.sum())} ({y.mean():.2%})")

    print("\n[2/3] 训练 XGBoost...")
    booster, val_auc, val_f1 = train_xgboost(X, y, num_boost_round=args.num_boost_round)

    print(f"\n[3/3] 保存模型到 {args.model_path}...")
    os.makedirs(os.path.dirname(args.model_path), exist_ok=True)
    booster.save_model(args.model_path)
    size_kb = os.path.getsize(args.model_path) / 1024
    print(f"  模型文件: {size_kb:.1f} KB")

    print("\n" + "=" * 70)
    print("训练完成!")
    print(f"  val_auc = {val_auc:.4f} {'OK' if val_auc > 0.85 else '< 0.85 警告'}")
    print(f"  val_f1  = {val_f1:.4f} {'OK' if val_f1 > 0.6 else '< 0.6 警告'}")
    print("=" * 70)
    print("下一步: python run_app.py 启动 Web 服务, 自动加载此模型")


if __name__ == "__main__":
    main()
