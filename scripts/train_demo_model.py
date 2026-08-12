"""
物流风控系统 - 教学场景 XGBoost 演示模型训练 (物流版)

【目的】
  不依赖 DB, 纯 numpy 合成 2000 样本, 训练一个针对 8 条物流规则 + 25 维物流特征的合理 XGBoost 模型.
  训完保存到 app/engine/xgb_model.json, run_app.py 启动时直接加载.

【为什么需要这个脚本】
  用户的真实 DB 数据是教学造数据 (gen_risk_data_with_dates.py), 正例比例可能偏低,
  训出 val_auc ≈ 0.5. 这个脚本合成"已知能触发物流规则"的样本, 训出针对业务场景的合理模型.

【6 种物流高风险模式 (对应 8 条物流规则)】
  1. 未实名寄件   (R001: user_real_name_verified=0)
  2. 危险品瞒报   (R002: 危险品申报 + 每公斤价值 < 50)
  3. 跨境违禁品   (R005: 国际件 + 危险品申报, 一票否决)
  4. COD 卷款     (R008: COD 逾期记录 + 大额代收 ≥1000, 一票否决)
  5. 大额低报     (R025: 申报 ≥3000 但每公斤价值 < 100)
  6. 改派异常/黑地址 (R018: 高频换收件人 + 高价值; R030: 地址命中黑名单, 一票否决)

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
from app.engine.ml_model import FEATURE_COLUMNS


# ============================================================
# 6 种物流高风险模式 + 1 种正常模式
# 跟 feature.py 25 维物流特征一一对应, 跟 8 条物流规则的触发条件对得上
# ============================================================

FEATURE_NAMES = FEATURE_COLUMNS
N_FEATURES = len(FEATURE_NAMES)
assert N_FEATURES == 25, f"必须是 25 维特征, 实际 {N_FEATURES}"

# 省份编码 (跟 init_business_data.sql 的 region.province_code 对齐, 北京=1...新疆=31)
def _sender_receiver_province(rng: random.Random, cross: bool = False) -> tuple:
    """返回 (sender_province_code, receiver_province_code); cross=True 时强制跨省."""
    s = rng.randint(1, 31)
    if cross:
        r = rng.choice([x for x in range(1, 32) if x != s])
    else:
        r = rng.choice([s] + [x for x in range(1, 32) if x != s])
    return s, r


def _base_user_fields(rng: random.Random, *, account_age=(30, 800), verified=1.0,
                     enterprise=0.0, parcel_count=(1, 30), parcel_30d=(0, 8),
                     parcel_7d=(0, 4), avg_declared=(50, 1500), receivers=(1, 2),
                     cod_overdue=0.0, black_hit=0.0) -> list:
    """用户维度 10 个特征 (共用模板, 各模式覆盖关键字段)."""
    return [
        rng.uniform(*account_age),       # user_account_age_days
        verified,                        # user_real_name_verified
        enterprise,                      # user_is_enterprise
        rng.randint(*parcel_count),      # user_total_parcel_count
        rng.randint(*parcel_30d),        # user_total_parcel_count_30d
        rng.randint(*parcel_7d),         # user_total_parcel_count_7d
        rng.uniform(*avg_declared),      # user_avg_declared_value
        rng.randint(*receivers),         # user_distinct_receiver_count
        cod_overdue,                     # user_cod_overdue_count
        black_hit,                       # user_blacklist_hit_count
    ]


def _base_order_fields(rng: random.Random, *, weight=(0.5, 10), declared=(20, 1500),
                      per_kg=(30, 500), pieces=(1, 3), intl=0.0, danger=0.0,
                      has_cod=0.0, cod_amount=0.0) -> list:
    """包裹维度 8 个特征 (共用模板, 各模式覆盖关键字段)."""
    return [
        rng.uniform(*weight),            # order_weight_kg
        rng.uniform(*declared),          # order_declared_value
        rng.uniform(*per_kg),            # order_value_per_kg
        rng.randint(*pieces),            # order_piece_count
        intl,                            # order_is_international
        danger,                          # order_is_dangerous_declared
        has_cod,                         # order_has_cod
        cod_amount,                      # order_cod_amount
    ]


def _base_addr_fields(rng: random.Random, *, cross=False, same_addr24h=1.0,
                      black_hit=0.0, proxy=0.0, sender_black=0.0) -> list:
    """地址维度 7 个特征 (共用模板, 各模式覆盖关键字段)."""
    s, r = _sender_receiver_province(rng, cross=cross)
    return [
        s,                               # addr_sender_province
        r,                               # addr_receiver_province
        1.0 if s != r else 0.0,          # addr_is_cross_province
        same_addr24h,                    # addr_same_address_sender_count_24h
        black_hit,                       # addr_address_blacklist_hit
        proxy,                           # addr_is_proxy_received
        sender_black,                    # addr_sender_is_blacklisted
    ]


def _gen_unverified_user(rng: random.Random) -> np.ndarray:
    """模式 1: 未实名寄件 (R001: user_real_name_verified=0)."""
    return np.array(
        _base_user_fields(rng, verified=0.0, account_age=(1, 30))
        + _base_order_fields(rng)
        + _base_addr_fields(rng),
        dtype=np.float32,
    )


def _gen_dangerous_hide(rng: random.Random) -> np.ndarray:
    """模式 2: 危险品瞒报 (R002: 危险品申报 + 每公斤价值 < 50)."""
    return np.array(
        _base_user_fields(rng)
        + _base_order_fields(
            rng,
            weight=(10, 50),      # 大重量
            declared=(100, 800),  # 申报价值偏低 → 每公斤 2~40 < 50
            per_kg=(2, 40),       # 价值密度异常低
            pieces=(1, 4),
            danger=1.0,           # 危险品申报
        )
        + _base_addr_fields(rng),
        dtype=np.float32,
    )


def _gen_cross_border(rng: random.Random) -> np.ndarray:
    """模式 3: 跨境违禁品 (R005: 国际件 + 危险品申报, 一票否决)."""
    return np.array(
        _base_user_fields(rng)
        + _base_order_fields(
            rng,
            weight=(3, 20),
            declared=(300, 3000),
            per_kg=(50, 500),
            intl=1.0,             # 国际件
            danger=1.0,           # 危险品申报
        )
        + _base_addr_fields(rng, cross=True),
        dtype=np.float32,
    )


def _gen_cod_runaway(rng: random.Random) -> np.ndarray:
    """模式 4: COD 卷款 (R008: COD 逾期 + 大额代收 ≥1000, 一票否决)."""
    return np.array(
        _base_user_fields(
            rng,
            cod_overdue=rng.randint(1, 5),   # 历史 COD 逾期
            black_hit=rng.uniform(1, 4),     # 黑名单命中 (卷款惯犯特征)
        )
        + _base_order_fields(
            rng,
            weight=(1, 10),
            declared=(500, 5000),
            per_kg=(50, 500),
            has_cod=1.0,                      # 本次 COD
            cod_amount=rng.uniform(1000, 8000),  # 大额代收 ≥1000
        )
        + _base_addr_fields(rng),
        dtype=np.float32,
    )


def _gen_underdeclare(rng: random.Random) -> np.ndarray:
    """模式 5: 大额低报 (R025: 申报 ≥3000 但每公斤价值 < 100)."""
    return np.array(
        _base_user_fields(
            rng,
            avg_declared=(2000, 6000),  # 用户平均申报价值偏高
        )
        + _base_order_fields(
            rng,
            weight=(30, 100),     # 大重量
            declared=(3000, 8000),  # 高申报价值 ≥3000
            per_kg=(30, 99),      # 每公斤价值 < 100
            pieces=(1, 6),
        )
        + _base_addr_fields(rng),
        dtype=np.float32,
    )


def _gen_change_dispatch(rng: random.Random) -> np.ndarray:
    """模式 6: 改派异常 + 黑地址 (R018: 高频换收件人+高价值; 部分 R030: 黑地址)."""
    use_black_addr = rng.random() < 0.4  # 40% 走黑地址 (R030), 60% 走改派 (R018)
    return np.array(
        _base_user_fields(
            rng,
            receivers=(3, 6),  # 高频更换收件人 ≥3
        )
        + _base_order_fields(
            rng,
            weight=(2, 30),
            declared=(2000, 6000),        # 高申报价值 ≥2000
            per_kg=(50, 500),
            pieces=(1, 5),
        )
        + _base_addr_fields(
            rng,
            black_hit=1.0 if use_black_addr else 0.0,  # 黑地址拦截
        ),
        dtype=np.float32,
    )


def _gen_normal_user(rng: random.Random) -> np.ndarray:
    """正常用户 (低风险, 通过/标记)."""
    return np.array(
        _base_user_fields(
            rng,
            verified=1.0,
            account_age=(60, 800),
            parcel_count=(1, 15),
            receivers=(1, 2),
        )
        + _base_order_fields(
            rng,
            weight=(0.5, 8),
            declared=(30, 1200),
            per_kg=(40, 500),
            pieces=(1, 3),
        )
        + _base_addr_fields(rng),
        dtype=np.float32,
    )


# 6 种正例模式 + 1 种负例
POSITIVE_PATTERNS = [
    _gen_unverified_user, _gen_dangerous_hide, _gen_cross_border,
    _gen_cod_runaway, _gen_underdeclare, _gen_change_dispatch,
]
NEGATIVE_PATTERN = _gen_normal_user


def gen_synthetic_dataset(n: int = 2000, pos_ratio: float = 0.5, seed: int = 42):
    """生成合成训练数据集 (物流版).

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

    # 正例: 6 种物流高风险模式轮换
    X_pos = np.zeros((n_pos, N_FEATURES), dtype=np.float32)
    for i in range(n_pos):
        pattern = POSITIVE_PATTERNS[i % len(POSITIVE_PATTERNS)]
        X_pos[i] = pattern(rng)

    # 负例: 1 种正常模式
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
        description="教学场景 XGBoost 演示模型训练 (物流版, 不依赖 DB, 纯合成数据)"
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
    print("教学场景 XGBoost 演示模型训练 (物流版)")
    print("=" * 70)
    print(f"样本数: {args.n} (正例 {args.pos_ratio*100:.0f}% / 负例 {(1-args.pos_ratio)*100:.0f}%)")
    print(f"模型保存: {args.model_path}")
    print("=" * 70)

    # 1. 生成合成数据
    print(f"\n[1/3] 生成 {args.n} 合成样本 (6 种物流高风险模式 + 1 种正常模式)...")
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
