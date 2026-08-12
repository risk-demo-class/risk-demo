"""
EduRisk 配置系统 — Pydantic Settings 模式
自动从 .env 加载,环境变量可覆盖,默认值兜底。
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ---------- 基础 ----------
    APP_NAME: str = "EduRisk 教育风控系统"
    APP_ENV: str = "dev"
    DEBUG: bool = True

    # ---------- 数据库 ----------
    DB_DRIVER: str = "mysql"        # mysql(生产) / sqlite(测试/本地快速跑)
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "edu_risk"
    DB_CHARSET: str = "utf8mb4"

    DB_POOL_SIZE: int = 10          # 连接池大小
    DB_MAX_OVERFLOW: int = 20       # 溢出连接
    DB_POOL_RECYCLE: int = 3600     # 1h 回收,避免 MySQL wait_timeout 断连

    def get_database_url_async(self) -> str:
        if self.DB_DRIVER == "sqlite":
            return "sqlite+aiosqlite:///./edu_risk.db"
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset={self.DB_CHARSET}"
        )

    def get_database_url_sync(self) -> str:
        if self.DB_DRIVER == "sqlite":
            return "sqlite:///./edu_risk.db"
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset={self.DB_CHARSET}"
        )

    # ---------- 决策阈值 ----------
    RISK_PASS_THRESHOLD: int = 30    # 0-29 通过
    RISK_MARK_THRESHOLD: int = 60    # 30-59 标记
    RISK_REVIEW_THRESHOLD: int = 80  # 60-79 人工审核
    RISK_VETO_MIN_SCORE: int = 90    # 极高规则一票否决最低分

    # ---------- 双轨融合 ----------
    ML_WEIGHT_RULE: float = 0.5      # α 规则权重
    ML_WEIGHT_XGB: float = 0.5       # β ML 权重
    ML_PASS_THRESHOLD: float = 0.30
    ML_MARK_THRESHOLD: float = 0.60
    ML_REVIEW_THRESHOLD: float = 0.80

    # ---------- 告警 ----------
    ALERT_PENDING_CASE_THRESHOLD: int = 50   # 待审核案件堆积阈值
    ALERT_RULE_HIT_RATE_MIN: float = 5.0     # 规则命中率下限 %
    ALERT_BLACKLIST_HIT_RATE_MAX: float = 30.0  # 黑名单命中率上限 %
    ALERT_CHECK_WINDOW_HOURS: int = 1

    # ---------- 案件 ----------
    CASE_TIMEOUT_HOURS: int = 24     # 案件超时自动关闭 (0=关闭此功能)
    ALERT_SCHEDULER_INTERVAL_MIN: int = 15  # 告警自动调度间隔 (0=关)

    # ---------- XGBoost ----------
    XGB_ENABLED: bool = True
    XGB_MODEL_PATH: str = "models/xgb_model.json"
    XGB_FEATURE_COUNT: int = 25

    # 训练 4 必做
    XGB_TEST_SIZE: float = 0.2
    XGB_EARLY_STOPPING_ROUNDS: int = 10
    XGB_MIN_SAMPLES: int = 1250      # 25 维 × 50
    XGB_MAX_SCALE_POS_WEIGHT: float = 10.0

    # 5 件套抗假收敛
    XGB_EARLY_STOP_METRIC: str = "auc"   # 早停指标换 auc(对不平衡敏感)
    XGB_WARMUP_ROUNDS: int = 50          # 前 50 轮强制不早停
    XGB_REG_ALPHA: float = 0.1           # L1 正则
    XGB_REG_LAMBDA: float = 1.0          # L2 正则
    XGB_MIN_CHILD_WEIGHT: int = 3
    XGB_SUBSAMPLE: float = 0.8
    XGB_COLSAMPLE_BYTREE: float = 0.8

    # 假收敛检测 3 信号
    XGB_MIN_BEST_ITER: int = 30
    XGB_MIN_VAL_AUC: float = 0.70
    XGB_MIN_VAL_F1: float = 0.50

    # ---------- AI Agent ----------
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL: str = "qwen-plus"
    LLM_TEMPERATURE: float = 0.1      # 业务场景要稳定
    AI_AGENT_CHAT_TIMEOUT_SEC: int = 60

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
