from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_stage_three_structure_is_complete() -> None:
    required = [
        "app/api.py",
        "app/config.py",
        "app/database.py",
        "app/engine/decision.py",
        "app/engine/graph.py",
        "app/engine/model_manager.py",
        "app/engine/rule_catalog.py",
        "app/service/features.py",
        "app/service/appeals.py",
        "app/routers/appeals.py",
        "app/bootstrap.py",
        "app/agent/tools.py",
        "scripts/init_db.py",
        "scripts/one_command.py",
        "templates/dashboard.html",
        "templates/appeal.html",
        "docker/docker-compose.yml",
    ]
    assert not [path for path in required if not (ROOT / path).exists()]
