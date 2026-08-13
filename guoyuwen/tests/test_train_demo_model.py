"""银行 25 维纯合成冒烟模型测试；最终验收仍由真实快照训练承担。"""

import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import xgboost as xgb

from app.engine.ml_model import FEATURE_COLUMNS
from scripts.train_demo_model import _normal, _risk_pattern, gen_synthetic_dataset

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "train_demo_model.py"


class TestTrainDemoModelStructure:
    def test_disclaimer_prevents_smoke_model_being_final_evidence(self):
        source = SCRIPT.read_text(encoding="utf-8")
        assert "不作为 Goal 3 最终验收模型" in source
        assert "非最终验收" in source

    def test_uses_bank_feature_abi(self):
        source = SCRIPT.read_text(encoding="utf-8")
        assert "FEATURE_NAMES = FEATURE_COLUMNS" in source
        assert "N_FEATURES == 25" in source
        assert len(FEATURE_COLUMNS) == 25

    def test_has_six_explainable_bank_patterns(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for label in ["异地大额", "凌晨密集", "新设备大额", "多卡归集", "信贷申请突击", "共享设备 + 代理环境"]:
            assert label in source

    def test_uses_fixed_seed_and_stratified_split(self):
        source = SCRIPT.read_text(encoding="utf-8")
        assert "seed: int = 20260812" in source
        assert "stratify=y" in source
        assert "test_size=settings.XGB_TEST_SIZE" in source


class TestSyntheticDatasetGeneration:
    def test_shape_ratio_and_determinism(self):
        first_X, first_y = gen_synthetic_dataset(n=500, pos_ratio=0.4, seed=42)
        second_X, second_y = gen_synthetic_dataset(n=500, pos_ratio=0.4, seed=42)
        assert first_X.shape == (500, 25)
        assert first_y.shape == (500,)
        assert int(first_y.sum()) == 200
        assert np.array_equal(first_X, second_X)
        assert np.array_equal(first_y, second_y)

    def test_normal_environment_is_neutral(self):
        rows = np.asarray([_normal(random.Random(seed)) for seed in range(30)])
        index = {name: FEATURE_COLUMNS.index(name) for name in FEATURE_COLUMNS}
        assert (rows[:, index["addr_is_proxy"]] == 0).all()
        assert (rows[:, index["addr_is_tor"]] == 0).all()
        assert (rows[:, index["addr_is_unusual"]] == 0).all()
        assert (rows[:, index["order_txn_count_1h"]] == 1).all()

    def test_each_risk_pattern_changes_named_bank_signal(self):
        index = {name: FEATURE_COLUMNS.index(name) for name in FEATURE_COLUMNS}
        rows = [_risk_pattern(random.Random(100 + pattern), pattern) for pattern in range(6)]
        assert rows[0][index["order_event_amount"]] > 50_000
        assert rows[0][index["addr_is_unusual"]] == 1
        assert rows[1][index["order_txn_count_1h"]] >= 3
        assert rows[1][index["order_is_night"]] == 1
        assert rows[2][index["order_new_device_days"]] < 7
        assert rows[3][index["order_payee_card_count_1h"]] >= 3
        assert rows[4][index["order_loan_institution_count_30d"]] >= 3
        assert rows[5][index["order_device_user_count"]] >= 5
        assert rows[5][index["addr_is_proxy"]] == 1


class TestTrainedModelSmoke:
    def _train(self, tmp_path, name):
        model_path = tmp_path / name
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--n", "500", "--num-boost-round", "50", "--model-path", str(model_path), "--seed", "42"],
            capture_output=True,
            timeout=60,
            cwd=ROOT,
        )
        assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
        assert "smoke val_auc=" in result.stdout.decode("utf-8", errors="replace")
        assert model_path.stat().st_size > 1024
        return model_path

    def test_training_pipeline_writes_loadable_model(self, tmp_path):
        model_path = self._train(tmp_path, "bank_smoke.json")
        booster = xgb.Booster()
        booster.load_model(str(model_path))
        rng = random.Random(123)
        normal = xgb.DMatrix(_normal(rng).reshape(1, -1), feature_names=FEATURE_COLUMNS)
        risky = xgb.DMatrix(_risk_pattern(rng, 0).reshape(1, -1), feature_names=FEATURE_COLUMNS)
        normal_probability = float(booster.predict(normal)[0])
        risky_probability = float(booster.predict(risky)[0])
        assert normal_probability < 0.5
        assert risky_probability > 0.5
        assert risky_probability - normal_probability > 0.3
