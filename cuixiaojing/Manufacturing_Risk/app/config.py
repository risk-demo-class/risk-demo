"""
全局配置: 从 .env 文件加载, 支持环境变量覆盖.
制造业风控系统 (仿 AI_Risk 电商风控).
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
    DB_PASSWORD: str = "Aa666666"
    DB_NAME: str = "manufacturing_risk"
    TEST_DB_NAME: str = "manufacturing_risk_test"

    def get_database_url_async(self, db_name: str | None = None) -> str:
        """构建异步 MySQL 连接 URL (用于 aiomysql 驱动)"""
        name = db_name or self.DB_NAME
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{name}?charset=utf8mb4"
        )

    def get_test_database_url_async(self) -> str:
        """测试库异步 URL"""
        return self.get_database_url_async(self.TEST_DB_NAME)

    # ---- 风控决策阈值 (评分 < PASS → 通过, < MARK → 标记, < REVIEW → 人工审核, >= REVIEW → 拒绝) ----
    RISK_PASS_THRESHOLD: int = 30
    RISK_MARK_THRESHOLD: int = 60
    RISK_REVIEW_THRESHOLD: int = 80
    RISK_MULTI_RULE_BONUS: int = 3     # 多规则命中时, 每条额外规则加的分
    RISK_VETO_MIN_SCORE: int = 90      # 一票否决时强制的最低分

    # ---- features 脱敏 (仿 P3-M6) ----
    # True: 响应里 features 返回全量 26 维 (教学/演示用)
    # False: 响应里 features={} (前端不展示)
    RISK_FEATURES_FULL_RETURN: bool = True

    # ---- LLM 配置 (DeepSeek, OpenAI 兼容格式; 复用电商 .env 的 key) ----
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com"
    LLM_MODEL_NAME: str = "deepseek-v4-flash"

    # ---- AI Agent chat 超时 ----
    AI_AGENT_CHAT_TIMEOUT_SEC: float = 60.0

    # ---- XGBoost 双轨融合配置 (默认关闭 = 纯规则模式) ----
    XGB_MODEL_PATH: str = "app/engine/xgb_model.json"   # 相对路径, ml_model.py resolve 成绝对
    XGB_ENABLED: bool = False                            # False = 纯规则, 兜底
    # 评分融合权重 (规则占比 + XGBoost 占比 = 1.0)
    ML_WEIGHT_RULE: float = 0.5
    ML_WEIGHT_XGB: float = 0.5
    # ML 单维度决策阈值
    ML_PASS_THRESHOLD: float = 0.30
    ML_MARK_THRESHOLD: float = 0.60
    ML_REVIEW_THRESHOLD: float = 0.80


settings = Settings()


# ============================================================
# Demo: 看一眼项目所有关键配置 (无需 DB / 启动服务, 纯 print)
# 跑法: python -m app.config
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Manufacturing_Risk 全局配置 (从 .env 加载, 缺省值兜底)")
    print("=" * 60)

    sections = [
        ("数据库", ["DB_HOST", "DB_PORT", "DB_USER", "DB_NAME", "TEST_DB_NAME"]),
        ("风控决策阈值", ["RISK_PASS_THRESHOLD", "RISK_MARK_THRESHOLD",
                       "RISK_REVIEW_THRESHOLD", "RISK_MULTI_RULE_BONUS", "RISK_VETO_MIN_SCORE"]),
        ("XGBoost 双轨融合", ["XGB_ENABLED", "XGB_MODEL_PATH",
                          "ML_WEIGHT_RULE", "ML_WEIGHT_XGB",
                          "ML_PASS_THRESHOLD", "ML_MARK_THRESHOLD", "ML_REVIEW_THRESHOLD"]),
        ("其他", ["RISK_FEATURES_FULL_RETURN"]),
    ]
    for sec_name, keys in sections:
        print(f"\n【{sec_name}】")
        for k in keys:
            v = getattr(settings, k, None)
            if v and "PASSWORD" in k and isinstance(v, str) and len(v) > 8:
                v = v[:2] + "***" + v[-2:]   # 脱敏
            print(f"  {k:<30} = {v}")
