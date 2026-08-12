"""银行信贷风控 - 数据生成器测试 (RED 基线).

期望 gen_10w_data 模块银行化:
  1. 风险画像分布 80% 正常 / 15% 中 / 5% 高 (RISK_TIERS 常量)
  2. 暴露银行领域生成函数 (客户/申请/还款/逾期/投诉)
  3. 贷款申请行包含银行时间线字段 (apply/approve/loan/mature_time)
"""
import importlib


def _gen_module():
    """导入 scripts/gen_10w_data 作为模块."""
    import sys
    from pathlib import Path

    scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return importlib.import_module("gen_10w_data")


def test_gen_has_bank_risk_tiers():
    """风险画像分布常量: 80% 正常 / 15% 中 / 5% 高."""
    mod = _gen_module()
    assert hasattr(mod, "RISK_TIERS"), "缺少 RISK_TIERS 常量"
    tiers = mod.RISK_TIERS
    assert {"normal", "medium", "high"} <= set(tiers.keys())
    assert abs(tiers["normal"] - 0.8) < 1e-6
    assert abs(tiers["medium"] - 0.15) < 1e-6
    assert abs(tiers["high"] - 0.05) < 1e-6


def test_gen_has_bank_generators():
    """模块暴露银行领域生成函数."""
    mod = _gen_module()
    for fn in ("gen_customers", "gen_loan_applications", "gen_repayments",
               "gen_overdues", "gen_complaints"):
        assert hasattr(mod, fn), f"缺少银行生成函数 {fn}"


def test_gen_loan_application_timeline_fields():
    """贷款申请行包含银行时间线字段."""
    mod = _gen_module()
    assert hasattr(mod, "loan_application_row"), "缺少 loan_application_row 函数"
    row = mod.loan_application_row.__doc__ or ""
    assert "apply_time" in row and "approve_time" in row, "时间线字段缺失"
    assert "mature_time" in row, "到期时间缺失"


def test_gen_has_bank_scale_defaults():
    """默认规模: 5000 客户 / 3 万申请 (D8 决策)."""
    mod = _gen_module()
    assert hasattr(mod, "DEFAULT_N_CUSTOMER"), "缺少 DEFAULT_N_CUSTOMER"
    assert mod.DEFAULT_N_CUSTOMER == 5000
    assert hasattr(mod, "DEFAULT_N_LOAN"), "缺少 DEFAULT_N_LOAN"
    assert mod.DEFAULT_N_LOAN == 30000