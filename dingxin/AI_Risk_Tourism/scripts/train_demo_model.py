"""
旅游风控系统 - 教学场景 XGBoost 演示模型训练

【目的】不依赖 DB, 纯 numpy 合成样本, 训练一个针对 12 条旅游规则 + 25 维特征的合理模型.
训完保存到 app/engine/xgb_model.json, run_app.py 启动时直接加载.

【12 种高风险模式】对应 R001-R034 全部规则触发条件:
  1 拒签史     2 短期多国    3 大额跨境    4 黄牛囤票
  5 0点突击    6 乘客不一致  7 新用户大单  8 黑护照
  9 高频退改   10 临行改签   11 酒店倒卖  12 混合高风险

【用法】
  python scripts/train_demo_model.py                 # 默认 3000 样本
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
import xgboost as xgb
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import train_test_split

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS

FEATURE_NAMES = FEATURE_COLUMNS
N_FEATURES = len(FEATURE_NAMES)
assert N_FEATURES == 25, f"必须是 25 维特征, 实际 {N_FEATURES}"


# 25 维特征索引速查 (跟 FEATURE_COLUMNS 顺序一致)
def _base_vec(rng: random.Random) -> np.ndarray:
    return np.zeros(N_FEATURES, dtype=np.float32)


def _gen_reject(rng: random.Random) -> np.ndarray:
    """模式 1: 拒签史 → R001 (visa_reject_90d >= 2)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(3, 15)
    v[1] = rng.uniform(1, 6)
    v[3] = rng.uniform(10000, 60000)
    v[6] = rng.uniform(2, 5)          # user_visa_reject_90d 高
    v[7] = rng.uniform(1, 3)
    v[23] = rng.uniform(2, 6)         # visa_apply_30d 高
    return v


def _gen_multi_country(rng: random.Random) -> np.ndarray:
    """模式 2: 短期多国 → R002 (visa_countries_30d >= 3)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(2, 10)
    v[6] = rng.uniform(0, 1)
    v[7] = rng.uniform(3, 6)          # visa_countries_30d 高
    v[23] = rng.uniform(3, 8)         # visa_apply_30d 高
    return v


def _gen_big_cross(rng: random.Random) -> np.ndarray:
    """模式 3: 大额跨境 → R005 (order_total_amount >= 50000)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(1, 8)
    v[3] = rng.uniform(60000, 200000)
    v[4] = rng.uniform(20000, 80000)
    v[5] = rng.uniform(50000, 120000)  # max_order_amount 高
    v[11] = rng.uniform(50000, 120000) # order_total_amount 高
    v[13] = rng.uniform(5, 15)
    v[15] = 1.0                        # order_is_overseas
    return v


def _gen_scalper(rng: random.Random) -> np.ndarray:
    """模式 4: 黄牛囤票 → R008 (same_flight_1h >= 5)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(5, 30)
    v[1] = rng.uniform(3, 12)
    v[11] = rng.uniform(2000, 8000)
    v[14] = rng.uniform(1, 2)
    v[16] = 1.0                        # order_is_flight
    v[17] = rng.uniform(5, 10)         # booking_count 高
    v[21] = rng.uniform(5, 12)         # same_flight_1h 高
    return v


def _gen_night(rng: random.Random) -> np.ndarray:
    """模式 5: 0点突击 → R012 (is_night=1 AND trip_days<7)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(1, 6)
    v[11] = rng.uniform(1500, 12000)
    v[12] = 1.0                        # order_is_night
    v[13] = rng.uniform(2, 6)          # trip_days < 7
    return v


