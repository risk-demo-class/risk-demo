"""教育训练数据必须来自真实流水线且不含旧模型评分。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_training_query_only_uses_unscored_assessments():
    source = (ROOT / "scripts" / "train_xgb_model.py").read_text(encoding="utf-8")
    assert "AND ml_score IS NULL" in source
    assert "FEATURE_COLUMNS" in source
    assert "val_auc" in source
    assert "val_f1" in source


def test_generator_calls_public_process_event():
    source = (ROOT / "scripts" / "gen_business_data.py").read_text(encoding="utf-8")
    assert "from app.service.event import process_event" in source
    assert "await process_event(db, request)" in source


def test_unloaded_model_persists_null_training_marker():
    source = (ROOT / "app" / "engine" / "decision.py").read_text(encoding="utf-8")
    assert "ml_result.score if ml_result else None" in source


def test_training_wrapper_defaults_to_hundreds_of_events():
    source = (ROOT / "scripts" / "gen_train_dataset.py").read_text(encoding="utf-8")
    assert "default=500" in source
    assert "generate_business_data" in source
    assert "unload_model()" in source
