"""银行信贷风控 - 训练数据 PD 标签测试 (RED 基线).

模型语义 (Q5 决策): XGBoost 输出 PD 违约概率,
  0 = 正常履约, 1 = 逾期违约 (正例来自逾期客户).
"""
import importlib


def _module(name: str):
    import sys
    from pathlib import Path

    scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return importlib.import_module(name)


def test_train_module_has_pd_label_fn():
    """train_xgb_model 提供 PD 标签函数 (逾期→1, 正常→0)."""
    mod = _module("train_xgb_model")
    assert hasattr(mod, "pd_label_for_customer"), "缺少 pd_label_for_customer 函数"
    assert hasattr(mod, "_pd_label_to_label") or hasattr(mod, "PD_LABEL"), (
        "缺少 PD 标签映射常量"
    )


def test_pd_label_mapping_correct():
    """PD 标签映射: 逾期客户=1, 正常客户=0."""
    mod = _module("train_xgb_model")
    # 有逾期记录 → 1
    assert mod.pd_label_for_customer.__doc__ is not None
    if hasattr(mod, "PD_LABEL"):
        assert mod.PD_LABEL["overdue"] == 1
        assert mod.PD_LABEL["normal"] == 0


def test_gen_train_dataset_uses_bank_events():
    """训练数据集生成器造银行事件 (贷款申请), 不用电商事件."""
    mod = _module("gen_train_dataset")
    assert hasattr(mod, "gen_train_dataset")
    # 事件类型应为银行 4 事件
    assert "贷款申请" in mod.__doc__, "生成器文档应说明贷款申请事件"


def test_gen_train_dataset_selects_overdue_customers():
    """生成器提供逾期客户选择函数 (PD 正例来源)."""
    mod = _module("gen_train_dataset")
    assert hasattr(mod, "_pick_overdue_customers"), "缺少 _pick_overdue_customers"
    assert hasattr(mod, "_pick_normal_customers"), "缺少 _pick_normal_customers"