def _gen_mismatch(rng: random.Random) -> np.ndarray:
    """模式 6: 乘客不一致 → R018 (passenger_match_rate < 0.3)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(2, 10)
    v[14] = rng.uniform(2, 4)
    v[19] = rng.uniform(0.0, 0.25)     # passenger_match_rate 低
    v[22] = rng.uniform(3, 6)          # distinct_passenger_count 高
    return v


def _gen_new_user_big(rng: random.Random) -> np.ndarray:
    """模式 7: 新用户大单 → R025/R032 (age<7 AND amount>=10000 AND 5乘客)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(1, 3)
    v[8] = rng.uniform(1, 6)           # account_age_days 低
    v[11] = rng.uniform(10000, 40000)  # order_total_amount 高
    v[14] = rng.uniform(5, 8)          # passenger_count 高
    v[22] = rng.uniform(5, 8)          # distinct_passenger_count 高
    return v


def _gen_black_passport(rng: random.Random) -> np.ndarray:
    """模式 8: 黑护照 → R030 (blacklist_passport_count >= 1)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(1, 5)
    v[11] = rng.uniform(2000, 10000)
    v[20] = rng.uniform(1, 3)          # blacklist_passport_count 高
    return v


def _gen_refund_abuse(rng: random.Random) -> np.ndarray:
    """模式 9: 高频退改 → R031 (refund_rate>=0.5 AND orders>=5)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(5, 20)          # total_orders 高
    v[1] = rng.uniform(1, 6)
    v[3] = rng.uniform(10000, 50000)
    v[10] = rng.uniform(0.5, 0.9)      # refund_rate 高
    return v


def _gen_urgent_refund(rng: random.Random) -> np.ndarray:
    """模式 10: 临行改签 → R033 (is_urgent=1 AND is_flight=1)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(1, 8)
    v[11] = rng.uniform(3000, 15000)
    v[13] = rng.uniform(2, 8)
    v[16] = 1.0                        # order_is_flight
    v[18] = 1.0                        # order_is_urgent
    return v


def _gen_hotel_scalper(rng: random.Random) -> np.ndarray:
    """模式 11: 酒店倒卖 → R034 (same_hotel_1h >= 3)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(3, 20)
    v[1] = rng.uniform(2, 10)
    v[11] = rng.uniform(1500, 6000)
    v[13] = rng.uniform(3, 8)
    v[17] = rng.uniform(3, 8)          # booking_count 高
    v[24] = rng.uniform(3, 8)          # same_hotel_1h 高
    return v


