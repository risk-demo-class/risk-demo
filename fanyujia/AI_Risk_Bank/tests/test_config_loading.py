"""Regression tests for configuration loading independent of the launch directory."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_settings_load_project_env_when_started_outside_project(monkeypatch, tmp_path):
    """An unrelated cwd .env must not redirect the training job to another DB."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "DB_HOST=wrong-host\nDB_PORT=3306\nDB_NAME=wrong_database\n",
        encoding="utf-8",
    )

    from app.config import Settings

    settings = Settings()

    assert settings.DB_NAME == "bank_risk"
    assert settings.DB_PORT == 9999
