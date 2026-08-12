"""
旅游风控系统 - 教学场景 XGBoost 演示模型训练 (P4-L4 2026-08-08)

【目的】
  不依赖 DB, 纯 numpy 合成 2000 样本, 训练一个针对 8 条旅游规则 + 25 特征的合理 XGBoost 模型.
  训完保存到 app/engine/xgb_model.json, 页面端启动时直接加载.

【6 种高风险模式 (对齐 8 条旅游规则)】
  1. 黄牛囤票   (R003 同航班 1 小时>=5 张 / R004 凌晨突击下单)
  2. 拒签历史   (R001 拒签>=2 次 / R002 30 天申请>=3 国)
  3. 大额跨境游 (R005 出境订单>20000)
  4. 新用户大单 (R006 注册<7 天 + 订单>10000)
  5. 高频退改   (R008 退改率>=50%)
  6. 混合高风险 (多种特征都偏高)

【用法】
  python scripts/train_demo_model.py                          # 默认 2000 样本, 训 200 轮
  python scripts/train_demo_model.py --n 5000                 # 5000 样本
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
from app.engine.ml_model import FEATURE_COLUMNS


# 25 维特征顺序 (跟 FEATURE_COLUMNS 一致, 顺序不能乱)
FEATURE_NAMES = FEATURE_COLUMNS
N_FEATURES = len(FEATURE_NAMES)
assert N_FEATURES == 25, f"必须是 25 维特征, 实际 {N_FEATURES}"


# ============================================================
# 6 种高风险模式 + 1 种正常模式
# 数组顺序跟 FEATURE_COLUMNS 一一对应:
#   [0] user_total_orders  [1] user_orders_30d  [2] user_total_amount
#   [3] user_avg_order_amount  [4] user_max_order_amount  [5] user_cancel_count
#   [6] user_refund_count  [7] user_refund_rate  [8] user_night_order_count
#   [9] user_same_flight_1h_count  [10] user_visa_apply_count
#   [11] user_visa_reject_count  [12] user_visa_multi_country_30d
#   [13] user_account_age_days
#   [14] order_total_amount  [15] order_passenger_count  [16] order_is_night
#   [17] order_days_to_depart  [18] order_trip_days  [19] order_is_international
#   [20] order_same_flight_1h_count  [21] order_new_passenger_rate
#   [22] addr_dest_country_count  [23] addr_international_order_rate
#   [24] addr_current_dest_used_before
# ============================================================

def _gen_scalper(rng: random.Random) -> np.ndarray:
    """模式 1: 黄牛囤票 (R003 同航班 1 小时>=5 张 / R004 凌晨突击下单)"""
    return np.array([
        rng.uniform(5, 15),       # user_total_orders
        rng.uniform(3, 10),       # user_orders_30d (近期突击)
        rng.uniform(5000, 30000), # user_total_amount
        rng.uniform(800, 3000),   # user_avg_order_amount
        rng.uniform(2000, 5000),  # user_max_order_amount
        rng.uniform(3, 8),        # user_cancel_count (占座取消)
        rng.uniform(0, 2),        # user_refund_count
        rng.uniform(0, 0.3),      # user_refund_rate
        rng.uniform(3, 10),       # user_night_order_count (凌晨 1-5 点)
        rng.uniform(5, 10),       # user_same_flight_1h_count ← 高
        rng.uniform(0, 1),        # user_visa_apply_count
        rng.uniform(0, 1),        # user_visa_reject_count
        rng.uniform(0, 1),        # user_visa_multi_country_30d
        rng.uniform(60, 300),     # user_account_age_days
        rng.uniform(500, 3000),   # order_total_amount
        rng.uniform(1, 2),        # order_passenger_count
        1.0,                      # order_is_night ← 必为 1
        rng.uniform(5, 30),       # order_days_to_depart
        rng.uniform(2, 6),        # order_trip_days (<7)
        0.0,                      # order_is_international (国内航线囤票)
        rng.uniform(5, 10),       # order_same_flight_1h_count ← 高
        rng.uniform(0, 0.3),      # order_new_passenger_rate
        rng.uniform(1, 3),        # addr_dest_country_count
        rng.uniform(0, 0.2),      # addr_international_order_rate
        rng.uniform(0, 1),        # addr_current_dest_used_before
    ], dtype=np.float32)


def _gen_visa_reject(rng: random.Random) -> np.ndarray:
    """模式 2: 拒签历史/短期多国 (R001 拒签>=2 / R002 30 天>=3 国)"""
    return np.array([
        rng.uniform(0, 3),        # user_total_orders
        rng.uniform(0, 2),        # user_orders_30d
        rng.uniform(1000, 20000), # user_total_amount
        rng.uniform(500, 5000),   # user_avg_order_amount
        rng.uniform(2000, 8000),  # user_max_order_amount
        rng.uniform(0, 1),        # user_cancel_count
        rng.uniform(0, 1),        # user_refund_count
        rng.uniform(0, 0.1),      # user_refund_rate
        rng.uniform(0, 1),        # user_night_order_count
        rng.uniform(0, 1),        # user_same_flight_1h_count
        rng.uniform(4, 8),        # user_visa_apply_count ← 高
        rng.uniform(2, 5),        # user_visa_reject_count ← 高
        rng.uniform(3, 6),        # user_visa_multi_country_30d ← 高
        rng.uniform(90, 400),     # user_account_age_days
        0.0,                      # order_total_amount (签证事件无订单)
        0.0,                      # order_passenger_count
        0.0,                      # order_is_night
        0.0,                      # order_days_to_depart
        0.0,                      # order_trip_days
        1.0,                      # order_is_international
        0.0,                      # order_same_flight_1h_count
        0.0,                      # order_new_passenger_rate
        rng.uniform(1, 4),        # addr_dest_country_count
        rng.uniform(0.8, 1.0),    # addr_international_order_rate ← 高
        rng.uniform(0, 1),        # addr_current_dest_used_before
    ], dtype=np.float32)


def _gen_big_cross_border(rng: random.Random) -> np.ndarray:
    """模式 3: 大额跨境游 (R005 出境订单 >20000)"""
    return np.array([
        rng.uniform(1, 8),        # user_total_orders
        rng.uniform(0, 3),        # user_orders_30d
        rng.uniform(50000, 200000),  # user_total_amount
        rng.uniform(8000, 30000), # user_avg_order_amount
        rng.uniform(25000, 80000),# user_max_order_amount ← 高
        rng.uniform(0, 2),        # user_cancel_count
        rng.uniform(0, 2),        # user_refund_count
        rng.uniform(0, 0.2),      # user_refund_rate
        rng.uniform(0, 2),        # user_night_order_count
        rng.uniform(0, 2),        # user_same_flight_1h_count
        rng.uniform(0, 2),        # user_visa_apply_count
        rng.uniform(0, 1),        # user_visa_reject_count
        rng.uniform(0, 1),        # user_visa_multi_country_30d
        rng.uniform(100, 1000),   # user_account_age_days
        rng.uniform(20000, 80000),# order_total_amount ← 高
        rng.uniform(2, 4),        # order_passenger_count
        rng.uniform(0, 1),        # order_is_night
        rng.uniform(15, 60),      # order_days_to_depart
        rng.uniform(6, 14),       # order_trip_days
        1.0,                      # order_is_international ← 出境
        rng.uniform(0, 2),        # order_same_flight_1h_count
        rng.uniform(0.2, 0.6),    # order_new_passenger_rate
        rng.uniform(1, 3),        # addr_dest_country_count
        rng.uniform(0.6, 1.0),    # addr_international_order_rate
        rng.uniform(0, 1),        # addr_current_dest_used_before
    ], dtype=np.float32)


def _gen_new_user_big_order(rng: random.Random) -> np.ndarray:
    """模式 4: 新用户大单 (R006 注册<7 天 + 订单>10000)"""
    return np.array([
        rng.uniform(1, 3),        # user_total_orders
        rng.uniform(1, 3),        # user_orders_30d
        rng.uniform(15000, 60000),# user_total_amount
        rng.uniform(10000, 30000),# user_avg_order_amount
        rng.uniform(15000, 50000),# user_max_order_amount ← 高
        rng.uniform(0, 1),        # user_cancel_count
        rng.uniform(0, 1),        # user_refund_count
        rng.uniform(0, 0.1),      # user_refund_rate
        rng.uniform(0, 1),        # user_night_order_count
        rng.uniform(0, 1),        # user_same_flight_1h_count
        rng.uniform(0, 1),        # user_visa_apply_count
        rng.uniform(0, 1),        # user_visa_reject_count
        rng.uniform(0, 1),        # user_visa_multi_country_30d
        rng.uniform(1, 6),        # user_account_age_days ← 关键 (注册<7 天)
        rng.uniform(12000, 50000),# order_total_amount ← 高
        rng.uniform(1, 3),        # order_passenger_count
        rng.uniform(0, 1),        # order_is_night
        rng.uniform(7, 30),       # order_days_to_depart
        rng.uniform(3, 10),       # order_trip_days
        rng.uniform(0, 1),        # order_is_international
        rng.uniform(0, 2),        # order_same_flight_1h_count
        rng.uniform(0.5, 1.0),    # order_new_passenger_rate ← 新乘客
        1.0,                      # addr_dest_country_count
        rng.uniform(0, 0.5),      # addr_international_order_rate
        0.0,                      # addr_current_dest_used_before (新目的地)
    ], dtype=np.float32)


def _gen_high_refund(rng: random.Random) -> np.ndarray:
    """模式 5: 高频退改 (R008 退改率>=50%)"""
    return np.array([
        rng.uniform(5, 20),       # user_total_orders
        rng.uniform(3, 12),       # user_orders_30d
        rng.uniform(8000, 60000), # user_total_amount
        rng.uniform(500, 4000),   # user_avg_order_amount
        rng.uniform(3000, 15000), # user_max_order_amount
        rng.uniform(0, 3),        # user_cancel_count
        rng.uniform(3, 12),       # user_refund_count ← 高 (已退改订单)
        rng.uniform(0.5, 0.9),    # user_refund_rate ← 高 (>=50%)
        rng.uniform(0, 3),        # user_night_order_count
        rng.uniform(0, 2),        # user_same_flight_1h_count
        rng.uniform(0, 2),        # user_visa_apply_count
        rng.uniform(0, 1),        # user_visa_reject_count
        rng.uniform(0, 1),        # user_visa_multi_country_30d
        rng.uniform(60, 400),     # user_account_age_days
        rng.uniform(500, 5000),   # order_total_amount
        rng.uniform(1, 3),        # order_passenger_count
        rng.uniform(0, 1),        # order_is_night
        rng.uniform(7, 40),       # order_days_to_depart
        rng.uniform(3, 10),       # order_trip_days
        rng.uniform(0, 1),        # order_is_international
        rng.uniform(0, 2),        # order_same_flight_1h_count
        rng.uniform(0, 0.4),      # order_new_passenger_rate
        rng.uniform(1, 4),        # addr_dest_country_count
        rng.uniform(0.2, 0.8),    # addr_international_order_rate
        rng.uniform(0, 1),        # addr_current_dest_used_before
    ], dtype=np.float32)


def _gen_mixed_high_risk(rng: random.Random) -> np.ndarray:
    """模式 6: 混合高风险 (多种特征都偏高, 最难判但学习价值高)"""
    return np.array([
        rng.uniform(8, 30),       # user_total_orders
        rng.uniform(4, 15),       # user_orders_30d
        rng.uniform(30000, 120000),  # user_total_amount
        rng.uniform(1000, 6000),  # user_avg_order_amount
        rng.uniform(10000, 40000),# user_max_order_amount 高
        rng.uniform(1, 6),        # user_cancel_count
        rng.uniform(2, 8),        # user_refund_count 中高
        rng.uniform(0.2, 0.6),    # user_refund_rate 中高
        rng.uniform(1, 6),        # user_night_order_count
        rng.uniform(2, 6),        # user_same_flight_1h_count
        rng.uniform(1, 4),        # user_visa_apply_count
        rng.uniform(1, 3),        # user_visa_reject_count 中高
        rng.uniform(1, 3),        # user_visa_multi_country_30d 中高
        rng.uniform(20, 200),     # user_account_age_days
        rng.uniform(3000, 30000), # order_total_amount 中高
        rng.uniform(1, 4),        # order_passenger_count
        rng.uniform(0.4, 1.0),    # order_is_night 中高
        rng.uniform(3, 30),       # order_days_to_depart
        rng.uniform(2, 8),        # order_trip_days
        rng.uniform(0, 1),        # order_is_international
        rng.uniform(2, 6),        # order_same_flight_1h_count
        rng.uniform(0.3, 0.8),    # order_new_passenger_rate
        rng.uniform(2, 6),        # addr_dest_country_count
        rng.uniform(0.3, 0.9),    # addr_international_order_rate
        rng.uniform(0, 1),        # addr_current_dest_used_before
    ], dtype=np.float32)


def _gen_normal_user(rng: random.Random) -> np.ndarray:
    """正常用户 (低风险, 通过/标记)."""
    return np.array([
        rng.uniform(0, 4),        # user_total_orders 少
        rng.uniform(0, 2),        # user_orders_30d
        rng.uniform(0, 12000),    # user_total_amount 少
        rng.uniform(0, 3000),     # user_avg_order_amount
        rng.uniform(0, 5000),     # user_max_order_amount ← 低
        rng.uniform(0, 1),        # user_cancel_count
        rng.uniform(0, 1),        # user_refund_count ← 低
        rng.uniform(0, 0.15),     # user_refund_rate ← 低
        rng.uniform(0, 1),        # user_night_order_count ← 低
        rng.uniform(0, 1),        # user_same_flight_1h_count
        rng.uniform(0, 2),        # user_visa_apply_count
        rng.uniform(0, 1),        # user_visa_reject_count ← 低
        rng.uniform(0, 1),        # user_visa_multi_country_30d ← 低
        rng.uniform(100, 3000),   # user_account_age_days ← 老用户
        rng.uniform(200, 3000),   # order_total_amount ← 低
        rng.uniform(1, 2),        # order_passenger_count
        0.0 if rng.random() < 0.85 else 1.0,  # order_is_night 大概率白天
        rng.uniform(15, 90),      # order_days_to_depart
        rng.uniform(3, 12),       # order_trip_days
        rng.uniform(0, 1),        # order_is_international
        rng.uniform(0, 1),        # order_same_flight_1h_count ← 低
        rng.uniform(0, 0.3),      # order_new_passenger_rate ← 低
        rng.uniform(1, 3),        # addr_dest_country_count
        rng.uniform(0, 0.4),      # addr_international_order_rate
        rng.uniform(0, 1),        # addr_current_dest_used_before
    ], dtype=np.float32)


# 6 种正例模式 + 1 种负例
POSITIVE_PATTERNS = [
    _gen_scalper, _gen_visa_reject, _gen_big_cross_border,
    _gen_new_user_big_order, _gen_high_refund, _gen_mixed_high_risk,
]
NEGATIVE_PATTERN = _gen_normal_user


def gen_synthetic_dataset(n: int = 2000, pos_ratio: float = 0.5, seed: int = 42):
    """生成合成训练数据集.

    Args:
        n: 总样本数
        pos_ratio: 正例比例 (默认 0.5)
        seed: 随机种子

    Returns:
        X: (N, 25) float32
        y: (N,) int (0/1)
    """
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
    """训练 XGBoost (用 ml_model.py 的同款超参, 保持一致)."""
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

    y_pred_prob = booster.predict(xgb.DMatrix(X_val, feature_names=FEATURE_NAMES))
    y_pred = (y_pred_prob >= 0.5).astype(int)

    tp = int(np.sum((y_pred == 1) & (y_val == 1)))
    fp = int(np.sum((y_pred == 1) & (y_val == 0)))
    fn = int(np.sum((y_pred == 0) & (y_val == 1)))
    tn = int(np.sum((y_pred == 0) & (y_val == 0)))

    from sklearn.metrics import roc_auc_score, f1_score
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
    parser.add_argument("--num-boost-round", type=int, default=200, help="XGBoost 迭代轮数 (默认 200)")
    parser.add_argument("--model-path", type=str,
                        default=os.path.join(PROJECT_ROOT, "app", "engine", "xgb_model.json"),
                        help="模型保存路径 (默认 app/engine/xgb_model.json)")
    parser.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42)")
    args = parser.parse_args()

    print("=" * 70)
    print("教学场景 XGBoost 演示模型训练 (旅游风控)")
    print("=" * 70)
    print(f"样本数: {args.n} (正例 {args.pos_ratio*100:.0f}% / 负例 {(1-args.pos_ratio)*100:.0f}%)")
    print(f"模型保存: {args.model_path}")
    print("=" * 70)

    # 1. 生成合成数据
    print(f"\n[1/3] 生成 {args.n} 合成样本 (6 种旅游高风险模式 + 1 种正常模式)...")
    X, y = gen_synthetic_dataset(n=args.n, pos_ratio=args.pos_ratio, seed=args.seed)
    print(f"  X.shape={X.shape}, 正例={int(y.sum())} ({y.mean():.2%})")

    # 2. 训练
    print("\n[2/3] 训练 XGBoost...")
    booster, val_auc, val_f1 = train_xgboost(X, y, num_boost_round=args.num_boost_round)

    # 3. 保存
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
    print("下一步:")
    print("  python scripts/main.py                # 启动 Web 服务, 自动加载此模型")
    print("  浏览器访问 http://localhost:8000       # 风险检查页能看到 XGBoost 评分")
    print("=" * 70)


if __name__ == "__main__":
    main()
