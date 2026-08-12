"""银行信贷风控 - 25 维特征对齐测试 (RED 基线).

期望特征前缀: cust_*×14 (客户) / loan_*×8 (申请) / dev_*×3 (设备网络),
与 ml_model.FEATURE_COLUMNS 一一对应, 防止 XGBoost 特征错位.
"""
import pytest

from app.engine.ml_model import FEATURE_COLUMNS

# 银行 25 维特征设计 (docs/bank_risk_plan.md + CONTEXT.md 术语)
CUST_FEATURES = [
    "cust_total_loans",         # 历史申请总数
    "cust_loans_30d",           # 近 30 天申请数
    "cust_loans_7d",            # 近 7 天申请数 (多头借贷)
    "cust_total_amount",        # 历史申请总金额
    "cust_avg_loan_amount",     # 平均申请金额
    "cust_max_loan_amount",     # 最大申请金额
    "cust_overdue_count",       # 逾期次数
    "cust_overdue_rate",        # 逾期率 (逾期次数/申请数)
    "cust_overdue_amount",      # 逾期总金额
    "cust_repay_count",         # 正常还款次数
    "cust_repay_rate",          # 还款结清率 (已结清/申请数)
    "cust_reject_count",        # 被拒次数
    "cust_complaint_count",     # 投诉次数
    "cust_contact_count",       # 联系信息数
]
LOAN_FEATURES = [
    "loan_amount",              # 申请金额
    "loan_term_month",          # 期限 (月)
    "loan_debt_ratio",          # 负债率 (现有负债/申请金额)
    "loan_apply_interval_sec",       # 距上次申请间隔 (秒)
    "loan_apply_is_night",           # 是否夜间申请 (0~6 点)
    "loan_to_income",           # 贷款收入比 (申请金额/年收入)
    "loan_apply_product_count",      # 申请过的产品种类数
    "loan_income_debt_ratio",   # 收入负债比 (现有负债/年收入)
]
DEV_FEATURES = [
    "dev_device_count",         # 设备使用数
    "dev_ip_province_count",    # 申请 IP 跨省数
    "dev_is_new",               # 本次设备是否新设备 (0/1)
]

BANK_FEATURE_COLUMNS = CUST_FEATURES + LOAN_FEATURES + DEV_FEATURES


def test_bank_feature_count_is_25():
    assert len(FEATURE_COLUMNS) == 25


def test_bank_feature_prefixes():
    cust = [f for f in FEATURE_COLUMNS if f.startswith("cust_")]
    loan = [f for f in FEATURE_COLUMNS if f.startswith("loan_")]
    dev = [f for f in FEATURE_COLUMNS if f.startswith("dev_")]
    assert len(cust) == 14, f"客户维度应为 14, 当前 {len(cust)}"
    assert len(loan) == 8, f"申请维度应为 8, 当前 {len(loan)}"
    assert len(dev) == 3, f"设备维度应为 3, 当前 {len(dev)}"


def test_bank_feature_names_expected():
    missing = set(BANK_FEATURE_COLUMNS) - set(FEATURE_COLUMNS)
    extra = set(FEATURE_COLUMNS) - set(BANK_FEATURE_COLUMNS)
    assert not missing, f"缺少银行特征: {missing}"
    assert not extra, f"多余非银行特征: {extra}"


def test_bank_feature_columns_align_with_feature_module():
    """FEATURE_COLUMNS 必须与 feature.py 的 compute_* 输出 key 对齐."""
    from app.engine import feature as feature_module

    # 静态断言: 三个 compute 函数存在且返回 dict[str, float]
    assert feature_module.compute_user_features.__annotations__["return"] == dict[str, float]
    assert feature_module.compute_loan_features.__annotations__["return"] == dict[str, float]
    assert feature_module.compute_device_features.__annotations__["return"] == dict[str, float]
    assert len(FEATURE_COLUMNS) == 25
    # 前缀归属: cust_/loan_/dev_ 分别对应三个 compute 组的输出域
    prefix_to_group = {"cust_": "user", "loan_": "loan", "dev_": "device"}
    for name in FEATURE_COLUMNS:
        prefix = next((p for p in prefix_to_group if name.startswith(p)), None)
        assert prefix, f"特征 {name} 缺少合法前缀 (cust_/loan_/dev_)"
        assert hasattr(feature_module, f"compute_{prefix_to_group[prefix]}_features")