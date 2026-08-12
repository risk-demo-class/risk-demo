from pathlib import Path

from scripts.init_db import _validated_db_name


ROOT = Path(__file__).resolve().parents[1]


def test_source_does_not_hardcode_local_password():
    source = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
    assert 'DB_PASSWORD: str = ""' in source
    assert "123456" not in source


def test_env_is_ignored_but_example_is_available():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in ignore
    assert (ROOT / ".env.example").exists()


def test_database_name_validation_blocks_injection():
    assert _validated_db_name("ai_risk_medical") == "ai_risk_medical"
    for invalid in ("ecs; DROP DATABASE ecs", "../ecs", "name-with-dash"):
        try:
            _validated_db_name(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"应拒绝数据库名: {invalid}")
