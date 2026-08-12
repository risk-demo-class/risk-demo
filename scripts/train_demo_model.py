"""
医疗风控系统 - 教学场景 XGBoost 演示模型训练

【目的】
  不依赖 DB, 纯 numpy 合成 2000 样本, 训练一个针对 30 条医疗规则 + 25 特征的合理 XGBoost 模型.
  训完保存到 app/engine/xgb_model.json, run_app.py 启动时直接加载.

【为什么需要这个脚本】
  用户的真实 DB 数据是教学造数据 (gen_risk_data_with_dates.py), 正例比例 < 3%, 训出 val_auc ≈ 0.5.
  这个脚本合成"已知能触发医疗规则"的样本 (医保卡盗刷/医生统方/处方超量/挂号黄牛/药品代购 等),
  训出针对业务场景的合理模型 (val_auc > 0.85).

【6 种高风险模式】
  1. 医保卡盗刷 (user_claim_hospitals_1h >= 3, 触发 R001)
  2. 医生统方 (order_doctor_rx_1d >= 50 + order_doctor_patient_1d >= 10, 触发 R002)
  3. 处方超量 (order_drug_quantity > 30, 触发 R008)
  4. 挂号黄牛 (user_cancel_24h >= 5, 触发 R005)
  5. 药品代购 (order_receiver_not_self = 1 + user_drug_amount > 5000, 触发 R018)
  6. 混合高风险 (黑医保卡 + 异地高频结算 + 多特征偏高)

【用法】
  python scripts/train_demo_model.py                    # 默认 2000 样本, 训 200 轮
  python scripts/train_demo_model.py --n 5000           # 5000 样本
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

# 25 维特征顺序 (跟 FEATURE_COLUMNS 一致, 医疗版)
FEATURE_NAMES = FEATURE_COLUMNS
N_FEATURES = len(FEATURE_NAMES)
assert N_FEATURES == 25, f"必须是 25 维特征, 实际 {N_FEATURES}"


def _gen_card_fraud(rng: random.Random) -> np.ndarray:
    """模式 1: 医保卡盗刷 (触发 R001 '1 小时内 ≥3 家医院结算')"""
    return np.array([
        rng.uniform(3, 20),       # user_total_visits
        rng.uniform(2, 8),        # user_visits_7d
        rng.uniform(3, 15),       # user_visits_30d
        rng.uniform(0, 3),        # user_cancel_count
        rng.uniform(0, 2),        # user_cancel_24h
        rng.uniform(3, 8),        # user_hospital_count  ← 高 (多院)
        rng.uniform(3, 6),        # user_claim_hospitals_1h  ← 高 (核心信号)
        rng.uniform(5, 20),       # user_claim_count
        rng.uniform(8000, 50000), # user_claim_amount
        rng.uniform(4, 12),       # user_claim_30d_count
        rng.uniform(8000, 40000), # user_claim_30d_amount
        rng.uniform(2, 10),       # user_rx_count
        rng.uniform(0, 3000),     # user_drug_amount
        0.0,                      # user_card_blacklist_hit
        rng.uniform(500, 8000),   # order_total_amount (单笔结算)
        rng.uniform(1, 3),        # order_item_count
        rng.uniform(0, 20),       # order_drug_quantity
        0.0 if rng.random() < 0.8 else 1.0,  # order_is_night
        rng.uniform(1, 15),       # order_doctor_rx_1d
        rng.uniform(1, 10),       # order_doctor_patient_1d
        rng.uniform(0, 3),        # order_diagnosis_same_7d
        0.0,                      # order_receiver_not_self
        rng.uniform(0, 2),        # addr_visit_count (新医院多 → 低)
        1.0,                      # addr_is_new  ← 首次就诊医院多
        0.0 if rng.random() < 0.6 else 1.0,  # addr_cross_region
    ], dtype=np.float32)


def _gen_doctor_tongfang(rng: random.Random) -> np.ndarray:
    """模式 2: 医生统方 (触发 R002 '医生 1 天 ≥50 张处方 + ≥10 患者')"""
    return np.array([
        rng.uniform(1, 8),        # user_total_visits
        rng.uniform(1, 4),        # user_visits_7d
        rng.uniform(1, 6),        # user_visits_30d
        rng.uniform(0, 2),        # user_cancel_count
        rng.uniform(0, 1),        # user_cancel_24h
        rng.uniform(1, 3),        # user_hospital_count
        rng.uniform(0, 1),        # user_claim_hospitals_1h
        rng.uniform(1, 5),        # user_claim_count
        rng.uniform(500, 5000),   # user_claim_amount
        rng.uniform(1, 4),        # user_claim_30d_count
        rng.uniform(500, 4000),   # user_claim_30d_amount
        rng.uniform(1, 5),        # user_rx_count
        rng.uniform(0, 1500),     # user_drug_amount
        0.0,                      # user_card_blacklist_hit
        rng.uniform(30, 300),     # order_total_amount (普通处方金额)
        rng.uniform(1, 4),        # order_item_count
        rng.uniform(5, 25),       # order_drug_quantity
        0.0 if rng.random() < 0.7 else 1.0,  # order_is_night
        rng.uniform(50, 90),      # order_doctor_rx_1d  ← 高 (核心信号)
        rng.uniform(10, 30),      # order_doctor_patient_1d  ← 高 (核心信号)
        rng.uniform(3, 10),       # order_diagnosis_same_7d  ← 同诊断聚集
        0.0,                      # order_receiver_not_self
        rng.uniform(1, 4),        # addr_visit_count
        0.0 if rng.random() < 0.6 else 1.0,  # addr_is_new
        0.0,                      # addr_cross_region
    ], dtype=np.float32)


def _gen_overdose(rng: random.Random) -> np.ndarray:
    """模式 3: 处方超量 (触发 R008 '单张处方药品数量 > 30')"""
    return np.array([
        rng.uniform(1, 10),       # user_total_visits
        rng.uniform(1, 4),        # user_visits_7d
        rng.uniform(1, 8),        # user_visits_30d
        rng.uniform(0, 2),        # user_cancel_count
        rng.uniform(0, 1),        # user_cancel_24h
        rng.uniform(1, 4),        # user_hospital_count
        rng.uniform(0, 1),        # user_claim_hospitals_1h
        rng.uniform(1, 6),        # user_claim_count
        rng.uniform(500, 8000),   # user_claim_amount
        rng.uniform(1, 5),        # user_claim_30d_count
        rng.uniform(500, 6000),   # user_claim_30d_amount
        rng.uniform(2, 10),       # user_rx_count  ← 多处方
        rng.uniform(500, 8000),   # user_drug_amount  ← 累计购药高
        0.0,                      # user_card_blacklist_hit
        rng.uniform(100, 800),    # order_total_amount
        rng.uniform(1, 3),        # order_item_count
        rng.uniform(31, 120),     # order_drug_quantity  ← 高 (核心信号)
        0.0 if rng.random() < 0.6 else 1.0,  # order_is_night
        rng.uniform(3, 20),       # order_doctor_rx_1d
        rng.uniform(2, 12),       # order_doctor_patient_1d
        rng.uniform(0, 4),        # order_diagnosis_same_7d
        0.0 if rng.random() < 0.7 else 1.0,  # order_receiver_not_self
        rng.uniform(1, 4),        # addr_visit_count
        0.0 if rng.random() < 0.5 else 1.0,  # addr_is_new
        0.0,                      # addr_cross_region
    ], dtype=np.float32)


def _gen_scalper(rng: random.Random) -> np.ndarray:
    """模式 4: 挂号黄牛 (触发 R005 '同手机号 24h 取消挂号 ≥5 次')"""
    return np.array([
        rng.uniform(8, 30),       # user_total_visits  ← 高 (反复抢号)
        rng.uniform(5, 15),       # user_visits_7d  ← 高
        rng.uniform(8, 25),       # user_visits_30d
        rng.uniform(5, 20),       # user_cancel_count  ← 高
        rng.uniform(5, 12),       # user_cancel_24h  ← 高 (核心信号)
        rng.uniform(3, 8),        # user_hospital_count  ← 多院占号
        rng.uniform(0, 1),        # user_claim_hospitals_1h
        rng.uniform(0, 3),        # user_claim_count (黄牛很少结算)
        rng.uniform(0, 2000),     # user_claim_amount
        rng.uniform(0, 2),        # user_claim_30d_count
        rng.uniform(0, 1500),     # user_claim_30d_amount
        rng.uniform(0, 3),        # user_rx_count
        rng.uniform(0, 500),      # user_drug_amount
        0.0,                      # user_card_blacklist_hit
        rng.uniform(20, 100),     # order_total_amount (挂号费)
        1.0,                      # order_item_count
        0.0,                      # order_drug_quantity
        0.0 if rng.random() < 0.5 else 1.0,  # order_is_night (凌晨抢号)
        rng.uniform(1, 15),       # order_doctor_rx_1d
        rng.uniform(1, 10),       # order_doctor_patient_1d
        rng.uniform(0, 2),        # order_diagnosis_same_7d
        0.0,                      # order_receiver_not_self
        rng.uniform(0, 2),        # addr_visit_count
        1.0,                      # addr_is_new
        0.0,                      # addr_cross_region
    ], dtype=np.float32)


def _gen_proxy_buyer(rng: random.Random) -> np.ndarray:
    """模式 5: 药品代购 (触发 R018 '收件人≠本人 + 累计金额 > 5000')"""
    return np.array([
        rng.uniform(2, 12),       # user_total_visits
        rng.uniform(1, 5),        # user_visits_7d
        rng.uniform(2, 10),       # user_visits_30d
        rng.uniform(0, 2),        # user_cancel_count
        rng.uniform(0, 1),        # user_cancel_24h
        rng.uniform(1, 4),        # user_hospital_count
        rng.uniform(0, 1),        # user_claim_hospitals_1h
        rng.uniform(1, 6),        # user_claim_count
        rng.uniform(500, 6000),   # user_claim_amount
        rng.uniform(1, 5),        # user_claim_30d_count
        rng.uniform(500, 5000),   # user_claim_30d_amount
        rng.uniform(2, 10),       # user_rx_count
        rng.uniform(5000, 30000), # user_drug_amount  ← 高 (核心信号)
        0.0,                      # user_card_blacklist_hit
        rng.uniform(500, 3000),   # order_total_amount
        1.0,                      # order_item_count
        rng.uniform(6, 25),       # order_drug_quantity  ← 批量
        0.0 if rng.random() < 0.7 else 1.0,  # order_is_night
        rng.uniform(2, 15),       # order_doctor_rx_1d
        rng.uniform(2, 10),       # order_doctor_patient_1d
        rng.uniform(0, 3),        # order_diagnosis_same_7d
        1.0,                      # order_receiver_not_self  ← 必为 1 (核心信号)
        rng.uniform(1, 4),        # addr_visit_count
        0.0 if rng.random() < 0.5 else 1.0,  # addr_is_new
        0.0 if rng.random() < 0.7 else 1.0,  # addr_cross_region
    ], dtype=np.float32)


def _gen_mixed_high_risk(rng: random.Random) -> np.ndarray:
    """模式 6: 混合高风险 (黑医保卡 + 异地高频结算 + 多特征偏高, 最难判但学习价值高)"""
    return np.array([
        rng.uniform(10, 40),      # user_total_visits
        rng.uniform(4, 12),       # user_visits_7d
        rng.uniform(8, 25),       # user_visits_30d
        rng.uniform(2, 8),        # user_cancel_count
        rng.uniform(1, 5),        # user_cancel_24h
        rng.uniform(4, 8),        # user_hospital_count  ← 高
        rng.uniform(1, 4),        # user_claim_hospitals_1h  ← 中高
        rng.uniform(6, 20),       # user_claim_count
        rng.uniform(15000, 80000),  # user_claim_amount  ← 高
        rng.uniform(5, 15),       # user_claim_30d_count
        rng.uniform(12000, 60000),  # user_claim_30d_amount  ← 高
        rng.uniform(3, 12),       # user_rx_count
        rng.uniform(2000, 15000), # user_drug_amount
        0.0 if rng.random() < 0.5 else 1.0,  # user_card_blacklist_hit  ← 中高概率撞黑
        rng.uniform(3000, 25000), # order_total_amount  ← 中高
        rng.uniform(1, 4),        # order_item_count
        rng.uniform(5, 35),       # order_drug_quantity
        0.0 if rng.random() < 0.6 else 1.0,  # order_is_night
        rng.uniform(5, 40),       # order_doctor_rx_1d
        rng.uniform(3, 20),       # order_doctor_patient_1d
        rng.uniform(1, 6),        # order_diagnosis_same_7d
        0.0 if rng.random() < 0.6 else 1.0,  # order_receiver_not_self
        rng.uniform(0, 3),        # addr_visit_count
        0.5 if rng.random() < 0.6 else 1.0,  # addr_is_new
        1.0,                      # addr_cross_region  ← 异地
    ], dtype=np.float32)


def _gen_normal_user(rng: random.Random) -> np.ndarray:
    """正常患者 (低风险, 通过/标记)."""
    return np.array([
        rng.uniform(0, 6),        # user_total_visits 少
        rng.uniform(0, 2),        # user_visits_7d
        rng.uniform(0, 3),        # user_visits_30d
        rng.uniform(0, 1),        # user_cancel_count  ← 低
        0.0,                      # user_cancel_24h  ← 0
        rng.uniform(1, 2),        # user_hospital_count  ← 固定 1-2 家
        0.0,                      # user_claim_hospitals_1h  ← 0
        rng.uniform(0, 3),        # user_claim_count
        rng.uniform(0, 3000),     # user_claim_amount  ← 低
        rng.uniform(0, 2),        # user_claim_30d_count
        rng.uniform(0, 2500),     # user_claim_30d_amount
        rng.uniform(0, 3),        # user_rx_count
        rng.uniform(0, 1000),     # user_drug_amount  ← 低
        0.0,                      # user_card_blacklist_hit  ← 不撞黑
        rng.uniform(0, 1500),     # order_total_amount
        rng.uniform(1, 2),        # order_item_count
        rng.uniform(0, 14),       # order_drug_quantity  ← 常规量
        0.0 if rng.random() < 0.9 else 1.0,  # order_is_night  ← 大概率白天
        rng.uniform(1, 12),       # order_doctor_rx_1d  ← 医生工作量正常
        rng.uniform(1, 8),        # order_doctor_patient_1d
        rng.uniform(0, 2),        # order_diagnosis_same_7d
        0.0,                      # order_receiver_not_self  ← 本人收件
        rng.uniform(1, 5),        # addr_visit_count  ← 常去医院
        0.0 if rng.random() < 0.7 else 1.0,  # addr_is_new  ← 大概率老医院
        0.0 if rng.random() < 0.8 else 1.0,  # addr_cross_region  ← 大概率本地
    ], dtype=np.float32)


# 6 种正例模式 + 1 种负例
POSITIVE_PATTERNS = [
    _gen_card_fraud, _gen_doctor_tongfang, _gen_overdose,
    _gen_scalper, _gen_proxy_buyer, _gen_mixed_high_risk,
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
        description="教学场景 XGBoost 演示模型训练 (医疗版, 不依赖 DB, 纯合成数据)"
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
    print("教学场景 XGBoost 演示模型训练 (医疗风控)")
    print("=" * 70)
    print(f"样本数: {args.n} (正例 {args.pos_ratio*100:.0f}% / 负例 {(1-args.pos_ratio)*100:.0f}%)")
    print(f"模型保存: {args.model_path}")
    print("=" * 70)

    # 1. 生成合成数据
    print(f"\n[1/3] 生成 {args.n} 合成样本 (6 种医疗高风险模式 + 1 种正常模式)...")
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
    print("  python run_app.py                    # 启动 Web 服务, 自动加载此模型")
    print("  浏览器访问 http://localhost:8000       # 风险检查页能看到 XGBoost 评分")
    print("=" * 70)


if __name__ == "__main__":
    main()