def _gen_mixed(rng: random.Random) -> np.ndarray:
    """模式 12: 混合高风险 (多特征中高, 学习价值高)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(8, 25)
    v[1] = rng.uniform(3, 10)
    v[3] = rng.uniform(30000, 120000)
    v[4] = rng.uniform(1500, 8000)
    v[6] = rng.uniform(0, 2)
    v[10] = rng.uniform(0.2, 0.6)
    v[11] = rng.uniform(8000, 30000)
    v[13] = rng.uniform(4, 12)
    v[15] = 1.0 if rng.random() < 0.7 else 0.0
    v[19] = rng.uniform(0.2, 0.8)
    return v


def _gen_normal(rng: random.Random) -> np.ndarray:
    """正常用户 (负例, 不触发规则)"""
    v = _base_vec(rng)
    v[0] = rng.uniform(1, 5)
    v[1] = rng.uniform(0, 2)
    v[2] = rng.uniform(0, 1)
    v[3] = rng.uniform(1000, 15000)
    v[4] = rng.uniform(500, 3000)
    v[5] = rng.uniform(1000, 6000)
    v[8] = rng.uniform(100, 800)       # 老账号
    v[9] = 1.0                         # 已实名
    v[10] = rng.uniform(0, 0.1)        # 低退改率
    v[11] = rng.uniform(500, 4000)
    v[12] = 0.0 if rng.random() < 0.85 else 1.0
    v[13] = rng.uniform(4, 12)
    v[14] = rng.uniform(1, 2)
    v[15] = 1.0 if rng.random() < 0.5 else 0.0
    v[19] = rng.uniform(0.8, 1.0)      # 高匹配率
    return v


POSITIVE_PATTERNS = [
    _gen_reject, _gen_multi_country, _gen_big_cross, _gen_scalper,
    _gen_night, _gen_mismatch, _gen_new_user_big, _gen_black_passport,
    _gen_refund_abuse, _gen_urgent_refund, _gen_hotel_scalper, _gen_mixed,
]
NEGATIVE_PATTERN = _gen_normal


def gen_synthetic_dataset(n: int = 3000, pos_ratio: float = 0.5, seed: int = 42):
    """生成合成训练数据集 (12 正例模式 + 1 负例模式)."""
    rng = random.Random(seed)
    np.random.seed(seed)
    n_pos = int(n * pos_ratio)
    n_neg = n - n_pos
    X_pos = np.array([POSITIVE_PATTERNS[i % len(POSITIVE_PATTERNS)](rng) for i in range(n_pos)], dtype=np.float32)
    X_neg = np.array([NEGATIVE_PATTERN(rng) for _ in range(n_neg)], dtype=np.float32)
    X = np.vstack([X_pos, X_neg])
    y = np.concatenate([np.ones(n_pos, dtype=np.int32), np.zeros(n_neg, dtype=np.int32)])
    idx = np.random.permutation(n)
    return X[idx], y[idx]


def train_xgboost(X: np.ndarray, y: np.ndarray, num_boost_round: int = 200):
    """训练 XGBoost (超参跟 ml_model.py 一致)."""
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
    print(f"\n[训练] {len(y_tr)} 训练 / {len(y_val)} 验证 (80/20 stratify, 正例 {y_tr.mean():.0%})")
    booster = xgb.train(
        params, dtrain, num_boost_round=num_boost_round,
        evals=[(dtrain, "train"), (dval, "val")],
        early_stopping_rounds=10, verbose_eval=30,
    )
    y_prob = booster.predict(xgb.DMatrix(X_val, feature_names=FEATURE_NAMES))
    y_pred = (y_prob >= 0.5).astype(int)
    val_auc = roc_auc_score(y_val, y_prob)
    val_f1 = f1_score(y_val, y_pred)
    print(f"\n[验证集] AUC={val_auc:.4f} F1={val_f1:.4f} Acc={(y_pred == y_val).mean():.4f} "
          f"BestIter={booster.best_iteration}")
    return booster, val_auc, val_f1


def main():
    parser = argparse.ArgumentParser(description="旅游教学场景 XGBoost 演示模型训练 (纯合成数据)")
    parser.add_argument("--n", type=int, default=3000)
    parser.add_argument("--pos-ratio", type=float, default=0.5)
    parser.add_argument("--num-boost-round", type=int, default=200)
    parser.add_argument("--model-path", type=str,
                        default=os.path.join(PROJECT_ROOT, "app", "engine", "xgb_model.json"))
    args = parser.parse_args()

    print("=" * 70)
    print("旅游教学场景 XGBoost 演示模型训练 (纯合成数据)")
    print(f"样本数: {args.n} (正例 {args.pos_ratio*100:.0f}%) → 模型: {args.model_path}")
    print("=" * 70)

    X, y = gen_synthetic_dataset(n=args.n, pos_ratio=args.pos_ratio)
    print(f"[1/3] 合成样本: X.shape={X.shape}, 正例={int(y.sum())} ({y.mean():.1%})")
    print("[2/3] 训练 XGBoost (12 高风险模式 + 正常模式)...")
    booster, val_auc, val_f1 = train_xgboost(X, y, num_boost_round=args.num_boost_round)
    print(f"[3/3] 保存模型...")
    os.makedirs(os.path.dirname(args.model_path), exist_ok=True)
    booster.save_model(args.model_path)
    print(f"  模型文件: {os.path.getsize(args.model_path)/1024:.1f} KB")
    print("\n" + "=" * 70)
    print(f"训练完成! val_auc={val_auc:.4f} ({'OK' if val_auc > 0.85 else 'WARN'}), "
          f"val_f1={val_f1:.4f}")
    print("下一步: python run_app.py 启动后, 模型自动加载")
    print("=" * 70)


if __name__ == "__main__":
    main()
