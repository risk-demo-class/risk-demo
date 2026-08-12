"""无需数据库的教育XGBoost演示数据测试。"""
from pathlib import Path
import subprocess
import sys

import numpy as np

from app.engine.ml_model import FEATURE_COLUMNS, load_model
from scripts.train_demo_model import gen_synthetic_dataset


ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_dataset_uses_current_25_features():
    X, y = gen_synthetic_dataset(n=200, pos_ratio=0.35, seed=42)
    assert X.shape == (200, len(FEATURE_COLUMNS)) == (200, 25)
    assert y.shape == (200,)
    assert X.dtype == np.float32
    assert set(np.unique(y)) == {0, 1}
    assert y.mean() == 0.35


def test_risk_samples_have_stronger_device_or_identity_signal():
    X, y = gen_synthetic_dataset(n=700, pos_ratio=0.5, seed=42)
    indexes = [FEATURE_COLUMNS.index(name) for name in (
        "device_distinct_users_30d", "student_id_blacklisted", "id_card_blacklisted",
    )]
    assert X[y == 1][:, indexes].mean() > X[y == 0][:, indexes].mean()


def test_training_script_produces_loadable_education_model(tmp_path):
    model = tmp_path / "education_xgb.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "train_demo_model.py"),
         "--n", "300", "--num-boost-round", "30", "--model-path", str(model)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert "val_auc=" in result.stdout
    assert "val_f1=" in result.stdout
    assert model.exists()
    assert load_model(str(model)) is True
