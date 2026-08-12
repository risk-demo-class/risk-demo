"""Application settings loaded from environment variables and ``.env``."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Central configuration for the modular monolith skeleton."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "BankRisk-AI"
    APP_VERSION: str = "1.0.0"
    APP_ENV: Literal["development", "test", "production"] = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = Field(default=8000, ge=1, le=65535)
    APP_RELOAD: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_RETENTION_DAYS: int = Field(default=30, ge=1, le=3650)
    LOG_PSEUDONYM_KEY: str = Field(default="development-only-change-me", min_length=16)
    ALERT_WEBHOOK_URL: str = ""
    ALERT_WEBHOOK_TIMEOUT_SECONDS: float = Field(default=2.0, gt=0, le=10)
    APPEAL_SIGNING_KEY: str = Field(default="development-appeal-signing-key", min_length=16)
    APPEAL_WINDOW_DAYS: int = Field(default=30, ge=1, le=180)
    APPEAL_REVIEW_SLA_DAYS: int = Field(default=7, ge=1, le=60)
    APPEAL_REVIEW_TOKEN: str = ""

    DB_DRIVER: Literal["sqlite", "mysql"] = "sqlite"
    SQLITE_PATH: str = "data/bankrisk.db"
    AUTO_INIT_DB: bool = True
    SEED_DEMO_DATA: bool = True

    DB_HOST: str = "localhost"
    DB_PORT: int = Field(default=3306, ge=1, le=65535)
    DB_USER: str = "bankrisk"
    DB_PASSWORD: str = ""
    DB_NAME: str = "bankrisk"
    TEST_DB_NAME: str = "bankrisk_test"

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = "neo4j"

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_NAME: str = "qwen-plus"

    ENABLE_RULE_ENGINE: bool = True
    RULE_ADDITIONAL_WEIGHT: float = Field(default=0.2, ge=0, le=1)
    ENABLE_MODEL_ENGINE: bool = True
    MODEL_DIR: str = "artifacts/models"
    MODEL_AUTO_TRAIN: bool = True

    ENABLE_GRAPH_ENGINE: bool = True
    GRAPH_BACKEND: Literal["local", "neo4j"] = "local"
    FUSION_ADDITIONAL_WEIGHT: float = Field(default=0.15, ge=0, le=1)

    ENABLE_AGENT: bool = True
    AGENT_MODE: Literal["local", "llm"] = "local"
    AGENT_APPROVAL_TOKEN: str = ""

    def database_url(self, db_name: str | None = None) -> URL:
        """Build an async SQLAlchemy URL without string-concatenating credentials."""
        if self.DB_DRIVER == "sqlite":
            return URL.create(
                drivername="sqlite+aiosqlite",
                database=self.SQLITE_PATH,
            )
        return URL.create(
            drivername="mysql+aiomysql",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=db_name or self.DB_NAME,
            query={"charset": "utf8mb4"},
        )

    def enabled_components(self) -> dict[str, bool]:
        return {
            "rule": self.ENABLE_RULE_ENGINE,
            "model": self.ENABLE_MODEL_ENGINE,
            "graph": self.ENABLE_GRAPH_ENGINE,
            "agent": self.ENABLE_AGENT,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
