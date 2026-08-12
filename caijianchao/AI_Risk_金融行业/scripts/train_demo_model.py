"""
金融风控系统 - 教学场景 XGBoost 演示模型训练 (P4-L4 2026-08-08, 40 维特征版重写)

【目的】
  不依赖 DB, 纯 numpy 合成 2000 样本, 训练一个针对 40 维特征体系的合理 XGBoost 模型.
  训完保存到 app/engine/xgb_model.json, run_app.py 启动时直接加载.

【为什么需要这个脚本】
  用户的真实 DB 数据是教学造数据 (gen_risk_data_with_dates.py), 正例比例 < 3%, 训出 val_auc ≈ 0.5.
  这个脚本合成"已知能触发规则"的样本 (高逾期/行为异常/大额/多设备/夜间高频 等),
  训出针对业务场景的合理模型 (val_auc > 0.85).

【6 种高风险模式】
  1. 高逾期率 (overdue_days > 30 / overdue_amount 高 → 信贷审批规则)
  2. 行为异常 (信息/密码频繁变更, 设备风险分高, 敏感操作密集 → 行为异常规则)
  3. 大额交易 (txn_amount > 50000 / is_first_large → 交易反欺诈规则)
  4. 多设备 (device_account_count > 5 / IP 频繁变更 → 反洗钱规则)
  5. 夜间高频 (beh_night_operation_count_30d 高 + 现金/转账密集 → 行为异常/反洗钱)
  6. 混合高风险 (上面多种特征都偏高)

【字符串特征约定】
  40 维中有 6 个字符串特征 (channel_type/country_code/from_account_type/to_account_type/
  device_env/loan_purpose), ml_model._features_to_array 里 float() 失败会回退 0.0.
  本脚本统一填 0.0, 跟 feature.py 生产路径完全一致.

【用法】
  .venv\\Scripts\\python.exe scripts\\train_demo_model.py                    # 默认 2000 样本, 训 200 轮
  .venv\\Scripts\\python.exe scripts\\train_demo_model.py --n 5000            # 5000 样本
  .venv\\Scripts\\python.exe scripts\\train_demo_model.py --model-path ml_models/xgb_demo.json
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

from app.engine.ml_model import FEATURE_COLUMNS, _features_to_array, train_and_save


# ============================================================
# 6 种高风险模式 + 1 种正常账户模式
# 跟 FEATURE_COLUMNS 40 维特征一一对应
# ============================================================

N_FEATURES = len(FEATURE_COLUMNS)
assert N_FEATURES == 40, f"必须是 40 维特征, 实际 {N_FEATURES}"

# 6 个字符串特征: ml_model._features_to_array 里 float() 失败回退 0.0, 这里统一填 0.0
STRING_FEATURES = {
    "channel_type", "country_code", "from_account_type",
    "to_account_type", "device_env", "loan_purpose",
}


def _base() -> dict:
    """40 键全 0 的基准 dict, 各模式函数只覆盖有区分度的特征."""
    return {col: 0.0 for col in FEATURE_COLUMNS}


def _gen_high_overdue_rate(rng: random.Random) -> dict:
    """模式 1: 高逾期率 (触发信贷审批规则: overdue_days > 30 / overdue_amount 高)"""
    f = _base()
    f.update({
        # 事件级
        "txn_amount": rng.uniform(5000, 30000),
        "is_counter": rng.randint(0, 1),
        "hour": rng.uniform(8, 22),
        "operation_interval_sec": rng.uniform(60, 3600),
        # 账户统计 (有逾期历史的账户通常资金往来频繁)
        "daily_cash_total": rng.uniform(2000, 15000),
        "daily_transfer_count": rng.uniform(3, 15),
        "daily_fail_count": rng.uniform(0, 3),
        "last_txn_days": rng.uniform(0, 7),
        "large_incoming_count": rng.uniform(0, 3),
        "per_txn_amount": rng.uniform(3000, 20000),
        "total_in_amount": rng.uniform(50000, 300000),
        "hold_minutes": rng.uniform(30, 1440),
        "device_account_count": rng.uniform(2, 5),
        "txn_count_30d_to_new": rng.uniform(3, 15),
        "counterparty_reg_days": rng.uniform(5, 90),
        # 信贷特征 ← 高风险核心
        "credit_inquiry_3m": rng.uniform(5, 15),
        "credit_usage_rate": rng.uniform(0.6, 0.95),
        "duration_months": rng.uniform(6, 36),
        "loan_to_income_ratio": rng.uniform(1.5, 3.0),
        "overdue_days": rng.uniform(30, 90),
        "overdue_amount": rng.uniform(10000, 100000),
        "unsettled_lender_count": rng.uniform(3, 8),
        "is_approved": 0,
        # 行为特征 (偏异常)
        "beh_dormant_days": rng.uniform(0, 15),
        "beh_info_change_count_30d": rng.uniform(1, 5),
        "beh_password_change_count_30d": rng.uniform(0, 3),
        "beh_device_env_risk_score": rng.uniform(0.3, 0.6),
        "beh_sensitive_op_interval_min": rng.uniform(30, 300),
        "beh_login_failure_count_7d": rng.uniform(1, 8),
        "beh_ip_change_count_30d": rng.uniform(2, 8),
        "beh_address_change_count_30d": rng.uniform(0, 4),
        "beh_night_operation_count_30d": rng.uniform(1, 8),
        "beh_high_risk_operation_count_30d": rng.uniform(1, 5),
    })
    return f


def _gen_behavior_anomaly(rng: random.Random) -> dict:
    """模式 2: 行为异常 (触发行为异常规则: 信息/密码频繁变更, 设备风险分高, 敏感操作密集)"""
    f = _base()
    f.update({
        # 事件级
        "txn_amount": rng.uniform(3000, 20000),
        "is_counter": rng.randint(0, 1),
        "hour": rng.uniform(0, 23),
        "operation_interval_sec": rng.uniform(10, 600),      # 操作密集
        # 账户统计
        "daily_cash_total": rng.uniform(5000, 30000),
        "daily_transfer_count": rng.uniform(2, 10),
        "daily_fail_count": rng.uniform(1, 8),
        "last_txn_days": rng.uniform(0, 10),
        "per_txn_amount": rng.uniform(2000, 15000),
        "total_in_amount": rng.uniform(30000, 200000),
        "hold_minutes": rng.uniform(30, 1200),
        "device_account_count": rng.uniform(1, 4),
        "txn_count_30d_to_new": rng.uniform(2, 10),
        "counterparty_reg_days": rng.uniform(10, 120),
        # 信贷特征 (中等)
        "credit_inquiry_3m": rng.uniform(1, 6),
        "credit_usage_rate": rng.uniform(0.3, 0.7),
        "duration_months": rng.uniform(12, 48),
        "loan_to_income_ratio": rng.uniform(0.5, 1.5),
        "overdue_days": rng.uniform(0, 20),
        "overdue_amount": rng.uniform(0, 30000),
        "unsettled_lender_count": rng.uniform(0, 3),
        "is_approved": rng.randint(0, 1),
        # 行为特征 ← 高风险核心
        "beh_dormant_days": rng.uniform(0, 10),
        "beh_info_change_count_30d": rng.uniform(4, 12),
        "beh_password_change_count_30d": rng.uniform(2, 6),
        "beh_device_env_risk_score": rng.uniform(0.5, 0.9),
        "beh_sensitive_op_interval_min": rng.uniform(5, 60),
        "beh_login_failure_count_7d": rng.uniform(3, 15),
        "beh_ip_change_count_30d": rng.uniform(5, 15),
        "beh_address_change_count_30d": rng.uniform(2, 6),
        "beh_night_operation_count_30d": rng.uniform(5, 20),
        "beh_high_risk_operation_count_30d": rng.uniform(4, 12),
    })
    return f


def _gen_high_amount(rng: random.Random) -> dict:
    """模式 3: 大额交易 (触发交易反欺诈规则: txn_amount > 50000 / is_first_large)"""
    f = _base()
    f.update({
        # 事件级 ← 高风险核心
        "txn_amount": rng.uniform(50000, 500000),
        "is_counter": rng.randint(0, 1),
        "hour": rng.uniform(8, 22),
        "operation_interval_sec": rng.uniform(60, 3600),
        # 账户统计
        "daily_cash_total": rng.uniform(0, 20000),
        "daily_transfer_count": rng.uniform(0, 5),
        "daily_fail_count": rng.uniform(0, 2),
        "last_txn_days": rng.uniform(0, 5),
        "is_first_large": 1,
        "large_incoming_count": rng.uniform(1, 8),
        "per_txn_amount": rng.uniform(30000, 200000),
        "total_in_amount": rng.uniform(200000, 2000000),
        "hold_minutes": rng.uniform(10, 720),               # 快速进出
        "device_account_count": rng.uniform(1, 3),
        "txn_count_30d_to_new": rng.uniform(2, 10),
        "counterparty_reg_days": rng.uniform(1, 30),        # 对端新户
        # 信贷特征 (低)
        "credit_inquiry_3m": rng.uniform(0, 2),
        "credit_usage_rate": rng.uniform(0.1, 0.4),
        "duration_months": rng.uniform(12, 60),
        "loan_to_income_ratio": rng.uniform(0.2, 0.8),
        "overdue_days": 0,
        "overdue_amount": 0,
        "unsettled_lender_count": rng.uniform(0, 2),
        "is_approved": rng.randint(0, 1),
        # 行为特征 (长期不动户 + 突然大额)
        "beh_dormant_days": rng.uniform(30, 180),
        "beh_info_change_count_30d": rng.uniform(0, 2),
        "beh_password_change_count_30d": rng.uniform(0, 1),
        "beh_device_env_risk_score": rng.uniform(0.1, 0.4),
        "beh_sensitive_op_interval_min": rng.uniform(120, 720),
        "beh_login_failure_count_7d": rng.uniform(0, 2),
        "beh_ip_change_count_30d": rng.uniform(1, 5),
        "beh_address_change_count_30d": rng.uniform(0, 2),
        "beh_night_operation_count_30d": rng.uniform(0, 3),
        "beh_high_risk_operation_count_30d": rng.uniform(0, 3),
    })
    return f


def _gen_multi_device(rng: random.Random) -> dict:
    """模式 4: 多设备 (触发反洗钱规则: device_account_count > 5 / IP 变更频繁)"""
    f = _base()
    f.update({
        # 事件级
        "txn_amount": rng.uniform(2000, 50000),
        "is_counter": rng.randint(0, 1),
        "hour": rng.uniform(8, 24),
        "operation_interval_sec": rng.uniform(30, 1800),
        # 账户统计
        "daily_cash_total": rng.uniform(5000, 50000),
        "daily_transfer_count": rng.uniform(1, 10),
        "daily_fail_count": rng.uniform(1, 5),
        "last_txn_days": rng.uniform(0, 5),
        "large_incoming_count": rng.uniform(1, 6),
        "per_txn_amount": rng.uniform(2000, 20000),
        "total_in_amount": rng.uniform(50000, 500000),
        "hold_minutes": rng.uniform(10, 600),
        "device_account_count": rng.uniform(5, 12),         # ← 高风险核心
        "txn_count_30d_to_new": rng.uniform(3, 12),
        "counterparty_reg_days": rng.uniform(5, 120),
        # 信贷特征 (中等)
        "credit_inquiry_3m": rng.uniform(1, 5),
        "credit_usage_rate": rng.uniform(0.2, 0.6),
        "duration_months": rng.uniform(12, 48),
        "loan_to_income_ratio": rng.uniform(0.3, 1.2),
        "overdue_days": rng.uniform(0, 15),
        "overdue_amount": rng.uniform(0, 20000),
        "unsettled_lender_count": rng.uniform(0, 3),
        "is_approved": rng.randint(0, 1),
        # 行为特征 ← 高风险核心
        "beh_dormant_days": rng.uniform(0, 20),
        "beh_info_change_count_30d": rng.uniform(2, 8),
        "beh_password_change_count_30d": rng.uniform(1, 5),
        "beh_device_env_risk_score": rng.uniform(0.4, 0.8),
        "beh_sensitive_op_interval_min": rng.uniform(15, 300),
        "beh_login_failure_count_7d": rng.uniform(1, 10),
        "beh_ip_change_count_30d": rng.uniform(8, 25),      # ← 高风险核心
        "beh_address_change_count_30d": rng.uniform(3, 8),  # ← 高风险核心
        "beh_night_operation_count_30d": rng.uniform(3, 15),
        "beh_high_risk_operation_count_30d": rng.uniform(2, 8),
    })
    return f


def _gen_night_high_freq(rng: random.Random) -> dict:
    """模式 5: 夜间高频 (触发行为异常/反洗钱规则: 夜间操作频繁 + 交易激增)"""
    f = _base()
    f.update({
        # 事件级 ← 高风险核心 (夜间)
        "txn_amount": rng.uniform(1000, 20000),
        "is_counter": rng.randint(0, 1),
        "hour": rng.uniform(22, 24) if rng.random() < 0.7 else rng.uniform(0, 4),
        "operation_interval_sec": rng.uniform(10, 300),     # 高频
        # 账户统计
        "daily_cash_total": rng.uniform(20000, 150000),     # 现金进出密集
        "daily_transfer_count": rng.uniform(5, 25),
        "daily_fail_count": rng.uniform(2, 8),
        "last_txn_days": rng.uniform(0, 3),
        "large_incoming_count": rng.uniform(1, 6),
        "per_txn_amount": rng.uniform(1000, 15000),
        "total_in_amount": rng.uniform(100000, 800000),
        "hold_minutes": rng.uniform(5, 360),
        "device_account_count": rng.uniform(2, 6),
        "txn_count_30d_to_new": rng.uniform(5, 20),
        "counterparty_reg_days": rng.uniform(3, 60),
        # 信贷特征 (中等)
        "credit_inquiry_3m": rng.uniform(2, 8),
        "credit_usage_rate": rng.uniform(0.4, 0.8),
        "duration_months": rng.uniform(6, 36),
        "loan_to_income_ratio": rng.uniform(0.8, 2.0),
        "overdue_days": rng.uniform(0, 25),
        "overdue_amount": rng.uniform(0, 40000),
        "unsettled_lender_count": rng.uniform(0, 4),
        "is_approved": rng.randint(0, 1),
        # 行为特征 ← 高风险核心
        "beh_dormant_days": 0,
        "beh_info_change_count_30d": rng.uniform(2, 7),
        "beh_password_change_count_30d": rng.uniform(1, 4),
        "beh_device_env_risk_score": rng.uniform(0.3, 0.7),
        "beh_sensitive_op_interval_min": rng.uniform(3, 40),
        "beh_login_failure_count_7d": rng.uniform(2, 10),
        "beh_ip_change_count_30d": rng.uniform(4, 12),
        "beh_address_change_count_30d": rng.uniform(1, 5),
        "beh_night_operation_count_30d": rng.uniform(20, 50),  # ← 高风险核心
        "beh_high_risk_operation_count_30d": rng.uniform(8, 20),
    })
    return f


def _gen_mixed_high_risk(rng: random.Random) -> dict:
    """模式 6: 混合高风险 (多种特征都偏高, 最难判但学习价值高)"""
    f = _base()
    f.update({
        # 事件级
        "txn_amount": rng.uniform(20000, 300000),
        "is_counter": rng.randint(0, 1),
        "hour": rng.uniform(0, 24),
        "operation_interval_sec": rng.uniform(10, 900),
        # 账户统计
        "daily_cash_total": rng.uniform(20000, 200000),
        "daily_transfer_count": rng.uniform(5, 25),
        "daily_fail_count": rng.uniform(2, 10),
        "last_txn_days": rng.uniform(0, 5),
        "is_first_large": rng.randint(0, 1),
        "large_incoming_count": rng.uniform(2, 10),
        "per_txn_amount": rng.uniform(10000, 100000),
        "total_in_amount": rng.uniform(200000, 2000000),
        "hold_minutes": rng.uniform(5, 600),
        "device_account_count": rng.uniform(4, 10),
        "txn_count_30d_to_new": rng.uniform(5, 20),
        "counterparty_reg_days": rng.uniform(1, 60),
        # 信贷特征 ← 偏高
        "credit_inquiry_3m": rng.uniform(4, 12),
        "credit_usage_rate": rng.uniform(0.5, 0.9),
        "duration_months": rng.uniform(6, 36),
        "loan_to_income_ratio": rng.uniform(1.0, 2.5),
        "overdue_days": rng.uniform(10, 60),
        "overdue_amount": rng.uniform(5000, 80000),
        "unsettled_lender_count": rng.uniform(2, 7),
        "is_approved": 0,
        # 行为特征 ← 偏高
        "beh_dormant_days": rng.uniform(0, 10),
        "beh_info_change_count_30d": rng.uniform(3, 10),
        "beh_password_change_count_30d": rng.uniform(2, 6),
        "beh_device_env_risk_score": rng.uniform(0.5, 0.9),
        "beh_sensitive_op_interval_min": rng.uniform(5, 120),
        "beh_login_failure_count_7d": rng.uniform(3, 15),
        "beh_ip_change_count_30d": rng.uniform(6, 20),
        "beh_address_change_count_30d": rng.uniform(2, 8),
        "beh_night_operation_count_30d": rng.uniform(10, 40),
        "beh_high_risk_operation_count_30d": rng.uniform(6, 18),
    })
    return f


def _gen_normal_user(rng: random.Random) -> dict:
    """正常账户 (低风险, 通过/标���)."""
    f = _base()
    f.update({
        # 事件级
        "txn_amount": rng.uniform(100, 5000),
        "is_counter": rng.randint(0, 1),
        "hour": rng.uniform(9, 20),
        "operation_interval_sec": rng.uniform(300, 3600),   # 低频
        # 账户统计 (一切偏低)
        "daily_cash_total": rng.uniform(0, 5000),
        "daily_transfer_count": rng.uniform(0, 3),
        "daily_fail_count": 0,
        "last_txn_days": rng.uniform(0, 3),
        "is_first_large": 0,
        "large_incoming_count": rng.uniform(0, 1),
        "per_txn_amount": rng.uniform(100, 3000),
        "total_in_amount": rng.uniform(5000, 100000),
        "hold_minutes": rng.uniform(0, 120),
        "device_account_count": rng.uniform(1, 2),
        "txn_count_30d_to_new": rng.uniform(0, 1),
        "counterparty_reg_days": rng.uniform(365, 3000),    # 老对端
        # 信贷特征 (干净)
        "credit_inquiry_3m": rng.uniform(0, 2),
        "credit_usage_rate": rng.uniform(0, 0.3),
        "duration_months": rng.uniform(12, 60),
        "loan_to_income_ratio": rng.uniform(0, 0.3),
        "overdue_days": rng.uniform(0, 2),
        "overdue_amount": rng.uniform(0, 1000),
        "unsettled_lender_count": rng.uniform(0, 1),
        "is_approved": 1,
        # 行为特征 (正常)
        "beh_dormant_days": rng.uniform(0, 10),
        "beh_info_change_count_30d": rng.uniform(0, 1),
        "beh_password_change_count_30d": rng.uniform(0, 1),
        "beh_device_env_risk_score": rng.uniform(0, 0.2),
        "beh_sensitive_op_interval_min": rng.uniform(60, 720),
        "beh_login_failure_count_7d": rng.uniform(0, 1),
        "beh_ip_change_count_30d": rng.uniform(0, 2),
        "beh_address_change_count_30d": rng.uniform(0, 1),
        "beh_night_operation_count_30d": rng.uniform(0, 1),
        "beh_high_risk_operation_count_30d": rng.uniform(0, 1),
    })
    return f


# 6 种正例模式 + 1 种负例
POSITIVE_PATTERNS = [
    _gen_high_overdue_rate, _gen_behavior_anomaly, _gen_high_amount,
    _gen_multi_device, _gen_night_high_freq, _gen_mixed_high_risk,
]
NEGATIVE_PATTERN = _gen_normal_user


def gen_synthetic_dataset(n: int = 2000, pos_ratio: float = 0.5, seed: int = 42):
    """生成合成训练数据集.

    Args:
        n: 总样本数
        pos_ratio: 正例比例 (默认 0.5)
        seed: 随机种子

    Returns:
        X: (N, 40) float32 (字符串特征 0.0, 与 _features_to_array 一致)
        y: (N,) int (0/1)
    """
    rng = random.Random(seed)
    np.random.seed(seed)

    n_pos = int(n * pos_ratio)
    n_neg = n - n_pos

    rows, labels = [], []
    # 正例: 6 种模式轮换
    for i in range(n_pos):
        pattern = POSITIVE_PATTERNS[i % len(POSITIVE_PATTERNS)]
        rows.append(_features_to_array(pattern(rng))[0])
        labels.append(1)
    # 负例: 1 种模式
    for _ in range(n_neg):
        rows.append(_features_to_array(NEGATIVE_PATTERN(rng))[0])
        labels.append(0)

    X = np.vstack(rows).astype(np.float32)
    y = np.array(labels, dtype=np.int32)

    # 乱序
    idx = np.random.permutation(n)
    return X[idx], y[idx]


def self_check(n_check: int = 50, seed: int = 7) -> None:
    """端到端自检: 模式函数 → dict(40键) → _features_to_array → (1,40) 断言."""
    print("\n[自检] 模式函数与 40 维特征对齐检查...")
    rng = random.Random(seed)
    for name, fn in [(f.__name__, f) for f in POSITIVE_PATTERNS] + [("_gen_normal_user", NEGATIVE_PATTERN)]:
        for _ in range(n_check):
            d = fn(rng)
            assert len(d) == N_FEATURES, f"{name}: dict 缺键, {len(d)} != {N_FEATURES}"
            arr = _features_to_array(d)
            assert arr.shape == (1, N_FEATURES), f"{name}: shape {arr.shape} != (1, {N_FEATURES})"
            for col in STRING_FEATURES:
                assert d[col] == 0.0, f"{name}: 字符串特征 {col} 必须为 0.0"
    print(f"  OK: 7 个模式函数 × {n_check} 次, 全部输出 40 维合法向量")


def main():
    parser = argparse.ArgumentParser(
        description="教学场景 XGBoost 演示模型训练 (不依赖 DB, 纯合成数据, 40 维特征)"
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
    print("教学场景 XGBoost 演示模型训练 (40 维特征体系)")
    print("=" * 70)
    print(f"样本数: {args.n} (正例 {args.pos_ratio*100:.0f}% / 负例 {(1-args.pos_ratio)*100:.0f}%)")
    print(f"特征维度: {N_FEATURES} (必须 40)")
    print(f"模型保存: {args.model_path}")
    print("=" * 70)

    # 0. 自检 (先验证再训练, 防模式函数写错)
    self_check()

    # 1. 生成合成数据
    print(f"\n[1/3] 生成 {args.n} 合成样本 (6 种高风险模式 + 1 种正常模式)...")
    X, y = gen_synthetic_dataset(n=args.n, pos_ratio=args.pos_ratio, seed=args.seed)
    assert X.shape == (args.n, N_FEATURES), f"X.shape={X.shape} 应为 ({args.n}, {N_FEATURES})"
    print(f"  X.shape={X.shape}, 正例={int(y.sum())} ({y.mean():.2%})")

    # 2. 训练 (复用 ml_model.train_and_save: warmup + AUC 早停 + F1 阈值扫描 + 假收敛检测)
    print("\n[2/3] 训练 XGBoost (复用 ml_model.train_and_save)...")
    metrics, booster = train_and_save(
        X, y,
        model_path=args.model_path,
        num_boost_round=args.num_boost_round,
        return_model=True,
    )
    print(f"  全量: acc={metrics['accuracy']:.4f}, auc={metrics['auc']:.4f}, f1={metrics['f1']:.4f}")
    if "val_accuracy" in metrics:
        print(f"  验证集: acc={metrics['val_accuracy']:.4f}, auc={metrics['val_auc']:.4f}, "
              f"f1={metrics['val_f1']:.4f} (最佳阈值 {metrics['best_f1_threshold']})")
    print(f"  scale_pos_weight={metrics['scale_pos_weight']:.2f}, best_iter={metrics['best_iteration']}")

    # 3. 特征重要性 Top10
    print("\n[3/3] 特征重要性 Top10 (gain):")
    try:
        score = booster.get_score(importance_type="gain")
        top = sorted(score.items(), key=lambda kv: kv[1], reverse=True)[:10]
        for feat, gain in top:
            print(f"  {feat:<38} {gain:.2f}")
    except Exception as e:
        print(f"  (跳过特征重要性: {e})")

    # 模型文件大小
    size_kb = os.path.getsize(args.model_path) / 1024
    print(f"\n模型文件: {args.model_path} ({size_kb:.1f} KB)")

    print("\n" + "=" * 70)
    print("训练完成!")
    print(f"  val_auc = {metrics.get('val_auc', metrics.get('auc', 0)):.4f} "
          f"{'OK' if metrics.get('val_auc', 0) > 0.85 else '(< 0.85 注意)'}")
    print("=" * 70)
    print("下一步:")
    print("  python run_app.py                    # 启动 Web 服务, 自动加载此模型")
    print("  浏览器访问 http://localhost:8000       # 风险检查页能看到 XGBoost 评分")
    print("=" * 70)


if __name__ == "__main__":
    main()
