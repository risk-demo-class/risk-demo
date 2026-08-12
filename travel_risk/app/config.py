"""
旅游风控系统 - 全局配置
从 .env 文件加载, 支持环境变量覆盖 (与电商模板同构, 业务维度改为旅游场景)
"""
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
    DB_PASSWORD: str = "123321"
    DB_NAME: str = "travel_risk"
    TEST_DB_NAME: str = "travel_risk_test"

    def get_database_url_async(self, db_name: str | None = None) -> str:
        """构建异步 MySQL 连接 URL (用于 aiomysql 驱动)"""
        name = db_name or self.DB_NAME
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{name}?charset=utf8mb4"
        )

    def get_database_url_sync(self, db_name: str | None = None) -> str:
        """构建同步 MySQL 连接 URL (用于 pymysql 驱动, 初始化脚本用)"""
        name = db_name or self.DB_NAME
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{name}?charset=utf8mb4"
        )

    def get_test_database_url_async(self) -> str:
        """测试库异步 URL"""
        return self.get_database_url_async(self.TEST_DB_NAME)

    # ---- 风控决策阈值 (按 event_type 拆, 旅游不同场景严苛度不同) ----
    # 注册/下单标准, 支付更严 (钱的事), 退改/理赔/投诉最严 (薅羊毛/骗保高发)
    RISK_PASS_THRESHOLD: int = 30
    RISK_MARK_THRESHOLD: int = 60
    RISK_REVIEW_THRESHOLD: int = 80
    RISK_MULTI_RULE_BONUS: int = 3     # 多规则命中时, 每条额外规则加的分
    RISK_VETO_MIN_SCORE: int = 90      # 一票否决时强制的最低分

    RISK_EVENT_THRESHOLDS: dict[str, dict[str, int]] = {
        "注册":      {"pass": 30, "mark": 60, "review": 80},
        "下单":      {"pass": 30, "mark": 60, "review": 80},   # 标准
        "支付":      {"pass": 25, "mark": 55, "review": 75},   # 支付更严 (钱的事)
        "退改申请":   {"pass": 40, "mark": 70, "review": 85},   # 退改更严 (薅羊毛)
        "理赔申请":   {"pass": 45, "mark": 75, "review": 90},   # 理赔最严 (骗保)
        "投诉":      {"pass": 35, "mark": 65, "review": 80},   # 投诉偏严
        "通用":      {"pass": 30, "mark": 60, "review": 80},   # = 全局默认
    }

    # ---- 风险等级 ↔ 分数 映射 (4 档, 区间左闭右闭) ----
    RISK_LEVEL_SCORE_MAP: dict[str, tuple[int, int]] = {
        "低":   (0, 29),
        "中":   (30, 59),
        "高":   (60, 84),
        "极高": (85, 100),
    }

    def get_risk_level_by_score(self, score: int) -> str:
        """根据分数反查风险等级 (前端下拉 + 后端校验)."""
        for level, (low, high) in self.RISK_LEVEL_SCORE_MAP.items():
            if low <= score <= high:
                return level
        return "极高" if score > 100 else "低"

    def get_event_thresholds(self, event_type: str) -> dict[str, int]:
        """按 event_type 查阈值, 找不到 fallback 到全局."""
        return self.RISK_EVENT_THRESHOLDS.get(
            event_type,
            {"pass": self.RISK_PASS_THRESHOLD, "mark": self.RISK_MARK_THRESHOLD, "review": self.RISK_REVIEW_THRESHOLD},
        )

    # ---- LLM 配置 (可选, 不配 AI Agent 自动降级为规则问答) ----
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_NAME: str = "qwen-plus"

    # ---- features 脱敏 ----
    RISK_FEATURES_FULL_RETURN: bool = True

    # ---- AI Agent chat 超时 ----
    AI_AGENT_CHAT_TIMEOUT_SEC: float = 60.0

    # ---- 案件超时自动关闭 (小时, 0=关闭) ----
    CASE_TIMEOUT_HOURS: int = 24

    # ---- 告警自动调度 (分钟, 0=关闭) ----
    ALERT_SCHEDULER_INTERVAL_MIN: int = 15

    # ---- 风控告警阈值 ----
    ALERT_PENDING_CASE_THRESHOLD: int = 50          # 场景 1: 待审核案件积压数
    ALERT_RULE_HIT_RATE_MIN: float = 5.0            # 场景 2: 最近窗口规则命中率下限 (%)
    ALERT_BLACKLIST_HIT_RATE_MAX: float = 30.0      # 场景 3: 最近窗口撞黑比例上限 (%)
    ALERT_CHECK_WINDOW_HOURS: int = 1               # 告警检查的时间窗口 (小时)

    # ---- XGBoost 双轨融合配置 ----
    XGB_MODEL_PATH: str = "app/engine/xgb_model.json"
    XGB_ENABLED: bool = True
    ML_WEIGHT_RULE: float = 0.5
    ML_WEIGHT_XGB: float = 0.5
    ML_PASS_THRESHOLD: float = 0.30
    ML_MARK_THRESHOLD: float = 0.60
    ML_REVIEW_THRESHOLD: float = 0.80
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


settings = Settings()


if __name__ == "__main__":
    print("=" * 60)
    print("Travel Risk 全局配置 (从 .env 加载, 缺省值兜底)")
    print("=" * 60)
    print(f"  数据库: {settings.DB_USER}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")
    print(f"  事件阈值: {settings.RISK_EVENT_THRESHOLDS}")
    print(f"  等级区间: {settings.RISK_LEVEL_SCORE_MAP}")
    print(f"  XGBoost: enabled={settings.XGB_ENABLED}, 融合权重 rule={settings.ML_WEIGHT_RULE}/xgb={settings.ML_WEIGHT_XGB}")
