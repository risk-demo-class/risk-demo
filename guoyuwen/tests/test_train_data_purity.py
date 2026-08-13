"""银行训练数据标签纯度、来源完整性与回填隔离测试。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRAIN_PY = ROOT / "scripts" / "train_xgb_model.py"
GEN_PY = ROOT / "scripts" / "gen_train_dataset.py"
BACKFILL_PY = ROOT / "scripts" / "backfill_ml_score.py"
ONE_COMMAND_PY = ROOT / "scripts" / "one_command.py"


class TestTrainDataPurity:
    def test_loader_filters_unscored_assessments(self):
        source = TRAIN_PY.read_text(encoding="utf-8")
        assert "AND ml_score IS NULL" in source
        select_block = source.split("SELECT assessment_id", 1)[1].split("FROM risk_assessment", 1)[0]
        assert "ml_score" not in select_block

    def test_labels_only_derive_from_existing_decision(self):
        source = TRAIN_PY.read_text(encoding="utf-8")
        assert 'decision in ("人工审核", "拒绝")' in source
        for forbidden in ["rule_results", "final_score", "risk_level"]:
            select_block = source.split("SELECT assessment_id", 1)[1].split("FROM risk_assessment", 1)[0]
            assert forbidden not in select_block

    def test_feature_order_is_explicit(self):
        source = TRAIN_PY.read_text(encoding="utf-8")
        assert "required = set(FEATURE_COLUMNS)" in source
        assert "if set(values) != required" in source
        assert "[values[name] for name in FEATURE_COLUMNS]" in source


class TestGenTrainDatasetScript:
    def test_uses_four_source_models_without_prefix_guessing(self):
        source = GEN_PY.read_text(encoding="utf-8")
        for model in ["LoginLog", "Transaction", "LoanApplication", "BankCard"]:
            assert model in source
        assert "不使用 ID 前缀猜类型" in source

    def test_uses_real_process_event_and_unique_sources(self):
        source = GEN_PY.read_text(encoding="utf-8")
        assert "from app.service.event import process_event" in source
        assert "await process_event(" in source
        assert "sources[:count]" in source

    def test_forces_model_outputs_null_after_pipeline(self):
        source = GEN_PY.read_text(encoding="utf-8")
        assert ".values(ml_score=None, ml_decision=None)" in source
        assert "尚未经过模型回填" in source

    def test_default_dataset_is_2000_with_fixed_seed(self):
        source = GEN_PY.read_text(encoding="utf-8")
        assert "count: int = 2000" in source
        assert "seed: int = 20260812" in source


class TestBackfillMlScoreScript:
    def test_only_updates_null_model_outputs(self):
        source = BACKFILL_PY.read_text(encoding="utf-8")
        assert "RiskAssessment.ml_score.is_(None)" in source
        assert ".values(ml_score=result.score, ml_decision=result.decision)" in source

    def test_requires_complete_25_feature_snapshot(self):
        source = BACKFILL_PY.read_text(encoding="utf-8")
        assert "if set(features) != set(FEATURE_COLUMNS)" in source
        assert "skipped += 1" in source

    def test_loads_and_uses_trained_model(self):
        source = BACKFILL_PY.read_text(encoding="utf-8")
        assert "is_model_loaded()" in source
        assert "load_model()" in source
        assert "predict(features)" in source


class TestTrainingWorkflowIntegration:
    def test_one_command_preserves_generate_train_backfill_order(self):
        source = ONE_COMMAND_PY.read_text(encoding="utf-8")
        generate = source.index("step_3_train_dataset()")
        train = source.index("step_4_train_xgboost()")
        backfill = source.index("step_5_backfill_ml_score()")
        assert generate < train < backfill

    def test_one_command_documents_real_pipeline_dataset_size(self):
        source = ONE_COMMAND_PY.read_text(encoding="utf-8")
        assert "2000 条真实 pipeline 训练数据" in source
        assert "25 维完整快照" in source
