"""
银行信贷风控系统 - 教学场景 XGBoost 演示模型训练 (P4-L4 2026-08-08, 银行版)

【目的】
  不依赖 DB, 纯 numpy 合成 2000 样本, 训练一个针对 30 规则 + 25 特征的合理 XGBoost 模型.
  训完可保存为演示模型 (默认 ml_models/xgb_demo.json, 不覆盖真实 PD 模型).

【为什么需要这个脚本】
  真实 PD 训练走 scripts/gen_train_dataset.py + train_xgb_model.py (逾期客户 = 正例).
  教学场景想快速看效果时, 用合成数据跑一遍, 验证 25 维特征 + 30 规则的联动.

【6 种高风险模式 (银行版)】
  1. 多头借贷 (cust_loans_30d/7d 高) → R101/R102
  2. 高负债 (loan_debt_ratio / loan_to_income 高) → R201/R202
  3. 大额申请 (loan_amount 高) → R301 反洗钱
  4. 逾期史 (cust_overdue_count/rate 高) → R501/R502
  5. 夜间高频申请 (loan_apply_is_night=1 + 短间隔) → R401 账户异常
  6. 设备异常 (dev_device_count 高 + 跨省 + 新设备) → R104 欺诈

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

from sklearn.model_selection import train_test_split  # noqa: E402

import xgboost as xgb  # noqa: E402

import numpy as np  # noqa: E402

from app.config import settings  # noqa: E402
from app.engine.ml_model import FEATURE_COLUMNS, _features_to_array  # noqa: E402


# ============================================================
# 6 种高风险模式 + 1 种正常客户模式 (银行版)
# 跟 feature.py 25 维特征一一对应, 跟 30 条规则的触发条件对得上
# ============================================================

# 25 维特征顺序 (跟 FEATURE_COLUMNS 一致)
FEATURE_NAMES = FEATURE_COLUMNS
N_FEATURES = len(FEATURE_NAMES)
assert N_FEATURES == 25, f"必须是 25 维特征, 实际 {N_FEATURES}"


def _gen_multi_loan(rng: random.Random) -> np.ndarray:
    """模式 1: 多头借贷 (触发 R101 '30天≥5笔' / R102 '30天≥8笔, 一票否决')"""
    return np.array([
        rng.uniform(8, 40),       # cust_total_loans (多头客户通常历史申请多)
        rng.uniform(5, 15),       # cust_loans_30d  ← 高
        rng.uniform(3, 8),        # cust_loans_7d  ← 高
        rng.uniform(20000, 100000),  # cust_total_amount
        rng.uniform(500, 3000),   # cust_avg_loan_amount
        rng.uniform(2000, 10000), # cust_max_loan_amount
        rng.uniform(0, 2),        # cust_overdue_count
        rng.uniform(0, 0.1),      # cust_overdue_rate
        rng.uniform(0, 5000),     # cust_overdue_amount
        rng.uniform(0, 5),        # cust_repay_count
        rng.uniform(0, 0.2),      # cust_repay_rate
        rng.uniform(1, 4),        # cust_reject_count
        rng.uniform(0, 2),        # cust_complaint_count
        rng.uniform(1, 3),        # cust_contact_count
        rng.uniform(5000, 30000), # loan_amount
        rng.uniform(12, 36),      # loan_term_month
        rng.uniform(0.3, 0.6),    # loan_debt_ratio  ← 中高
        rng.uniform(30, 3600),    # loan_apply_interval_sec
        0.0 if rng.random() < 0.7 else 1.0,  # loan_apply_is_night
        rng.uniform(0.3, 0.7),    # loan_to_income
        rng.uniform(1, 5),        # loan_apply_product_count
        rng.uniform(0.2, 0.5),    # loan_income_debt_ratio
        rng.uniform(2, 5),        # dev_device_count
        rng.uniform(2, 4),        # dev_ip_province_count  ← 跨省
        0.0 if rng.random() < 0.5 else 1.0,  # dev_is_new
    ], dtype=np.float32)


def _gen_high_debt(rng: random.Random) -> np.ndarray:
    """模式 2: 高负债 (触发 R201 '负债率≥50%' / R202 '负债率≥80%, 一票否决')"""
    return np.array([
        rng.uniform(3, 15),
        rng.uniform(1, 5),
        rng.uniform(0, 3),
        rng.uniform(30000, 150000),
        rng.uniform(800, 5000),
        rng.uniform(3000, 15000),
        rng.uniform(0, 3),
        rng.uniform(0, 0.15),
        rng.uniform(0, 5000),
        rng.uniform(1, 6),
        rng.uniform(0.1, 0.4),
        rng.uniform(0, 3),
        rng.uniform(0, 2),
        rng.uniform(1, 3),
        rng.uniform(20000, 80000),  # loan_amount  ← 大额
        rng.uniform(24, 60),        # loan_term_month
        rng.uniform(0.5, 0.9),      # loan_debt_ratio  ← 高
        rng.uniform(60, 7200),
        0.0 if rng.random() < 0.8 else 1.0,
        rng.uniform(0.6, 1.2),      # loan_to_income  ← 高
        rng.uniform(1, 4),
        rng.uniform(0.5, 0.9),      # loan_income_debt_ratio  ← 高
        rng.uniform(1, 3),
        rng.uniform(1, 2),
        0.0 if rng.random() < 0.7 else 1.0,
    ], dtype=np.float32)


def _gen_large_amount(rng: random.Random) -> np.ndarray:
    """模式 3: 大额申请 (触发 R301 反洗钱 '单笔≥30万' / R302 '频繁大额')"""
    return np.array([
        rng.uniform(1, 10),
        rng.uniform(0, 3),
        rng.uniform(0, 1),
        rng.uniform(100000, 400000),
        rng.uniform(2000, 10000),
        rng.uniform(15000, 50000),  # cust_max_loan_amount  ← 高
        rng.uniform(0, 2),
        rng.uniform(0, 0.1),
        rng.uniform(0, 2000),
        rng.uniform(0, 3),
        rng.uniform(0, 0.2),
        rng.uniform(0, 2),
        rng.uniform(0, 1),
        rng.uniform(1, 2),
        rng.uniform(300000, 800000),  # loan_amount  ← 极高
        rng.uniform(12, 36),
        rng.uniform(0.2, 0.5),
        rng.uniform(30, 1800),
        0.0 if rng.random() < 0.8 else 1.0,
        rng.uniform(0.3, 0.6),
        rng.uniform(1, 3),
        rng.uniform(0.2, 0.4),
        rng.uniform(1, 3),
        rng.uniform(1, 2),
        0.0 if rng.random() < 0.7 else 1.0,
    ], dtype=np.float32)


def _gen_overdue_history(rng: random.Random) -> np.ndarray:
    """模式 4: 逾期史 (触发 R501 '逾期率≥30%' / R502 '逾期率≥50%, 一票否决')"""
    return np.array([
        rng.uniform(5, 20),
        rng.uniform(1, 6),
        rng.uniform(0, 3),
        rng.uniform(15000, 60000),
        rng.uniform(500, 3000),
        rng.uniform(2000, 8000),
        rng.uniform(3, 10),       # cust_overdue_count  ← 高
        rng.uniform(0.3, 0.8),    # cust_overdue_rate  ← 高
        rng.uniform(5000, 50000), # cust_overdue_amount  ← 高
        rng.uniform(0, 3),        # cust_repay_count  ← 低
        rng.uniform(0.05, 0.3),   # cust_repay_rate  ← 低
        rng.uniform(1, 4),        # cust_reject_count
        rng.uniform(0, 3),
        rng.uniform(1, 2),
        rng.uniform(10000, 50000),
        rng.uniform(12, 36),
        rng.uniform(0.3, 0.6),
        rng.uniform(60, 3600),
        0.0 if rng.random() < 0.7 else 1.0,
        rng.uniform(0.4, 0.8),
        rng.uniform(1, 4),
        rng.uniform(0.3, 0.6),
        rng.uniform(1, 3),
        rng.uniform(1, 2),
        0.0 if rng.random() < 0.6 else 1.0,
    ], dtype=np.float32)


def _gen_night_high_freq(rng: random.Random) -> np.ndarray:
    """模式 5: 夜间高频申请 (触发 R401 账户异常 '0-6点申请' / '短间隔连申')"""
    return np.array([
        rng.uniform(3, 15),
        rng.uniform(3, 10),       # cust_loans_30d  ← 高
        rng.uniform(1, 5),
        rng.uniform(10000, 50000),
        rng.uniform(300, 2000),
        rng.uniform(1500, 6000),
        rng.uniform(0, 2),
        rng.uniform(0, 0.1),
        rng.uniform(0, 2000),
        rng.uniform(0, 3),
        rng.uniform(0, 0.2),
        rng.uniform(0, 2),
        rng.uniform(0, 1),
        rng.uniform(1, 2),
        rng.uniform(5000, 30000),
        rng.uniform(12, 36),
        rng.uniform(0.2, 0.5),
        rng.uniform(30, 1200),    # loan_apply_interval_sec  ← 快
        1.0,                      # loan_apply_is_night  ← 必为 1
        rng.uniform(0.3, 0.6),
        rng.uniform(1, 3),
        rng.uniform(0.2, 0.4),
        rng.uniform(1, 3),
        rng.uniform(1, 2),
        0.0 if rng.random() < 0.5 else 1.0,
    ], dtype=np.float32)


def _gen_device_anomaly(rng: random.Random) -> np.ndarray:
    """模式 6: 设备异常 (触发 R104 欺诈 '多设备' / R105 '新设备+跨省')"""
    return np.array([
        rng.uniform(5, 20),
        rng.uniform(1, 5),
        rng.uniform(0, 3),
        rng.uniform(20000, 80000),
        rng.uniform(500, 3000),
        rng.uniform(2000, 10000),
        rng.uniform(0, 3),
        rng.uniform(0, 0.15),
        rng.uniform(0, 3000),
        rng.uniform(0, 4),
        rng.uniform(0, 0.3),
        rng.uniform(0, 3),
        rng.uniform(0, 2),
        rng.uniform(1, 3),
        rng.uniform(5000, 30000),
        rng.uniform(12, 36),
        rng.uniform(0.2, 0.5),
        rng.uniform(60, 3600),
        0.0 if rng.random() < 0.6 else 1.0,
        rng.uniform(0.3, 0.6),
        rng.uniform(1, 4),
        rng.uniform(0.2, 0.4),
        rng.uniform(4, 10),       # dev_device_count  ← 高
        rng.uniform(3, 7),        # dev_ip_province_count  ← 跨省
        0.3 if rng.random() < 0.7 else 1.0,  # dev_is_new  ← 中高概率新设备
    ], dtype=np.float32)


def _gen_normal_customer(rng: random.Random) -> np.ndarray:
    """正常客户 (低风险, 通过/标记)."""
    return np.array([
        rng.uniform(0, 5),        # cust_total_loans 少
        rng.uniform(0, 2),        # cust_loans_30d
        rng.uniform(0, 1),        # cust_loans_7d
        rng.uniform(0, 10000),    # cust_total_amount 少
        rng.uniform(0, 1000),     # cust_avg_loan_amount
        rng.uniform(0, 3000),     # cust_max_loan_amount  ← 低
        rng.uniform(0, 1),        # cust_overdue_count  ← 低
        rng.uniform(0, 0.05),     # cust_overdue_rate  ← 低
        rng.uniform(0, 500),      # cust_overdue_amount
        rng.uniform(0, 3),        # cust_repay_count
        rng.uniform(0.3, 0.8),    # cust_repay_rate  ← 高
        rng.uniform(0, 1),        # cust_reject_count  ← 低
        rng.uniform(0, 1),        # cust_complaint_count  ← 低
        rng.uniform(1, 2),        # cust_contact_count
        rng.uniform(0, 1500),     # loan_amount  ← 低
        rng.uniform(6, 24),       # loan_term_month
        rng.uniform(0.05, 0.3),   # loan_debt_ratio  ← 低
        rng.uniform(120, 7200),   # loan_apply_interval_sec (正常)
        0.0 if rng.random() < 0.85 else 1.0,  # loan_apply_is_night  ← 大概率白天
        rng.uniform(0.1, 0.3),    # loan_to_income  ← 低
        rng.uniform(1, 2),        # loan_apply_product_count
        rng.uniform(0.05, 0.2),   # loan_income_debt_ratio  ← 低
        1.0,                      # dev_device_count  ← 1 台
        1.0,                      # dev_ip_province_count  ← 1 个省
        0.0 if rng.random() < 0.8 else 1.0,  # dev_is_new  ← 大概率老设备
    ], dtype=np.float32)


# 6 种正例模式 + 1 种负例
POSITIVE_PATTERNS = [
    _gen_multi_loan, _gen_high_debt, _gen_large_amount,
    _gen_overdue_history, _gen_night_high_freq, _gen_device_anomaly,
]
NEGATIVE_PATTERN = _gen_normal_customer


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

    # 正例: 6 种模式轮换
    X_pos = np.zeros((n_pos, N_FEATURES), dtype=np.float32)
    for i in range(n_pos):
        pattern = POSITIVE_PATTERNS[i % len(POSITIVE_PATTERNS)]
        X_pos[i] = pattern(rng)

    # 负例: 1 种模式
    X_neg = np.zeros((n_neg, N_FEATURES), dtype=np.float32)
    for i in range(n_neg):
        X_neg[i] = NEGATIVE_PATTERN(rng)

    X = np.vstack([X_pos, X_neg])
    y = np.concatenate([np.ones(n_pos, dtype=np.int32), np.zeros(n_neg, dtype=np.int32)])

    # 乱序
    idx = np.random.permutation(n)
    return X[idx], y[idx]


def train_xgboost(X: np.ndarray, y: np.ndarray, num_boost_round: int = 200):
    """训练 XGBoost (用 ml_model.py 的同款超参, 保持一致)."""
    # 80/20 stratify
    X_tr, X_val, y_tr, y_val = train_test_split(
        X, y, test_size=settings.XGB_TEST_SIZE, stratify=y, random_state=42,
    )

    # DMatrix (XGBoost 2.x 必须)
    dtrain = xgb.DMatrix(X_tr, label=y_tr, feature_names=FEATURE_NAMES)
    dval = xgb.DMatrix(X_val, label=y_val, feature_names=FEATURE_NAMES)

    # 训练参数 (跟 ml_model.py 一致, 但简化版)
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

    # 评估
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
                        default=os.path.join(PROJECT_ROOT, "ml_models", "xgb_demo.json"),
                        help="模型保存路径 (默认 ml_models/xgb_demo.json, 不覆盖真实 PD 模型)")
    parser.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42)")
    args = parser.parse_args()

    print("=" * 70)
    print("教学场景 XGBoost 演示模型训练 (银行版)")
    print("=" * 70)
    print(f"样本数: {args.n} (正例 {args.pos_ratio*100:.0f}% / 负例 {(1-args.pos_ratio)*100:.0f}%)")
    print(f"模型保存: {args.model_path}")
    print("=" * 70)

    # 1. 生成合成数据
    print(f"\n[1/3] 生成 {args.n} 合成样本 (6 种高风险模式 + 1 种正常模式)...")
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
    print("  真实 PD 训练: python scripts/gen_train_dataset.py --reset && python scripts/train_xgb_model.py")
    print("  演示模型: 想用演示模型覆盖, 手动 cp ml_models/xgb_demo.json app/engine/xgb_model.json")
    print("=" * 70)


if __name__ == "__main__":
    main()