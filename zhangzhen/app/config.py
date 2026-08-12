"""集中管理应用配置。

真实密码和 API Key 只允许出现在未提交的 ``.env`` 中；仓库仅保存
``.env.example`` 占位符。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """从环境变量或项目根目录的 .env 读取配置。"""

    APP_NAME: str = "银行业智能风控系统"
    APP_ENV: str = "development"
    DEBUG: bool = False
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "change_me"
    DB_NAME: str = "bank_risk"
    TEST_DB_NAME: str = "bank_risk_test"
    DATABASE_URL: str | None = None

    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_NAME: str = "qwen-plus"

    XGB_ENABLED: bool = True
    CASE_TIMEOUT_HOURS: int = 24
    ALERT_SCHEDULER_INTERVAL_MIN: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    def get_database_url_async(self, database_name: str | None = None) -> str:
        """返回 SQLAlchemy 异步数据库 URL。

        测试可以通过 ``DATABASE_URL=sqlite+aiosqlite:///:memory:`` 覆盖；
        Docker 中只需把 ``DB_HOST`` 设置为 Compose 服务名 ``mysql``。
        """

        if self.DATABASE_URL and database_name is None:
            return self.DATABASE_URL

        url = URL.create(
            drivername="mysql+aiomysql",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_HOST,
            port=self.DB_PORT,
            database=database_name or self.DB_NAME,
            query={"charset": "utf8mb4"},
        )
        return url.render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

