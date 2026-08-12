from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    pingpong_db_host: str = "127.0.0.1"
    pingpong_db_port: int = 9999
    pingpong_db_user: str = "root"
    pingpong_db_password: str = ""
    pingpong_db_name: str = "pingpong"
    pingpong_model_path: str = "artifacts/xgb_inbound_model.json"
    pingpong_model_threshold: float = 0.5
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: float = 45.0

    @property
    def database_url(self) -> URL:
        return URL.create(
            "mysql+pymysql",
            username=self.pingpong_db_user,
            password=self.pingpong_db_password,
            host=self.pingpong_db_host,
            port=self.pingpong_db_port,
            database=self.pingpong_db_name,
            query={"charset": "utf8mb4"},
        )

    @property
    def model_path(self) -> Path:
        path = Path(self.pingpong_model_path)
        return path if path.is_absolute() else ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
