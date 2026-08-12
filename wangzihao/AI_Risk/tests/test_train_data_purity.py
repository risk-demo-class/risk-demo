"""Manufacturing snapshot dataset and backfill purity tests."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
GEN = (ROOT / "scripts" / "gen_train_dataset.py").read_text(encoding="utf-8")
EVENT_GEN = (ROOT / "scripts" / "gen_risk_data.py").read_text(encoding="utf-8")
BACKFILL = (ROOT / "scripts" / "backfill_ml_score.py").read_text(encoding="utf-8")
COMMON = (ROOT / "scripts" / "ml_pipeline_common.py").read_text(encoding="utf-8")


def test_dataset_export_is_read_only_and_uses_snapshots():
    assert "load_snapshot_dataset" in GEN
    assert "UPDATE risk_assessment" not in GEN
    assert "FROM risk_feature" in COMMON
    assert "feature_columns" in COMMON


def test_rule_only_generation_nulls_only_scoped_batch():
    assert "WHERE e.event_source_id LIKE 'ML%'" in EVENT_GEN
    assert "SET a.ml_score = NULL" in EVENT_GEN
    assert "UPDATE risk_assessment SET ml_score=NULL" not in EVENT_GEN


def test_backfill_uses_immutable_snapshots_and_only_null_rows():
    assert "FROM risk_feature" in BACKFILL
    assert "ml_score IS NULL" in BACKFILL
    assert "compute_all_features" not in BACKFILL
    assert "settings.DB_URL" not in BACKFILL
    assert "dry_run" in BACKFILL


def test_label_contract_is_documented_as_weak_supervision():
    assert "weak/synthetic" in GEN
    assert "label=1" in GEN and "label=0" in GEN
