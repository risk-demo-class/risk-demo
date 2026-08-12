"""
旅游出行风控系统 - 全局配置模块.

设计原则:
1. 所有密钥只从环境变量 / .env 读取, 代码内不出现真实密钥.
2. 所有路径使用相对路径, 不硬编码绝对路径.
3. 配置加载失败时记录日志并抛出, 避免带错误配置启动.
"""

import logging
import math
from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """全局配置, 自动从 .env 和环境变量加载."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- 应用 ----------
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"

    # ---------- 数据库 ----------
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = ""
    DB_PASSWORD: str = Field(default="", repr=False, description="数据库密码, 只从环境变量读取")
    DB_NAME: str = "travel_risk"
    TEST_DB_NAME: str = "travel_risk_test"
    DB_CHARSET: str = "utf8mb4"

    # ---------- 风控决策阈值 ----------
    RISK_PASS_THRESHOLD: int = 30
    RISK_MARK_THRESHOLD: int = 60
    RISK_REVIEW_THRESHOLD: int = 80
    RISK_MULTI_RULE_BONUS: int = 3
    RISK_VETO_MIN_SCORE: int = 90

    # ---------- 特征配置 ----------
    FEATURE_CONFIG_PATH: str = "config/features.yaml"
    FEATURE_REGISTRY_CACHE_ENABLED: bool = True
    RISK_FEATURES_FULL_RETURN: bool = True

    # ---------- 数据集与模型产物 ----------
    TRAIN_CSV_PATH: str = "data/travel_risk_train.csv"
    EVALUATE_REPORT_PATH: str = "docs/model_evaluation.md"
    XGB_MODEL_PATH: str = "app/engine/xgb_model.json"

    # ---------- 规则 + XGBoost 双轨融合 ----------
    ML_WEIGHT_RULE: float = 0.5
    ML_WEIGHT_XGB: float = 0.5
    ML_PASS_THRESHOLD: float = 0.30
    ML_MARK_THRESHOLD: float = 0.60
    ML_REVIEW_THRESHOLD: float = 0.80

    # ---------- XGBoost ----------
    XGB_ENABLED: bool = True
    XGB_TRAIN_DATA_LIMIT: int = 2500
    XGB_TEST_SIZE: float = 0.2
    XGB_EARLY_STOPPING_ROUNDS: int = 10
    XGB_MIN_SAMPLES: int = 1250
    XGB_MAX_SCALE_POS_WEIGHT: float = 10.0
    XGB_MAX_DEPTH: int = 6
    XGB_LEARNING_RATE: float = 0.1
    XGB_MIN_CHILD_WEIGHT: int = 3
    XGB_REG_ALPHA: float = 0.1
    XGB_REG_LAMBDA: float = 1.0
    XGB_GAMMA: float = 0.0
    XGB_SUBSAMPLE: float = 0.8
    XGB_COLSAMPLE_BYTREE: float = 0.8
    XGB_WARMUP_ROUNDS: int = 50
    XGB_EARLY_STOP_METRIC: str = "auc"
    XGB_MIN_BEST_ITER: int = 30
    XGB_MIN_VAL_AUC: float = 0.70
    XGB_MIN_VAL_F1: float = 0.50
    XGB_MIN_POS_RATIO: float = 0.15
    XGB_MAX_POS_RATIO: float = 0.60

    # ---------- DeepSeek 本地 LLM ----------
    LLM_ENABLED: bool = False
    LLM_BASE_URL: str = "http://localhost:11434/v1"
    LLM_MODEL_NAME: str = "deepseek-r1:7b"
    LLM_API_KEY: str = Field(default="", repr=False, description="本地模型通常无需密钥, 兼容 OpenAI 接口")
    LLM_TIMEOUT_SEC: float = 10.0
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 512

    # ---------- AI Agent ----------
    AI_AGENT_CHAT_TIMEOUT_SEC: float = 60.0

    # ---------- 案件与告警 ----------
    CASE_TIMEOUT_HOURS: int = 24
    ALERT_SCHEDULER_INTERVAL_MIN: int = 15
    ALERT_PENDING_CASE_THRESHOLD: int = 50
    ALERT_RULE_HIT_RATE_MIN: float = 5.0
    ALERT_BLACKLIST_HIT_RATE_MAX: float = 30.0
    ALERT_CHECK_WINDOW_HOURS: int = 1

    @model_validator(mode="after")
    def _validate_thresholds(self) -> "Settings":
        """校验核心阈值, 配置错误时拒绝启动."""
        if not (
            0 <= self.RISK_PASS_THRESHOLD
            < self.RISK_MARK_THRESHOLD
            < self.RISK_REVIEW_THRESHOLD
            <= 100
        ):
            raise ValueError("决策阈值必须满足 0 <= PASS < MARK < REVIEW <= 100")

        weight_sum = self.ML_WEIGHT_RULE + self.ML_WEIGHT_XGB
        if not math.isclose(weight_sum, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"规则与模型权重之和必须为 1, 当前: {weight_sum}"
            )

        if not (0 < self.LLM_TIMEOUT_SEC <= 120):
            raise ValueError("LLM_TIMEOUT_SEC 必须在 (0, 120] 区间")

        return self

    def _encode(self, value: str) -> str:
        """对连接串中的账号 / 密码做 URL 编码."""
        return quote_plus(value or "")

    def get_database_url_async(self, db_name: str | None = None) -> str:
        """构建异步 MySQL 连接串, 用于 aiomysql."""
        name = db_name or self.DB_NAME
        user = self._encode(self.DB_USER)
        password = self._encode(self.DB_PASSWORD)
        return (
            f"mysql+aiomysql://{user}:{password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{name}"
            f"?charset={self.DB_CHARSET}"
        )

    def get_database_url_sync(self, db_name: str | None = None) -> str:
        """构建同步 MySQL 连接串, 用于 pymysql / 造数脚本."""
        name = db_name or self.DB_NAME
        user = self._encode(self.DB_USER)
        password = self._encode(self.DB_PASSWORD)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{name}"
            f"?charset={self.DB_CHARSET}"
        )

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """带日志和异常捕获的配置加载入口."""
    try:
        logger.info("开始加载配置: env_file=.env, 支持环境变量覆盖")
        return Settings()
    except Exception as exc:
        logger.exception("配置加载失败: %s", exc)
        raise


settings = get_settings()


if __name__ == "__main__":
    print("=" * 60)
    print("旅游出行风控系统配置概览")
    print("=" * 60)
    print(f"APP_HOST={settings.APP_HOST}")
    print(f"APP_PORT={settings.APP_PORT}")
    print(f"DB_HOST={settings.DB_HOST}")
    print(f"DB_PORT={settings.DB_PORT}")
    print(f"DB_NAME={settings.DB_NAME}")
    print(f"FEATURE_CONFIG_PATH={settings.FEATURE_CONFIG_PATH}")
    print(f"XGB_MODEL_PATH={settings.XGB_MODEL_PATH}")
    print(f"XGB_ENABLED={settings.XGB_ENABLED}")
    print(f"LLM_ENABLED={settings.LLM_ENABLED}")
    print(f"LLM_BASE_URL={settings.LLM_BASE_URL}")
    print(f"LLM_MODEL_NAME={settings.LLM_MODEL_NAME}")
    print("密钥字段已脱敏, 不打印")
