"""教育版一键流程的静态契约。"""
from pathlib import Path


SOURCE = (Path(__file__).resolve().parents[1] / "scripts" / "one_command.py").read_text(encoding="utf-8")


def test_workflow_uses_real_scripts_in_order():
    scripts = ["init_db.py", "gen_train_dataset.py", "train_xgb_model.py", "backfill_ml_score.py"]
    positions = [SOURCE.index(name) for name in scripts]
    assert positions == sorted(positions)


def test_reset_is_explicit_and_training_can_be_skipped():
    assert '"--reset", "--yes"' in SOURCE
    assert '"--skip-init"' in SOURCE
    assert '"--skip-train"' in SOURCE


def test_subprocess_failure_is_not_silenced():
    assert "result.returncode" in SOURCE
    assert "raise SystemExit" in SOURCE


def test_event_volume_is_configurable():
    assert '"--events"' in SOURCE
    assert "default=500" in SOURCE
