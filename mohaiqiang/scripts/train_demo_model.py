"""
物流风控系统 - 教学场景 XGBoost 演示模型训练

【目的】
  不依赖 DB, 纯 numpy 合成样本, 训练一个针对物流规则 + 30 维特征的合理 XGBoost 模型.
  训完保存到 app/engine/xgb_model.json, run_app.py 启动时直接加载.

【和 gen_logistics_train_dataset.py 的关系】
  - gen_logistics_train_dataset.py: 从真实物流 DB 造严格标注训练集, 供正式训练
  - train_demo_model.py: 不需要 DB, 合成"已知能触发物流规则"的样本, 快速演示模型

【6 种高风险模式 (对应物流规则)】
  1. 高频寄件       (sender_waybills_30d / night_pickup 高)
  2. 危险品瞒报     (sender_dangerous_item_count / waybill_is_dangerous)
  3. 跨境异常       (sender_cross_border_count / waybill_value_weight_ratio 高)
  4. 多地址/共用地址 (sender_remote/temp/shared + address_* 高)
  5. COD拒收        (sender_cod_total_amount / sender_cod_reject_rate 高)
  6. 实名/账户异常  (sender_realname_verified=0 / verify_fail / account_risk)

【用法】
  python scripts/train_demo_model.py                     # 默认 2000 样本
  python scripts/train_demo_model.py --n 5000
  python scripts/train_demo_model.py --model-path ml_models/xgb_demo.json
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
from sklearn.model_selection import train_test_split

from app.config import settings
from app.engine.ml_model import FEATURE_COLUMNS, _features_to_array


FEATURE_NAMES = FEATURE_COLUMNS
N_FEATURES = len(FEATURE_NAMES)
assert N_FEATURES == 30, f"必须是 30 维物流特征, 实际 {N_FEATURES}"


def _pattern(rng: random.Random, **overrides) -> np.ndarray:
    """默认全 0, 用 override 填充指定特征, 再按 FEATURE_COLUMNS 顺序转数组."""
    features = {col: 0.0 for col in FEATURE_NAMES}
    features.update(overrides)
    return _features_to_array(features)[0]


def _gen_high_freq(rng: random.Random) -> np.ndarray:
    """模式 1: 高频寄件, 触发 R003/R004/R005."""
    return _pattern(
        rng,
        sender_total_waybills=rng.uniform(50, 200),
        sender_waybills_30d=rng.uniform(50, 120),
        sender_waybills_7d=rng.uniform(10, 50),
        sender_night_pickup_count=rng.uniform(5, 20),
        sender_realname_verified=1.0,
        waybill_declared_value=rng.uniform(200, 1500),
        waybill_weight_kg=rng.uniform(1, 5),
        waybill_value_weight_ratio=rng.uniform(100, 500),
    )


def _gen_dangerous(rng: random.Random) -> np.ndarray:
    """模式 2: 危险品瞒报, 触发 R007/R008."""
    return _pattern(
        rng,
        sender_dangerous_item_count=rng.uniform(3, 15),
        sender_abnormal_count=rng.uniform(3, 12),
        sender_realname_verified=1.0,
        waybill_declared_value=rng.uniform(50, 300),
        waybill_weight_kg=rng.uniform(0.5, 2),
        waybill_value_weight_ratio=rng.uniform(50, 300),
        waybill_is_dangerous=1.0,
    )


def _gen_cross_border(rng: random.Random) -> np.ndarray:
    """模式 3: 跨境异常, 触发 R009/R010."""
    return _pattern(
        rng,
        sender_cross_border_count=rng.uniform(20, 60),
        sender_high_value_ratio=rng.uniform(0.5, 1.0),
        sender_value_weight_ratio=rng.uniform(2000, 5000),
        sender_realname_verified=1.0,
        waybill_declared_value=rng.uniform(2000, 6000),
        waybill_weight_kg=rng.uniform(0.5, 2),
        waybill_value_weight_ratio=rng.uniform(1000, 4000),
        waybill_is_cross_border=1.0,
    )


def _gen_multi_address(rng: random.Random) -> np.ndarray:
    """模式 4: 多地址/共用地址, 触发 R014/R015/R016."""
    return _pattern(
        rng,
        sender_waybills_30d=rng.uniform(20, 60),
        sender_remote_address_count=rng.uniform(3, 8),
        sender_temp_address_count=rng.uniform(5, 12),
        sender_shared_address_count=rng.uniform(3, 10),
        sender_realname_verified=1.0,
        address_is_remote=1.0,
        address_is_temp=1.0,
        address_shared_count=rng.uniform(3, 8),
        address_use_count=rng.uniform(5, 15),
    )


def _gen_cod_reject(rng: random.Random) -> np.ndarray:
    """模式 5: COD 拒收, 触发 R011/R012/R013."""
    return _pattern(
        rng,
        sender_cod_total_amount=rng.uniform(50000, 200000),
        sender_cod_reject_rate=rng.uniform(0.3, 0.8),
        sender_complaint_count=rng.uniform(2, 8),
        sender_claim_count=rng.uniform(2, 8),
        sender_realname_verified=1.0,
        waybill_status_risk=1.0,
    )


def _gen_realname_risk(rng: random.Random) -> np.ndarray:
    """模式 6: 实名/账户异常, 触发 R001/R002/R020."""
    return _pattern(
        rng,
        sender_waybills_30d=rng.uniform(10, 40),
        sender_night_pickup_count=rng.uniform(3, 10),
        sender_realname_verified=0.0,
        sender_verify_fail_count=rng.uniform(3, 10),
        sender_account_risk=1.0,
    )


def _gen_normal(rng: random.Random) -> np.ndarray:
    """正常寄件人 (低风险, 通过/标记)."""
    return _pattern(
        rng,
        sender_total_waybills=rng.uniform(0, 5),
        sender_waybills_30d=rng.uniform(0, 2),
        sender_waybills_7d=0.0,
        sender_night_pickup_count=0.0,
        sender_dangerous_item_count=0.0,
        sender_cod_total_amount=0.0,
        sender_cod_reject_rate=0.0,
        sender_realname_verified=1.0,
        sender_verify_fail_count=0.0,
        sender_complaint_count=0.0,
        sender_claim_count=0.0,
        sender_abnormal_count=0.0,
        sender_cross_border_count=0.0,
        sender_remote_address_count=0.0,
        sender_temp_address_count=0.0,
        sender_shared_address_count=0.0,
        sender_insured_ratio=rng.uniform(0, 0.1),
        sender_high_value_ratio=rng.uniform(0, 0.2),
        sender_value_weight_ratio=rng.uniform(50, 200),
        sender_account_risk=0.0,
        waybill_declared_value=rng.uniform(50, 500),
        waybill_weight_kg=rng.uniform(0.5, 3),
        waybill_value_weight_ratio=rng.uniform(50, 300),
        waybill_is_dangerous=0.0,
        waybill_is_cross_border=0.0,
        waybill_status_risk=0.0,
        address_is_remote=0.0,
        address_is_temp=0.0,
        address_shared_count=1.0,
        address_use_count=rng.uniform(1, 5),
    )


POSITIVE_PATTERNS = [
    _gen_high_freq,
    _gen_dangerous,
    _gen_cross_border,
    _gen_multi_address,
    _gen_cod_reject,
    _gen_realname_risk,
]
NEGATIVE_PATTERN = _gen_normal


def gen_synthetic_dataset(n: int = 2000, pos_ratio: float = 0.5, seed: int = 42):
    """生成合成训练数据集 (30 维)."""
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
    parser.add_argument("--num-boost-round", type=int, default=200, help="迭代轮数 (默认 200)")
    parser.add_argument("--model-path", type=str,
                        default=os.path.join(PROJECT_ROOT, "app", "engine", "xgb_model.json"),
                        help="模型保存路径 (默认 app/engine/xgb_model.json)")
    parser.add_argument("--seed", type=int, default=42, help="随机种子 (默认 42)")
    args = parser.parse_args()

    print("=" * 70)
    print("教学场景 XGBoost 演示模型训练 (物流 30 维)")
    print("=" * 70)
    print(f"样本数: {args.n} (正例 {args.pos_ratio*100:.0f}% / 负例 {(1-args.pos_ratio)*100:.0f}%)")
    print(f"模型保存: {args.model_path}")
    print("=" * 70)

    print(f"\n[1/3] 生成 {args.n} 合成样本 (6 种高风险模式 + 1 种正常模式)...")
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
    print("下一步:")
    print("  python run_app.py                    # 启动 Web 服务, 自动加载此模型")
    print("  浏览器访问 http://localhost:8000       # 风险检查页能看到 XGBoost 评分")
    print("=" * 70)


if __name__ == "__main__":
    main()
