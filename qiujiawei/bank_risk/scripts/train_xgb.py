"""
银行风控系统 - XGBoost 模型训练脚本

从 DB 拉交易/贷款/登录数据 → 算 25 维特征 → 生成标签 → 训练 → 评估

标签生成逻辑 (基于欺诈调研):
  label=1 (高风险) 如果满足以下任一:
    - 交易金额 > 5万 (大额转账)
    - 夜间(0-5点) + 1小时内≥3笔 (凌晨密集)
    - 新设备(<7天) + 金额>3万 (新设备大额)
    - 1小时内转入同一卡≥3次 (多卡归集)
    - 近6个月贷款申请≥3次 (多头借贷)
    - 设备关联≥5用户 (设备多人共用)
    - IP代理 或 Tor (秒拨代理)
  额外加 10% 噪声 (模拟真实标注误差)

用法:
  python -m bank_risk.scripts.train_xgb
  python -m bank_risk.scripts.train_xgb --noise 0.15   # 15% 噪声
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime

import numpy as np
from sqlalchemy import select

from bank_risk.app.database import AsyncSessionLocal
from bank_risk.app.engine.feature import (
    FEATURE_COLUMNS,
    compute_all_features,
)
from bank_risk.app.engine.ml_model import train_and_save, FEATURE_COLUMNS as ML_FEATURE_COLUMNS
from bank_risk.app.models import Transaction, LoanApplication, LoginLog

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _generate_label(features: dict, noise_rate: float = 0.10) -> int:
    """根据特征 dict 生成标签 (0=安全, 1=高风险), 加噪声模拟标注误差."""
    is_risky = 0

    # R001: 异地大额转账 (txn_geo_changed=1 + amount>50000)
    if features.get("txn_geo_changed", 0) == 1 and features.get("txn_amount", 0) > 50000:
        is_risky = 1
    # R002: 凌晨密集操作 (txn_is_night=1 + txn_hour_freq>=3)
    elif features.get("txn_is_night", 0) == 1 and features.get("txn_hour_freq", 0) >= 3:
        is_risky = 1
    # R005: 新设备大额 (txn_device_age_days<7 + amount>30000)
    elif features.get("txn_device_age_days", 999) < 7 and features.get("txn_amount", 0) > 30000:
        is_risky = 1
    # R008: 多卡归集 (txn_to_same_card_1h>=3)
    elif features.get("txn_to_same_card_1h", 0) >= 3:
        is_risky = 1
    # R012: 信贷突击 (user_loan_count_6m>=3)
    elif features.get("user_loan_count_6m", 0) >= 3:
        is_risky = 1
    # R018: 设备多人共用 (dev_multi_user_count>=5)
    elif features.get("dev_multi_user_count", 0) >= 5:
        is_risky = 1
    # R025: IP代理/Tor
    elif features.get("ip_is_proxy", 0) == 1 or features.get("ip_is_tor", 0) == 1:
        is_risky = 1

    # 加噪声: noise_rate 概率翻转标签
    if np.random.random() < noise_rate:
        is_risky = 1 - is_risky

    return is_risky


async def collect_training_data(noise_rate: float = 0.10) -> tuple[np.ndarray, np.ndarray]:
    """从 DB 拉数据 → 算特征 → 生成标签 → 返回 (X, y)."""
    X_list = []
    y_list = []

    async with AsyncSessionLocal() as db:
        # 1. 交易事件 (转账/信用卡)
        txns = list((await db.execute(
            select(Transaction).order_by(Transaction.txn_at)
        )).scalars().all())
        logger.info("拉取交易记录: %d 条", len(txns))

        for txn in txns:
            features = await compute_all_features(
                db=db,
                event_type="转账",
                source_id=txn.txn_id,
                user_id=txn.user_id,
                event_data={"device_id": txn.device_id, "ip": txn.ip},
            )
            label = _generate_label(features, noise_rate)
            X_list.append([float(features.get(col, 0.0)) for col in FEATURE_COLUMNS])
            y_list.append(label)

        # 2. 贷款事件
        loans = list((await db.execute(
            select(LoanApplication).order_by(LoanApplication.apply_at)
        )).scalars().all())
        logger.info("拉取贷款申请: %d 条", len(loans))

        for loan in loans:
            features = await compute_all_features(
                db=db,
                event_type="贷款",
                source_id=loan.loan_id,
                user_id=loan.user_id,
                event_data={},
            )
            label = _generate_label(features, noise_rate)
            X_list.append([float(features.get(col, 0.0)) for col in FEATURE_COLUMNS])
            y_list.append(label)

        # 3. 登录事件
        logins = list((await db.execute(
            select(LoginLog).order_by(LoginLog.login_at)
        )).scalars().all())
        logger.info("拉取登录记录: %d 条", len(logins))

        for login in logins:
            features = await compute_all_features(
                db=db,
                event_type="登录",
                source_id="",
                user_id=login.user_id,
                event_data={"device_id": login.device_id, "ip": login.ip},
            )
            label = _generate_label(features, noise_rate)
            X_list.append([float(features.get(col, 0.0)) for col in FEATURE_COLUMNS])
            y_list.append(label)

    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list, dtype=np.int32)
    return X, y


async def main():
    parser = argparse.ArgumentParser(description="银行风控 XGBoost 训练")
    parser.add_argument("--noise", type=float, default=0.10, help="标签噪声率 (默认 0.10)")
    args = parser.parse_args()

    print("=" * 60)
    print("银行风控系统 - XGBoost 模型训练")
    print(f"特征族: 用户(10) + 交易(8) + 设备IP(7) = 25 维")
    print(f"标签噪声: {args.noise * 100:.0f}%")
    print("=" * 60)

    # 校验特征列对齐
    assert FEATURE_COLUMNS == ML_FEATURE_COLUMNS, (
        f"feature.py 和 ml_model.py 的 FEATURE_COLUMNS 不一致!\n"
        f"  feature.py:  {FEATURE_COLUMNS}\n"
        f"  ml_model.py: {ML_FEATURE_COLUMNS}"
    )
    print(f"\n[1] 特征列对齐校验: PASS (25 维)")

    # 采集训练数据
    print(f"\n[2] 采集训练数据:")
    X, y = await collect_training_data(noise_rate=args.noise)
    n = len(y)
    n_pos = int(np.sum(y == 1))
    n_neg = int(np.sum(y == 0))
    pos_ratio = n_pos / n if n else 0
    print(f"  总样本: {n}")
    print(f"  正例 (高风险): {n_pos} ({100 * pos_ratio:.1f}%)")
    print(f"  负例 (安全):   {n_neg} ({100 * (1 - pos_ratio):.1f}%)")

    if n_pos < 5 or n_neg < 5:
        print(f"\n[ERROR] 正例或负例太少 (< 5), 无法训练")
        sys.exit(1)

    # 训练
    print(f"\n[3] XGBoost 训练:")
    print(f"  目标函数: binary:logistic (sigmoid → P(拒绝))")
    print(f"  早停指标: auc (early_stopping={10} rounds)")
    print(f"  正负比平衡: scale_pos_weight=min(neg/pos, 10.0)")
    print()

    metrics = train_and_save(X, y)

    # 打印评估结果
    print(f"\n[4] 训练完成 — 评估指标:")
    print(f"  {'指标':<25} {'值':>10}")
    print(f"  {'-' * 35}")
    print(f"  {'样本总量':.<25} {metrics['n_train']:>10}")
    print(f"  {'正例 (高风险)':.<25} {metrics['n_pos']:>10}")
    print(f"  {'正例比例':.<25} {metrics['pos_ratio']:>10.4f}")
    print(f"  {'scale_pos_weight':.<25} {metrics['scale_pos_weight']:>10.4f}")
    print(f"  {'best_iteration':.<25} {metrics['best_iteration']:>10}")
    print(f"  {'-' * 35}")
    print(f"  {'训练集 accuracy':.<25} {metrics['accuracy']:>10.4f}")
    print(f"  {'训练集 precision':.<25} {metrics['precision']:>10.4f}")
    print(f"  {'训练集 recall':.<25} {metrics['recall']:>10.4f}")
    print(f"  {'训练集 F1':.<25} {metrics['f1']:>10.4f}")
    print(f"  {'训练集 AUC':.<25} {metrics['auc']:>10.4f}")
    print(f"  {'-' * 35}")

    val_auc = metrics.get("val_auc", 0)
    val_f1 = metrics.get("val_f1", 0)
    val_acc = metrics.get("val_accuracy", 0)
    best_thr = metrics.get("best_f1_threshold", 0.5)

    print(f"  {'验证集 accuracy':.<25} {val_acc:>10.4f}")
    print(f"  {'验证集 AUC':.<25} {val_auc:>10.4f}")
    print(f"  {'验证集 F1':.<25} {val_f1:>10.4f}")
    print(f"  {'最佳 F1 阈值':.<25} {best_thr:>10.2f}")
    print(f"  {'-' * 35}")

    # 质量验收
    is_fake = metrics.get("is_fake_convergence", False)
    print(f"  {'假收敛标志':.<25} {str(is_fake):>10}")

    print(f"\n[5] 模型保存: {metrics['model_path']}")

    # 质量判定
    print(f"\n{'=' * 60}")
    if val_auc >= 0.70 and val_f1 >= 0.50:
        print(f"质量判定: PASS  (val_auc={val_auc:.4f} >= 0.70, val_f1={val_f1:.4f} >= 0.50)")
    elif val_auc >= 0.60:
        print(f"质量判定: WARN  (val_auc={val_auc:.4f}, 模型有区分力但不够强)")
    else:
        print(f"质量判定: FAIL  (val_auc={val_auc:.4f} < 0.60, 模型无效)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
