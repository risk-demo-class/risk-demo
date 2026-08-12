"""
电信风控系统 - 全局配置 (从 .env 加载, 缺省值兜底)

参照 ai_risk 风格: pydantic-settings 自动读 .env + 环境变量覆盖.
新数据库名 telecom (与 ai_risk 的 ecs 隔离, 独立存储电信业务数据).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置, 自动从 .env 文件和环境变量加载"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 数据库配置 (复用 ai_risk 的 docker MySQL, 新建 telecom 库) ----
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123321"
    DB_NAME: str = "telecom"          # 电信业务库 (区别于 ai_risk 的 ecs)
    TEST_DB_NAME: str = "telecom_test"

    def get_database_url_async(self, db_name: str | None = None) -> str:
        """异步 MySQL URL (aiomysql 驱动, 给 SQLAlchemy 用)"""
        name = db_name or self.DB_NAME
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{name}?charset=utf8mb4"
        )

    def get_database_url_sync(self, db_name: str | None = None) -> str:
        """同步 MySQL URL (pymysql 驱动, 给造数脚本用)"""
        name = db_name or self.DB_NAME
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{name}?charset=utf8mb4"
        )

    # ---- 风控决策阈值 (按 event_type 拆, 电信场景) ----
    # 电信事件严苛度: 国际来电 > 开户 > 通信 > 物联网
    RISK_PASS_THRESHOLD: int = 30
    RISK_MARK_THRESHOLD: int = 60
    RISK_REVIEW_THRESHOLD: int = 80
    RISK_MULTI_RULE_BONUS: int = 3
    RISK_VETO_MIN_SCORE: int = 90

    # 按事件类型拆阈值 (找不到 fallback 全局)
    RISK_EVENT_THRESHOLDS: dict[str, dict[str, int]] = {
        "开户":       {"pass": 30, "mark": 60, "review": 80},
        "通话":       {"pass": 35, "mark": 65, "review": 82},
        "国际来电":    {"pass": 40, "mark": 70, "review": 85},   # 最严
        "短信发送":    {"pass": 35, "mark": 65, "review": 82},
        "物联网激活":  {"pass": 30, "mark": 60, "review": 80},
        "通用":       {"pass": 30, "mark": 60, "review": 80},
    }

    # ---- 风险等级 ↔ 分数映射 (4 档) ----
    RISK_LEVEL_SCORE_MAP: dict[str, tuple[int, int]] = {
        "低":   (0, 29),
        "中":   (30, 59),
        "高":   (60, 84),
        "极高": (85, 100),
    }

    def get_event_thresholds(self, event_type: str) -> dict[str, int]:
        return self.RISK_EVENT_THRESHOLDS.get(
            event_type,
            {"pass": self.RISK_PASS_THRESHOLD,
             "mark": self.RISK_MARK_THRESHOLD,
             "review": self.RISK_REVIEW_THRESHOLD},
        )

    def get_risk_level_by_score(self, score: int) -> str:
        for level, (low, high) in self.RISK_LEVEL_SCORE_MAP.items():
            if low <= score <= high:
                return level
        return "极高" if score > 100 else "低"

    # ---- XGBoost 双轨融合配置 (参照 ai_risk) ----
    XGB_MODEL_PATH: str = "app/engine/xgb_model.json"
    XGB_ENABLED: bool = True
    # 评分融合权重 (规则 + XGBoost = 1.0)
    ML_WEIGHT_RULE: float = 0.5
    ML_WEIGHT_XGB: float = 0.5
    # ML 概率 → 4 档决策阈值
    ML_PASS_THRESHOLD: float = 0.30
    ML_MARK_THRESHOLD: float = 0.60
    ML_REVIEW_THRESHOLD: float = 0.80
    # 训练数据拉取上限
    XGB_TRAIN_DATA_LIMIT: int = 2500
    # 训练参数
    XGB_TEST_SIZE: float = 0.2
    XGB_EARLY_STOPPING_ROUNDS: int = 10
    XGB_MIN_SAMPLES: int = 1250
    XGB_MAX_SCALE_POS_WEIGHT: float = 10.0
    # 训练超参 (防假收敛)
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
    # 质量验收阈值
    XGB_MIN_BEST_ITER: int = 30
    XGB_MIN_VAL_AUC: float = 0.70
    XGB_MIN_VAL_F1: float = 0.50
    XGB_MIN_POS_RATIO: float = 0.15
    XGB_MAX_POS_RATIO: float = 0.60

    # ---- LLM 配置 (阿里云百炼, 复用 ai_risk 同款, Agent 用) ----
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_NAME: str = "qwen-plus"
    # Agent 对话超时 (秒), 防 LLM 网络挂死
    AI_AGENT_CHAT_TIMEOUT_SEC: float = 60.0
    # 特征是否全量返回给前端 (教学默认 True, 生产按角色脱敏)
    RISK_FEATURES_FULL_RETURN: bool = True
    # ---- Agent 复用 ai_risk API (HTTP 代理, 不重装 langchain 栈) ----
    # tele-risk 的 /api/agent/chat 转发到 ai_risk 的 /api/agent/chat, 复用其 LLM + 工具栈.
    # ai_risk 默认跑在 8000 端口, tele-risk 跑 8001, 互不冲突.
    AI_RISK_API_BASE: str = "http://localhost:8000"
    AI_AGENT_ENABLED: bool = True  # False=直接返"未启用", 不发 HTTP


settings = Settings()
