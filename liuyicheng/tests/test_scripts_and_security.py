import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_init_db_default_is_not_destructive():
    source = (ROOT / "scripts/init_db.py").read_text(encoding="utf-8")
    assert 'default=False' in source
    assert "DEFAULT_DB = settings.DB_NAME" in source
    assert "DEFAULT_PASSWORD = settings.DB_PASSWORD" in source


def test_generator_hashes_sensitive_identifiers():
    source = (ROOT / "scripts/gen_business_data.py").read_text(encoding="utf-8")
    assert "hashlib.sha256" in source
    assert "card_no_hash" not in source or "card" in source
    ast.parse(source)


def test_api_example_uses_only_four_contract_fields():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert '"event_type": "转账"' in readme
    assert '"event_data": {}' in readme
    assert '"order_id"' not in readme


def test_app_shutdown_disposes_async_database_engine():
    source = (ROOT / "scripts/main.py").read_text(encoding="utf-8")
    assert "load_model()" in source
    assert "await stop_scheduler()" in source
    assert "await async_engine.dispose()" in source
    assert source.index("await stop_scheduler()") < source.index("await async_engine.dispose()")
    ast.parse(source)


def test_example_env_contains_no_real_llm_key():
    source = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "LLM_API_KEY=\n" in source
    assert "XGB_TRAIN_DATA_LIMIT=1000" in source


def test_training_samples_force_rule_only_labels():
    generator = (ROOT / "scripts/gen_train_dataset.py").read_text(encoding="utf-8")
    model = (ROOT / "app/engine/ml_model.py").read_text(encoding="utf-8")
    trainer = (ROOT / "scripts/train_xgb_model.py").read_text(encoding="utf-8")
    assert "unload_model()" in generator
    assert "ml_score=NULL" in generator
    assert "_schedule_load()" not in model
    assert "AND ml_score IS NULL" in trainer
    for retired_script in ("gen_risky_users.py", "gen_risk_data_with_dates.py", "gen_risk_data.py"):
        assert retired_script not in trainer


def test_readme_generates_seven_day_history():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    one_command = (ROOT / "scripts/one_command.py").read_text(encoding="utf-8")
    history_script = (ROOT / "scripts/spread_demo_history.py").read_text(encoding="utf-8")
    backfill_script = (ROOT / "scripts/backfill_ml_score.py").read_text(encoding="utf-8")
    assert "--samples $samples --days $days" in readme
    assert '"--days", str(args.days)' in one_command
    assert '"--samples", str(args.samples)' in one_command
    assert 'run("backfill_ml_score.py")' in one_command
    assert "RiskAssessment" in history_script
    assert "RiskCase" in history_script
    assert "WHERE ml_score IS NULL" in backfill_script
    ast.parse(history_script)
    ast.parse(backfill_script)
