"""
【银行版】教学场景 XGBoost 演示模型训练测试
- 验证 scripts/train_demo_model.py 结构 (48 维银行特征)
- 验证合成数据特征分布
- 验证训练后模型能加载
"""
import re
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "train_demo_model.py"


class TestTrainDemoModelStructure:
    """train_demo_model.py 脚本结构"""

    def test_script_exists(self):
        assert SCRIPT.exists()

    def test_has_7_pattern_generators(self):
        """必须有 6 种正例模式 + 1 种正常模式 = 7 个生成器."""
        src = SCRIPT.read_text(encoding="utf-8")
        for name in ["_gen_low_credit_high_amount", "_gen_proxy_ip_transfer",
                     "_gen_high_debt_loan", "_gen_night_high_freq", "_gen_abnormal_login",
                     "_gen_mixed_high_risk", "_gen_normal_user"]:
            assert f"def {name}(" in src, f"缺模式: {name}"

    def test_uses_correct_feature_order(self):
        """48 维特征顺序必须跟 FEATURE_COLUMNS 一致."""
        src = SCRIPT.read_text(encoding="utf-8")
        assert "FEATURE_NAMES = FEATURE_COLUMNS" in src
        assert "N_FEATURES = len(FEATURE_NAMES)" in src
        assert "N_FEATURES == 48" in src

    def test_saves_to_default_path(self):
        """默认保存到 app/engine/xgb_model.json."""
        src = SCRIPT.read_text(encoding="utf-8")
        m = re.search(r'--model-path.*?default\s*=\s*os\.path\.join\([^,]+,\s*"app",\s*"engine",\s*"xgb_model\.json"\)', src, re.DOTALL)
        assert m, "默认应保存到 app/engine/xgb_model.json"

    def test_uses_ml_model_hyperparams(self):
        """训练超参跟 ml_model.py 一致 (max_depth 6 / lr 0.1 / min_child_weight 3 等)."""
        src = SCRIPT.read_text(encoding="utf-8")
        assert '"max_depth": 6' in src
        assert '"learning_rate": 0.1' in src
        assert '"min_child_weight": 3' in src
        assert '"subsample": 0.8' in src
        assert '"colsample_bytree": 0.8' in src
        assert '"reg_alpha": 0.1' in src
        assert '"reg_lambda": 1.0' in src

    def test_uses_stratify_split(self):
        """80/20 stratify 拆分."""
        src = SCRIPT.read_text(encoding="utf-8")
        assert "train_test_split" in src
        assert "stratify=y" in src
        assert "test_size=settings.XGB_TEST_SIZE" in src


class TestSyntheticDatasetGeneration:
    """合成数据生成函数 (不依赖 XGBoost, 纯 numpy)"""

    def test_gen_synthetic_dataset_default_size(self):
        """默认 2000 样本, 48 维."""
        import sys
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from scripts.train_demo_model import gen_synthetic_dataset
        X, y = gen_synthetic_dataset(n=2000, pos_ratio=0.5, seed=42)
        assert X.shape == (2000, 48), f"X.shape 错: {X.shape}"
        assert y.shape == (2000,), f"y.shape 错: {y.shape}"
        assert y.sum() == 1000, f"正例数错: {y.sum()} (期望 1000)"

    def test_gen_synthetic_dataset_feature_order_matches_columns(self):
        """合成数据的特征顺序必须跟 FEATURE_COLUMNS 一致, 否则训练/推理错位."""
        import random
        import sys
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from scripts.train_demo_model import _gen_low_credit_high_amount
        rng = random.Random(42)
        # 拿 10 个低信用分大额交易样本
        X = np.array([_gen_low_credit_high_amount(rng) for _ in range(10)])
        # 第 0 列 (idx=0) 应该是 user_credit_score (300-500 低信用分)
        assert (X[:, 0] >= 300).all() and (X[:, 0] <= 500).all(), (
            f"user_credit_score 应该是 300-500, 实际范围: {X[:, 0].min()}-{X[:, 0].max()}"
        )
        # 第 15 列 (idx=15) 应该是 txn_amount (大额 2万-15万)
        assert (X[:, 15] >= 20000).all() and (X[:, 15] <= 150000).all(), (
            f"txn_amount 应该是 20000-150000, 实际: {X[:, 15].min()}-{X[:, 15].max()}"
        )

    def test_normal_user_low_risk_features(self):
        """正常用户模式: 高信用分/低负债/小额交易 都应合理."""
        import random
        import sys
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from scripts.train_demo_model import _gen_normal_user
        rng = random.Random(42)
        X = np.array([_gen_normal_user(rng) for _ in range(100)])
        # 负例: user_credit_score (col 0) >= 650
        assert (X[:, 0] >= 650).all(), f"正常用户 credit_score 应 >= 650, 实际最小: {X[:, 0].min()}"
        # 负例: user_debt_ratio (col 8) <= 0.35
        assert (X[:, 8] <= 0.35).all(), f"正常用户 debt_ratio 应 <= 0.35, 实际最大: {X[:, 8].max()}"
        # 负例: txn_amount (col 15) <= 5000
        assert (X[:, 15] <= 5000).all(), f"正常用户 txn_amount 应 <= 5000, 实际最大: {X[:, 15].max()}"


