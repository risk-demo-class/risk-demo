"""物流模型训练数据不得由规则/旧模型决策反向标注。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRAIN_SRC = (ROOT / "scripts" / "train_xgb_model.py").read_text(encoding="utf-8")
GEN_SRC = (ROOT / "scripts" / "gen_risk_data.py").read_text(encoding="utf-8")


def test_training_label_comes_from_shipment():
    assert "JOIN shipment" in TRAIN_SRC
    assert "s.risk_label" in TRAIN_SRC
    assert "decision AS label" not in TRAIN_SRC
    assert "ml_score AS label" not in TRAIN_SRC


def test_generator_disables_old_model_during_snapshot_creation():
    assert "XGB_ENABLED = False" in GEN_SRC
    assert "process_event" in GEN_SRC


def test_training_requires_all_25_features():
    assert "set(FEATURE_COLUMNS).issubset(values)" in TRAIN_SRC


def test_training_enforces_acceptance_thresholds():
    assert "XGB_MIN_VAL_AUC" in TRAIN_SRC
    assert "XGB_MIN_VAL_F1" in TRAIN_SRC
