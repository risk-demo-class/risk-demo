from app.config import Settings


def test_mysql_async_url_uses_configured_host_and_database() -> None:
    settings = Settings(
        _env_file=None,
        DB_HOST="mysql",
        DB_PORT=3306,
        DB_USER="risk_user",
        DB_PASSWORD="change_me",
        DB_NAME="bank_risk",
        DATABASE_URL="",
    )

    url = settings.get_database_url_async()

    assert url.startswith("mysql+aiomysql://risk_user:change_me@mysql:3306/bank_risk")
    assert "charset=utf8mb4" in url


def test_explicit_database_url_is_supported_for_tests() -> None:
    settings = Settings(_env_file=None, DATABASE_URL="sqlite+aiosqlite:///:memory:")

    assert settings.get_database_url_async() == "sqlite+aiosqlite:///:memory:"