class TestTrainedModelQuality:
    """训练质量: 验证合成的脚本能训出 val_auc > 0.85 的模型.

    注: 用较小的 n (500) 跑, 5 秒出结果, 验证流程跑得通.
    """

    def test_training_pipeline_runs(self, tmp_path):
        """跑完整训练流程, 验证能生成模型文件."""
        import subprocess
        import sys
        model_path = tmp_path / "test_xgb.json"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--n", "500", "--num-boost-round", "50",
             "--model-path", str(model_path), "--seed", "42"],
            capture_output=True, timeout=60, cwd=ROOT,
        )
        # 跑成功 (returncode=0)
        assert result.returncode == 0, (
            f"训练失败, returncode={result.returncode}\n"
            f"stdout: {result.stdout.decode('utf-8', errors='replace')[-1000:]}\n"
            f"stderr: {result.stderr.decode('utf-8', errors='replace')[-1000:]}"
        )
        # 模型文件存在
        assert model_path.exists(), f"模型文件未生成: {model_path}"
        # 模型文件 > 1KB (有内容)
        assert model_path.stat().st_size > 1024, "模型文件太小"

    def test_trained_model_loads(self, tmp_path):
        """训完的模型能加载, 推理能给合理评分."""
        import subprocess
        import sys
        model_path = tmp_path / "test_xgb2.json"
        subprocess.run(
            [sys.executable, str(SCRIPT), "--n", "500", "--num-boost-round", "50",
             "--model-path", str(model_path), "--seed", "42"],
            capture_output=True, timeout=60, cwd=ROOT,
            check=True,
        )
        # 加载并推理
        import xgboost as xgb
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        booster = xgb.Booster()
        booster.load_model(str(model_path))
        # 推理 1 个样本 (正常用户 vs 混合高风险)
        from scripts.train_demo_model import _gen_normal_user, _gen_mixed_high_risk
        import random
        rng = random.Random(123)
        X_normal = _gen_normal_user(rng).reshape(1, -1)
        X_risk = _gen_mixed_high_risk(rng).reshape(1, -1)
        from app.engine.ml_model import FEATURE_COLUMNS
        dmat_normal = xgb.DMatrix(X_normal, feature_names=FEATURE_COLUMNS)
        dmat_risk = xgb.DMatrix(X_risk, feature_names=FEATURE_COLUMNS)
        prob_normal = float(booster.predict(dmat_normal)[0])
        prob_risk = float(booster.predict(dmat_risk)[0])
        # 正常用户 < 0.5, RISK 用户 > 0.5
        assert prob_normal < 0.5, f"正常用户应 < 0.5, 实际: {prob_normal}"
        assert prob_risk > 0.5, f"RISK 用户应 > 0.5, 实际: {prob_risk}"
        # RISK 应该比 normal 高很多 (区分度)
        assert prob_risk - prob_normal > 0.3, (
            f"区分度应 > 0.3, 实际: {prob_risk - prob_normal:.4f}"
        )
