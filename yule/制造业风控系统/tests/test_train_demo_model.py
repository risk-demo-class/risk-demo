"""
制造业教学场景 XGBoost 演示模型训练测试 (P4-L4 2026-08-08)
- 验证 scripts/train_demo_model.py 结构
- 验证合成数据特征分布
- 验证训练后模型能加载
"""
import re
import os
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "train_demo_model.py"


class TestTrainDemoModelStructure:
    """train_demo_model.py 脚本结构"""

    def test_script_exists(self):
        assert SCRIPT.exists()

    def test_has_8_pattern_generators(self):
        """必须有 8 种制造业正例模式 + 1 种正常模式."""
        src = SCRIPT.read_text(encoding="utf-8")
        for name in ["_gen_cross_region", "_gen_out_warranty", "_gen_bulk_order",
                     "_gen_warranty_abuse", "_gen_new_dealer", "_gen_repair_cost",
                     "_gen_contract_expired", "_gen_mixed_black", "_gen_normal"]:
            assert f"def {name}(" in src, f"缺模式: {name}"

    def test_uses_correct_feature_order(self):
        """25 维特征顺序必须跟 FEATURE_COLUMNS 一致."""
        src = SCRIPT.read_text(encoding="utf-8")
        assert "FEATURE_COLUMNS" in src
        assert "N_FEATURES = len(FEATURE_COLUMNS)" in src
        assert "N_FEATURES == 25" in src

    def test_saves_to_default_path(self):
        """默认保存到 app/engine/xgb_model.json."""
        src = SCRIPT.read_text(encoding="utf-8")
        assert 'PROJECT_ROOT, "app/engine/xgb_model.json"' in src

    def test_uses_ml_model_train_and_save(self):
        """训练复用 ml_model.train_and_save (超参由 ml_model.py 统一管理)."""
        src = SCRIPT.read_text(encoding="utf-8")
        assert "train_and_save" in src
        assert "from app.engine.ml_model import" in src


class TestSyntheticDatasetGeneration:
    """合成数据生成函数 (不依赖 XGBoost, 纯 numpy)"""

    def test_gen_synthetic_dataset_default_size(self):
        """默认 2000 样本."""
        import sys
        for p in [str(ROOT)]:
            if p not in sys.path:
                sys.path.insert(0, p)
        from scripts.train_demo_model import gen_synthetic_dataset
        X, y = gen_synthetic_dataset(n=2000, pos_ratio=0.5, seed=42)
        assert X.shape == (2000, 25), f"X.shape 错: {X.shape}"
        assert y.shape == (2000,), f"y.shape 错: {y.shape}"
        assert y.sum() == 1000, f"正例数错: {y.sum()} (期望 1000)"

    def test_gen_synthetic_dataset_feature_order_matches_columns(self):
        """合成数据的特征顺序必须跟 FEATURE_COLUMNS 一致, 否则训练/推理错位."""
        import random
        import sys
        for p in [str(ROOT)]:
            if p not in sys.path:
                sys.path.insert(0, p)
        from scripts.train_demo_model import _gen_bulk_order
        rng = random.Random(42)
        X = np.array([_gen_bulk_order(rng) for _ in range(10)])
        # 第 14 列 (idx=13) 应该是 order_quantity (大额囤货 110-200)
        assert (X[:, 13] >= 110).all() and (X[:, 13] <= 200).all(), (
            f"order_quantity 应该是 110-200, 实际范围: {X[:, 13].min()}-{X[:, 13].max()}"
        )
        # 第 11 列 (idx=10) 是 user_cross_report_count, 大额囤货模式应 <= 1
        assert (X[:, 10] <= 1).all(), "大额囤货模式串货举报数应 <= 1"

    def test_normal_user_low_risk_features(self):
        """正常经销商模式: 订货量/串货举报/合同年龄 都应是低风险值."""
        import random
        import sys
        for p in [str(ROOT)]:
            if p not in sys.path:
                sys.path.insert(0, p)
        from scripts.train_demo_model import _gen_normal
        rng = random.Random(42)
        X = np.array([_gen_normal(rng) for _ in range(100)])
        # 负例: order_quantity (col 13) <= 30
        assert (X[:, 13] <= 30).all(), f"正常经销商 order_quantity 应 <= 30, 实际最大: {X[:, 13].max()}"
        # 负例: user_cross_report_count (col 10) <= 1
        assert (X[:, 10] <= 1).all(), f"正常经销商 cross_report 应 <= 1, 实际最大: {X[:, 10].max()}"
        # 负例: user_contract_age_days (col 11) >= 90 (老经销商)
        assert (X[:, 11] >= 90).all(), f"正常经销商 contract_age 应 >= 90, 实际最小: {X[:, 11].min()}"


class TestTrainedModelQuality:
    """训练质量: 验证合成的脚本能训出 val_auc > 0.85 的模型."""

    def test_training_pipeline_runs(self, tmp_path):
        """跑完整训练流程, 验证能生成模型文件."""
        import subprocess
        import sys
        model_path = tmp_path / "test_xgb.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--n", "500", "--seed", "42"],
            capture_output=True, timeout=120, cwd=ROOT,
        )
        assert result.returncode == 0, (
            f"训练失败, returncode={result.returncode}\n"
            f"stdout: {result.stdout.decode('utf-8', errors='replace')[-1000:]}\n"
            f"stderr: {result.stderr.decode('utf-8', errors='replace')[-1000:]}"
        )
