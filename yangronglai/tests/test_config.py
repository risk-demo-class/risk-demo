from app.config import Settings


def test_completed_components_are_enabled_by_default(monkeypatch) -> None:
    for key in ("ENABLE_RULE_ENGINE", "ENABLE_MODEL_ENGINE", "ENABLE_GRAPH_ENGINE", "ENABLE_AGENT"):
        monkeypatch.delenv(key, raising=False)
    cfg = Settings(_env_file=None)
    assert cfg.enabled_components() == {
        "rule": True,
        "model": True,
        "graph": True,
        "agent": True,
    }


def test_mysql_database_url_handles_password_as_url_component() -> None:
    cfg = Settings(_env_file=None, DB_DRIVER="mysql", DB_PASSWORD="p@ss:word")
    url = cfg.database_url()
    assert url.password == "p@ss:word"
    assert url.drivername == "mysql+aiomysql"


def test_local_development_defaults_to_async_sqlite() -> None:
    cfg = Settings(_env_file=None)
    assert cfg.database_url().drivername == "sqlite+aiosqlite"


def test_observability_defaults_have_retention_and_pseudonym_key() -> None:
    cfg = Settings(_env_file=None)
    assert cfg.LOG_RETENTION_DAYS == 30
    assert len(cfg.LOG_PSEUDONYM_KEY) >= 16
    assert cfg.ALERT_WEBHOOK_URL == ""


def test_client_appeal_defaults_are_bounded_and_internal_review_is_locked() -> None:
    cfg = Settings(_env_file=None)
    assert cfg.APPEAL_WINDOW_DAYS == 30
    assert cfg.APPEAL_REVIEW_SLA_DAYS == 7
    assert len(cfg.APPEAL_SIGNING_KEY) >= 16
    assert cfg.APPEAL_REVIEW_TOKEN == ""
