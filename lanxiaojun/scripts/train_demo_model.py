"""
电商风控系统 - 教学场景 XGBoost 演示模型训练 (P4-L4 2026-08-08)

【目的】
  不依赖 DB, 纯 numpy 合成 2000 样本, 训练一个针对 30 规则 + 20 特征的合理 XGBoost 模型.
  训完保存到 app/engine/xgb_model.json, run_app.py 启动时直接加载.

【为什么需要这个脚本】
  用户的真实 DB 数据是教学造数据 (gen_risk_data_with_dates.py), 正例比例 < 3%, 训出 val_auc ≈ 0.5.
  这个脚本合成"已知能触发 30 规则"的样本 (高退款率/高投诉/大额/多地址/夜间下单 等),
  训出针对业务场景的合理模型 (val_auc > 0.85).

【6 种高风险模式】
  1. 高退款率 (refund_rate > 0.3, refund_count > 5)
  2. 高投诉 (complaint_count > 3)
  3. 大额订单 (max_order_amount > 15000)
  4. 多地址 (addr_province_count > 3)
  5. 夜间高频 (order_is_night=1 + orders_30d 高)
  6. 混合高风险 (上面多种特征都偏高)

【用法】
  python scripts/train_demo_model.py                    # 默认 2000 样本, 训 200 轮
  python scripts/train_demo_model.py --n 5000            # 5000 样本
  python scripts/train_demo_model.py --model-path ml_models/xgb_demo.json  # 自定义保存路径
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

# 把项目根目录加到 sys.path, 这样能 import app.*
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS, _features_to_array


# ============================================================
# 20 维特征顺序 (跟 FEATURE_COLUMNS 一致)
# ============================================================

FEATURE_NAMES = FEATURE_COLUMNS
N_FEATURES = len(FEATURE_NAMES)
assert N_FEATURES == 20, f"必须是 20 维特征, 实际 {N_FEATURES}"


def _gen_high_refund_rate(rng: random.Random) -> np.ndarray:
    """模式 1: 高退款率 (触发 R004 '退款率 > 30%' / R006 '退款次数 > 5')"""
    return np.array([
        rng.uniform(5, 30),       # user_total_orders
        rng.uniform(1, 8),        # user_orders_30d
        rng.uniform(0, 3),        # user_orders_7d
        rng.uniform(20000, 100000),  # user_total_amount
        rng.uniform(500, 3000),   # user_avg_order_amount
        rng.uniform(2000, 10000), # user_max_order_amount
        rng.uniform(5, 20),       # user_refund_count
        rng.uniform(8, 25),       # user_postsale_count
        rng.uniform(0.3, 0.8),    # user_refund_rate
        rng.uniform(0.4, 0.9),    # user_postsale_rate
        rng.uniform(5000, 50000), # user_refund_amount
        rng.uniform(0, 5),        # user_cancel_count
        rng.uniform(0, 2),        # user_complaint_count
        rng.uniform(2, 5),        # user_address_count
        rng.uniform(200, 5000),   # order_total_amount
        rng.uniform(1, 5),        # order_item_count
        rng.uniform(1, 10),       # order_sku_count
        rng.uniform(0, 200),      # order_discount_amount
        rng.uniform(0, 0.1),      # order_discount_rate
        rng.uniform(60, 3600),    # order_pay_interval_sec
    ], dtype=np.float32)


def _gen_high_complaint(rng: random.Random) -> np.ndarray:
    """模式 2: 高投诉 (触发 R013 '投诉次数 > 3' / R014 '投诉率高')"""
    return np.array([
        rng.uniform(10, 40),
        rng.uniform(2, 10),
        rng.uniform(1, 4),
        rng.uniform(30000, 150000),
        rng.uniform(800, 5000),
        rng.uniform(3000, 15000),
        rng.uniform(1, 5),
        rng.uniform(3, 10),
        rng.uniform(0.05, 0.2),
        rng.uniform(0.1, 0.3),
        rng.uniform(500, 5000),
        rng.uniform(0, 3),
        rng.uniform(3, 15),       # user_complaint_count
        rng.uniform(2, 6),
        rng.uniform(300, 8000),
        rng.uniform(1, 6),
        rng.uniform(1, 12),
        rng.uniform(0, 300),
        rng.uniform(0, 0.1),
        rng.uniform(120, 7200),
    ], dtype=np.float32)


def _gen_high_amount(rng: random.Random) -> np.ndarray:
    """模式 3: 大额订单 (触发 R007 '单笔金额 > 10000' / R008 '高金额用户')"""
    return np.array([
        rng.uniform(1, 10),
        rng.uniform(0, 3),
        rng.uniform(0, 1),
        rng.uniform(50000, 200000),
        rng.uniform(2000, 10000),
        rng.uniform(15000, 50000),  # user_max_order_amount
        rng.uniform(0, 2),
        rng.uniform(0, 3),
        rng.uniform(0, 0.1),
        rng.uniform(0, 0.1),
        rng.uniform(0, 2000),
        rng.uniform(0, 2),
        rng.uniform(0, 1),
        rng.uniform(1, 3),
        rng.uniform(10000, 50000),  # order_total_amount
        rng.uniform(1, 4),
        rng.uniform(1, 8),
        rng.uniform(0, 500),
        rng.uniform(0, 0.05),
        rng.uniform(30, 1800),
    ], dtype=np.float32)


def _gen_multi_address(rng: random.Random) -> np.ndarray:
    """模式 4: 多地址 (触发 R011 '多省份地址 > 3')"""
    return np.array([
        rng.uniform(5, 20),
        rng.uniform(1, 6),
        rng.uniform(0, 3),
        rng.uniform(15000, 60000),
        rng.uniform(500, 3000),
        rng.uniform(2000, 8000),
        rng.uniform(0, 3),
        rng.uniform(1, 5),
        rng.uniform(0, 0.15),
        rng.uniform(0.05, 0.2),
        rng.uniform(0, 3000),
        rng.uniform(0, 3),
        rng.uniform(0, 2),
        rng.uniform(5, 10),       # user_address_count
        rng.uniform(300, 5000),
        rng.uniform(1, 4),
        rng.uniform(1, 8),
        rng.uniform(0, 200),
        rng.uniform(0, 0.1),
        rng.uniform(60, 3600),
    ], dtype=np.float32)


def _gen_night_high_freq(rng: random.Random) -> np.ndarray:
    """模式 5: 夜间高频 (注意：夜间用 order_is_night 但 20 维里没有, 改用 order_pay_interval_sec 短 + 订单多)"""
    return np.array([
        rng.uniform(10, 40),
        rng.uniform(5, 15),       # user_orders_30d
        rng.uniform(2, 6),        # user_orders_7d
        rng.uniform(20000, 80000),
        rng.uniform(300, 2000),
        rng.uniform(1500, 6000),
        rng.uniform(0, 3),
        rng.uniform(0, 4),
        rng.uniform(0, 0.1),
        rng.uniform(0, 0.15),
        rng.uniform(0, 2000),
        rng.uniform(0, 3),
        rng.uniform(0, 1),
        rng.uniform(1, 3),
        rng.uniform(200, 3000),
        rng.uniform(1, 4),
        rng.uniform(1, 6),
        rng.uniform(0, 150),
        rng.uniform(0, 0.1),
        rng.uniform(10, 300),     # order_pay_interval_sec 快支付
    ], dtype=np.float32)


def _gen_mixed_high_risk(rng: random.Random) -> np.ndarray:
    """模式 6: 混合高风险 (多种特征都偏高)"""
    return np.array([
        rng.uniform(15, 50),
        rng.uniform(3, 12),
        rng.uniform(1, 5),
        rng.uniform(40000, 150000),
        rng.uniform(800, 4000),
        rng.uniform(8000, 30000),
        rng.uniform(3, 12),
        rng.uniform(5, 20),
        rng.uniform(0.15, 0.5),
        rng.uniform(0.2, 0.6),
        rng.uniform(2000, 30000),
        rng.uniform(0, 4),
        rng.uniform(1, 6),
        rng.uniform(3, 8),
        rng.uniform(2000, 20000),
        rng.uniform(1, 6),
        rng.uniform(2, 12),
        rng.uniform(0, 400),
        rng.uniform(0, 0.1),
        rng.uniform(10, 600),
    ], dtype=np.float32)


def _gen_normal_user(rng: random.Random) -> np.ndarray:
    """正常用户 (低风险)"""
    return np.array([
        rng.uniform(0, 5),
        rng.uniform(0, 2),
        rng.uniform(0, 1),
        rng.uniform(0, 10000),
        rng.uniform(0, 1000),
        rng.uniform(0, 3000),
        rng.uniform(0, 1),
        rng.uniform(0, 2),
        rng.uniform(0, 0.05),
        rng.uniform(0, 0.1),
        rng.uniform(0, 500),
        rng.uniform(0, 1),
        rng.uniform(0, 1),
        rng.uniform(1, 2),
        rng.uniform(0, 1500),
        rng.uniform(1, 3),
        rng.uniform(1, 5),
        rng.uniform(0, 100),
        rng.uniform(0, 0.1),
        rng.uniform(120, 7200),
    ], dtype=np.float32)


# 6 种正例模式 + 1 种负例
POSITIVE_PATTERNS = [
    _gen_high_refund_rate, _gen_high_complaint, _gen_high_amount,
    _gen_multi_address, _gen_night_high_freq, _gen_mixed_high_risk,
]
NEGATIVE_PATTERN = _gen_normal_user


def gen_synthetic_dataset(n: int = 2000, pos_ratio: float = 0.5, seed: int = 42):
    """生成合成训练数据集."""
    rng = random.Random(seed)
    np.random.seed(seed)

    n_pos = int(n * pos_ratio)
    n_neg = n - n_pos

    X_pos = np.zeros((n_pos, N_FEATURES), dtype=np.float32)
    for i in range(n_pos):
        pattern = POSITIVE_PATTERNS[i % len(POSITIVE_PATTERNS)]
        X_pos[i] = pattern(rng)

    X_neg = np.zeros((n_neg, N_FEATURES), dtype=np.float32)
    for i in range(n_neg):
        X_neg[i] = NEGATIVE_PATTERN(rng)

    X = np.vstack([X_pos, X_neg])
    y = np.concatenate([np.ones(n_pos, dtype=np.int32), np.zeros(n_neg, dtype=np.int32)])

    idx = np.random.permutation(n)
    return X[idx], y[idx]


def train_xgboost(X: np.ndarray, y: np.ndarray, num_boost_round: int = 200):
    """训练 XGBoost"""
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
        params,
        dtrain,
        num_boost_round=num_boost_round,
        evals=[(dtrain, "train"), (dval, "val")],
        early_stopping_rounds=10,
        verbose_eval=20,
    )

    from sklearn.metrics import roc_auc_score, f1_score

    y_pred_prob = booster.predict(xgb.DMatrix(X_val, feature_names=FEATURE_NAMES))
    y_pred = (y_pred_prob >= 0.5).astype(int)

    tp = int(np.sum((y_pred == 1) & (y_val == 1)))
    fp = int(np.sum((y_pred == 1) & (y_val == 0)))
    fn = int(np.sum((y_pred == 0) & (y_val == 1)))
    tn = int(np.sum((y_pred == 0) & (y_val == 0)))

    val_auc = roc_auc_score(y_val, y_pred_prob)
    val_f1 = f1_score(y_val, y_pred)
    val_acc = (tp + tn) / len(y_val)

    print(f"\n[验证集]")
    print(f"  AUC = {val_auc:.4f} {'OK' if val_auc > 0.85 else 'WARN'}")
    print(f"  F1  = {val_f1:.4f} {'OK' if val_f1 > 0.6 else 'WARN'}")
    print(f"  Acc = {val_acc:.4f}")
    print(f"  Confusion: TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"  Best iter: {booster.best_iteration}")

    return booster, val_auc, val_f1


def main():
    parser = argparse.ArgumentParser(description="教学场景 XGBoost 演示模型训练")
    parser.add_argument("--n", type=int, default=2000, help="合成样本数")
    parser.add_argument("--pos-ratio", type=float, default=0.05, help="正例比例")
    parser.add_argument("--num-boost-round", type=int, default=200, help="迭代轮数")
    parser.add_argument("--model-path", type=str,
                        default=os.path.join(PROJECT_ROOT, "app", "engine", "xgb_model.json"),
                        help="模型保存路径")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    print("=" * 70)
    print("教学场景 XGBoost 演示模型训练 (20维)")
    print("=" * 70)
    print(f"样本数: {args.n} (正例 {args.pos_ratio*100:.0f}%)")
    print(f"模型保存: {args.model_path}")
    print("=" * 70)

    print(f"\n[1/3] 生成 {args.n} 合成样本...")
    X, y = gen_synthetic_dataset(n=args.n, pos_ratio=args.pos_ratio, seed=args.seed)
    print(f"  X.shape={X.shape}, 正例={int(y.sum())} ({y.mean():.2%})")

    print("\n[2/3] 训练 XGBoost...")
    booster, val_auc, val_f1 = train_xgboost(X, y, num_boost_round=args.num_boost_round)

    print(f"\n[3/3] 保存模型到 {args.model_path}...")
    os.makedirs(os.path.dirname(args.model_path), exist_ok=True)
    booster.save_model(args.model_path)
    print(f"  模型文件: {os.path.getsize(args.model_path) / 1024:.1f} KB")

    print("\n" + "=" * 70)
    print("训练完成!")
    print(f"  val_auc = {val_auc:.4f}")
    print(f"  val_f1  = {val_f1:.4f}")
    print("=" * 70)


if __name__ == "__main__":
    main()