"""物流项目一键执行脚本结构测试。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "scripts" / "one_command.py").read_text(encoding="utf-8")


def test_pipeline_uses_logistics_database_initializer():
    assert "init_db.py" in SCRIPT
    assert '"--reset", "--yes"' in SCRIPT


def test_pipeline_generates_features_and_trains_model():
    assert "gen_train_dataset.py" in SCRIPT
    assert "train_xgb_model.py" in SCRIPT


def test_pipeline_can_start_service():
    assert '"--start"' in SCRIPT
    assert "run_app.py" in SCRIPT


def test_pipeline_can_skip_database_reset():
    assert '"--skip-init"' in SCRIPT
