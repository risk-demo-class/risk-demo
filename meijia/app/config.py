"""只读取本项目 RISK_* 变量，避免复用旧电商项目的 DB_* 配置。

.env 支持: 启动时加载项目根 .env (RISK_* 变量), 真实环境变量优先。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("RISK_MYSQL_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("RISK_MYSQL_PORT", "13306"))
    db_user: str = os.getenv("RISK_MYSQL_USER", "risk_user")
    db_password: str = os.getenv("RISK_MYSQL_PASSWORD", "risk_pass")
    db_name: str = os.getenv("RISK_MYSQL_DATABASE", "risk_proj")

    @property
    def database_url(self) -> str:
        from urllib.parse import quote_plus

        password = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{self.db_user}:{password}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    # ---- 决策阈值 (规则轨道) ----
    # score_to_level 固定 90/70/40 (DB 集成校验依赖 80→高, 勿改档位)。
    # 多规则命中时每条额外规则加的分; 一票否决(极高)推分下限。
    RISK_MULTI_RULE_BONUS: int = 3
    RISK_VETO_MIN_SCORE: int = 90

    # ---- XGBoost 双轨融合 ----
    XGB_ENABLED: bool = _env_bool("RISK_XGB_ENABLED", True)
    XGB_MODEL_PATH: str = os.getenv("RISK_XGB_MODEL_PATH", "app/engine/xgb_model.json")
    ML_WEIGHT_RULE: float = float(os.getenv("RISK_ML_WEIGHT_RULE", "0.5"))
    ML_WEIGHT_XGB: float = float(os.getenv("RISK_ML_WEIGHT_XGB", "0.5"))
    # ML 轨道 P(拒绝) 概率 → 4 档决策阈值
    ML_PASS_THRESHOLD: float = float(os.getenv("RISK_ML_PASS", "0.30"))
    ML_MARK_THRESHOLD: float = float(os.getenv("RISK_ML_MARK", "0.60"))
    ML_REVIEW_THRESHOLD: float = float(os.getenv("RISK_ML_REVIEW", "0.80"))

    # ---- XGBoost 训练参数 ----
    XGB_TEST_SIZE: float = 0.2
    XGB_EARLY_STOPPING_ROUNDS: int = 10
    XGB_MIN_SAMPLES: int = 500        # gen_risk_data 默认 1000, 教学下限放宽
    XGB_MAX_SCALE_POS_WEIGHT: float = 10.0
    XGB_MAX_DEPTH: int = 6
    XGB_LEARNING_RATE: float = 0.1
    XGB_MIN_CHILD_WEIGHT: int = 3
    XGB_REG_ALPHA: float = 0.1        # L1
    XGB_REG_LAMBDA: float = 1.0       # L2
    XGB_GAMMA: float = 0.0
    XGB_SUBSAMPLE: float = 0.8
    XGB_COLSAMPLE_BYTREE: float = 0.8
    XGB_WARMUP_ROUNDS: int = 50       # 前 N 轮强制不早停, 防假收敛
    XGB_EARLY_STOP_METRIC: str = "auc"
    # 训练数据质量校验
    XGB_MIN_POS_RATIO: float = 0.10
    XGB_MAX_POS_RATIO: float = 0.60

    # ---- LLM / AI Agent ----
    LLM_API_KEY: str = os.getenv("RISK_LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("RISK_LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    LLM_MODEL_NAME: str = os.getenv("RISK_LLM_MODEL_NAME", "qwen-plus")
    AI_AGENT_CHAT_TIMEOUT_SEC: float = float(os.getenv("RISK_AGENT_TIMEOUT", "60"))

    # ---- 案件超时自动关闭 ----
    # "待审核"案件超过 N 小时没人审, 自动关案。0 = 关闭此功能。
    CASE_TIMEOUT_HOURS: int = int(os.getenv("RISK_CASE_TIMEOUT_HOURS", "24"))

    # ---- 告警自动调度 ----
    # 告警检查的间隔 (分钟)。0 = 关闭自动调度, 只能手动 POST /api/alerts/check。
    ALERT_SCHEDULER_INTERVAL_MIN: int = int(os.getenv("RISK_ALERT_SCHEDULER_INTERVAL_MIN", "15"))

    # ---- 风控告警阈值 ----
    ALERT_PENDING_CASE_THRESHOLD: int = int(os.getenv("RISK_ALERT_PENDING_CASE_THRESHOLD", "50"))
    ALERT_RULE_HIT_RATE_MIN: float = float(os.getenv("RISK_ALERT_RULE_HIT_RATE_MIN", "5.0"))
    ALERT_BLACKLIST_HIT_RATE_MAX: float = float(os.getenv("RISK_ALERT_BLACKLIST_HIT_RATE_MAX", "30.0"))
    ALERT_CHECK_WINDOW_HOURS: int = int(os.getenv("RISK_ALERT_CHECK_WINDOW_HOURS", "1"))


settings = Settings()
