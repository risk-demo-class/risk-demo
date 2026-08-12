"""
医疗风控系统 - 全局配置
从 .env 文件加载, 支持环境变量覆盖.
P0 只保留骨架 + 数据层真正需要的配置; XGBoost / 调度等配置在对应阶段补充.
"""
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置, 自动从 .env 文件和环境变量加载"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # ---- 数据库配置 ----
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    # 凭据必须由 .env 或环境变量提供，源码不保存本机密码。
    DB_PASSWORD: str = ""
    DB_NAME: str = "ai_risk_medical"
    TEST_DB_NAME: str = "ai_risk_medical_test"

    def get_database_url_async(self, db_name: str | None = None) -> str:
        """构建异步 MySQL 连接 URL (aiomysql 驱动)"""
        name = db_name or self.DB_NAME
        return (
            f"mysql+aiomysql://{quote_plus(self.DB_USER)}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{name}?charset=utf8mb4"
        )

    def get_test_database_url_async(self) -> str:
        """测试库异步 URL"""
        return self.get_database_url_async(self.TEST_DB_NAME)

    # ---- 风控决策阈值 (复用 AI_Risk 约定, 四档决策) ----
    # 评分 < PASS → 通过, < MARK → 标记, < REVIEW → 人工审核, >= REVIEW → 拒绝
    RISK_PASS_THRESHOLD: int = 30
    RISK_MARK_THRESHOLD: int = 60
    RISK_REVIEW_THRESHOLD: int = 80
    RISK_MULTI_RULE_BONUS: int = 3     # 多规则命中时, 每条额外规则加的分
    RISK_VETO_MIN_SCORE: int = 90      # 一票否决时强制的最低分

    # ---- XGBoost 双轨融合 (P2) ----
    XGB_ENABLED: bool = True
    XGB_MODEL_PATH: str = "app/engine/xgb_model.json"
    XGB_METADATA_PATH: str = "app/engine/xgb_model.meta.json"
    XGB_TRAIN_DATA_LIMIT: int = 1200
    XGB_TEST_SIZE: float = 0.20
    XGB_CALIBRATION_SIZE: float = 0.20
    XGB_RANDOM_STATE: int = 20260811
    XGB_EARLY_STOPPING_ROUNDS: int = 20
    XGB_NUM_BOOST_ROUND: int = 300
    XGB_MIN_VAL_AUC: float = 0.70
    XGB_MIN_VAL_F1: float = 0.50
    ML_WEIGHT_RULE: float = 0.60
    ML_WEIGHT_XGB: float = 0.40
    ML_PASS_THRESHOLD: float = 0.25
    ML_MARK_THRESHOLD: float = 0.50
    ML_REVIEW_THRESHOLD: float = 0.75

    # ---- LLM 配置 (P3 AI 助手使用, P0 仅占位) ----
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_NAME: str = "qwen-plus"

    # ---- 特征脱敏 (P1 起使用) ----
    RISK_FEATURES_FULL_RETURN: bool = True

    # ---- AI Agent 超时 (P3) ----
    AI_AGENT_CHAT_TIMEOUT_SEC: float = 60.0

    # ---- 告警与本地服务 (P3) ----
    ALERT_SCHEDULER_ENABLED: bool = True
    ALERT_INTERVAL_SECONDS: int = 300
    ALERT_PENDING_CASE_THRESHOLD: int = 5
    ALERT_HIGH_RISK_RATE_THRESHOLD: float = 0.60
    ALERT_DOCTOR_AMOUNT_THRESHOLD: float = 100000.0
    ALERT_HOSPITAL_CLAIM_THRESHOLD: float = 200000.0
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    APP_SESSION_SECRET: str = "medical-risk-local-dev-change-me"
    SESSION_MAX_AGE_SECONDS: int = 28800
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "admin"


settings = Settings()


# ============================================================
# Demo: 看一眼项目所有关键配置 (无需 DB / 启动服务, 纯 print)
# 跑法: uv run python app/config.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Medical Risk AI 全局配置 (从 .env 加载, 缺省值兜底)")
    print("=" * 60)

    sections = [
        ("数据库", ["DB_HOST", "DB_PORT", "DB_USER", "DB_NAME", "TEST_DB_NAME"]),
        ("风控决策阈值", ["RISK_PASS_THRESHOLD", "RISK_MARK_THRESHOLD",
                       "RISK_REVIEW_THRESHOLD", "RISK_MULTI_RULE_BONUS", "RISK_VETO_MIN_SCORE"]),
        ("XGBoost (P2)", ["XGB_ENABLED", "XGB_MODEL_PATH", "ML_WEIGHT_RULE", "ML_WEIGHT_XGB"]),
        ("LLM (P3)", ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME"]),
        ("其他", ["RISK_FEATURES_FULL_RETURN", "AI_AGENT_CHAT_TIMEOUT_SEC"]),
    ]
    for sec_name, keys in sections:
        print(f"\n【{sec_name}】")
        for k in keys:
            v = getattr(settings, k, None)
            if v and "API_KEY" in k and isinstance(v, str) and len(v) > 8:
                v = v[:4] + "***" + v[-4:]   # 脱敏
            print(f"  {k:<30} = {v}")
