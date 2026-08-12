"""
银行风控系统 - 全局配置
====================
从 .env 文件加载, 支持环境变量覆盖.
覆盖四大场景: 登录 / 转账 / 贷款 / 信用卡

配置项说明:
  - 数据库: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
  - 风控阈值: 评分 < PASS → 通过, < MARK → 标记, < REVIEW → 人工审核, >= REVIEW → 拒绝
  - 一票否决: 极高风险规则命中后强制拒绝, 最低分 RISK_VETO_MIN_SCORE
  - XGBoost: 双轨融合权重、训练参数、质量验收阈值
  - LLM: AI Agent 对话配置
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
    DB_PASSWORD: str = "1234"
    DB_NAME: str = "bank_risk"
    TEST_DB_NAME: str = "bank_risk_test"

    def get_database_url_async(self, db_name: str | None = None) -> str:
        """构建异步 MySQL 连接 URL"""
        name = db_name or self.DB_NAME
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{name}?charset=utf8mb4"
        )

    def get_test_database_url_async(self) -> str:
        return self.get_database_url_async(self.TEST_DB_NAME)

    # ---- 风控决策阈值 ----
    # 评分 < PASS → 通过 (放行)
    # < MARK  → 标记 (放行但记录)
    # < REVIEW → 人工审核 (挂起进入人工队列)
    # >= REVIEW → 拒绝 (不执行)
    RISK_PASS_THRESHOLD: int = 30
    RISK_MARK_THRESHOLD: int = 60
    RISK_REVIEW_THRESHOLD: int = 80
    RISK_MULTI_RULE_BONUS: int = 3       # 多规则命中时, 每条额外规则加的分
    RISK_VETO_MIN_SCORE: int = 90        # 一票否决时强制的最低分

    # ---- XGBoost 双轨融合配置 ----
    XGB_MODEL_PATH: str = "app/engine/xgb_bank_risk_model.json"
    XGB_ENABLED: bool = True             # False = 纯规则, 兜底
    # 评分融合权重 (规则占比 + XGBoost 占比 = 1.0)
    ML_WEIGHT_RULE: float = 0.5
    ML_WEIGHT_XGB: float = 0.5
    # ML 单维度的决策阈值 (P(拒绝) 概率 → 4 档)
    ML_PASS_THRESHOLD: float = 0.30
    ML_MARK_THRESHOLD: float = 0.60
    ML_REVIEW_THRESHOLD: float = 0.80
    # 训练数据加载
    XGB_TRAIN_DATA_LIMIT: int = 2500
    # 训练参数
    XGB_TEST_SIZE: float = 0.2
    XGB_EARLY_STOPPING_ROUNDS: int = 10
    XGB_MIN_SAMPLES: int = 300            # 银行场景样本量较小, 降低门槛
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
    # 质量验收
    XGB_MIN_BEST_ITER: int = 20           # 银行训练样本少, 适当降低
    XGB_MIN_VAL_AUC: float = 0.70
    XGB_MIN_VAL_F1: float = 0.50
    XGB_MIN_POS_RATIO: float = 0.10
    XGB_MAX_POS_RATIO: float = 0.60

    # ---- LLM 配置 (阿里云百炼) ----
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_NAME: str = "qwen-plus"

    # ---- 案件超时自动关闭 ----
    CASE_TIMEOUT_HOURS: int = 24

    # ---- 告警阈值 ----
    ALERT_PENDING_CASE_THRESHOLD: int = 50
    ALERT_RULE_HIT_RATE_MIN: float = 5.0
    ALERT_BLACKLIST_HIT_RATE_MAX: float = 30.0
    ALERT_CHECK_WINDOW_HOURS: int = 1

    # ---- 特征脱敏 ----
    RISK_FEATURES_FULL_RETURN: bool = True

    # ---- AI Agent 超时 ----
    AI_AGENT_CHAT_TIMEOUT_SEC: float = 120.0


settings = Settings()


# ============================================================
# Demo: 查看所有关键配置
# 跑法: python app/config.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("银行风控系统 - 全局配置")
    print("=" * 60)

    sections = [
        ("数据库", ["DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"]),
        ("风控决策阈值", ["RISK_PASS_THRESHOLD", "RISK_MARK_THRESHOLD",
                       "RISK_REVIEW_THRESHOLD", "RISK_MULTI_RULE_BONUS", "RISK_VETO_MIN_SCORE"]),
        ("XGBoost 双轨融合", ["XGB_ENABLED", "XGB_MODEL_PATH",
                          "ML_WEIGHT_RULE", "ML_WEIGHT_XGB",
                          "ML_PASS_THRESHOLD", "ML_MARK_THRESHOLD", "ML_REVIEW_THRESHOLD"]),
        ("LLM", ["LLM_MODEL_NAME", "LLM_BASE_URL"]),
    ]
    for sec_name, keys in sections:
        print(f"\n【{sec_name}】")
        for k in keys:
            v = getattr(settings, k, None)
            if v and "API_KEY" in k and isinstance(v, str) and len(v) > 8:
                v = v[:4] + "***" + v[-4:]
            print(f"  {k:<30} = {v}")
