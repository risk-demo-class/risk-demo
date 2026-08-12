from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "PP Risk"
    DATABASE_URL: str | None = None
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "pp_risk"
    TEST_DB_NAME: str = "pp_risk_test"
    RISK_PASS_THRESHOLD: int = 30
    RISK_REVIEW_THRESHOLD: int = 70
    RISK_REJECT_THRESHOLD: int = 90
    LLM_ENABLED: bool = True
    LLM_PROVIDER: str = "dashscope"
    LLM_MODEL_NAME: str = "qwen-plus"
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_API_KEY: str = ""
    LLM_TEMPERATURE: float = 0.1
    LLM_TIMEOUT_SECONDS: float = 60.0
    LLM_MAX_TOOL_ROUNDS: int = 8
    AGENT_SESSION_TTL_MINUTES: int = 60

    def get_database_url_async(self, db_name: str | None = None) -> str:
        if self.DATABASE_URL and db_name is None:
            return self.DATABASE_URL
        user = quote_plus(self.DB_USER)
        password = quote_plus(self.DB_PASSWORD)
        database = db_name or self.DB_NAME
        return (
            f"mysql+aiomysql://{user}:{password}@{self.DB_HOST}:"
            f"{self.DB_PORT}/{database}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
