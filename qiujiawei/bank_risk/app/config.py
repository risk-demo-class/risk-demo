"""
银行风控系统 - 全局配置: 从 .env 文件加载, 支持环境变量覆盖.

跟 AI_Risk/app/config.py 模式一致, 但适配银行场景:
  - 数据库名默认 bank_risk
  - APP_PORT 默认 8001
  - 枚举值映射到银行 4 大场景 (信用卡/贷款/转账/登录)
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
    DB_NAME: str = "bank_risk"
    TEST_DB_NAME: str = "bank_risk_test"

    def get_database_url_async(self, db_name: str | None = None) -> str:
        """构建异步 MySQL 连接 URL (用于 aiomysql 驱动)"""
        name = db_name or self.DB_NAME
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{name}?charset=utf8mb4"
        )

    def get_test_database_url_async(self) -> str:
        """测试库异步 URL (用于 conftest.py 初始化测试库)"""
        return self.get_database_url_async(self.TEST_DB_NAME)

    # ---- 风控决策阈值 ----
    # 评分 < PASS → 通过, < MARK → 标记, < REVIEW → 人工审核, >= REVIEW → 拒绝
    RISK_PASS_THRESHOLD: int = 30
    RISK_MARK_THRESHOLD: int = 60
    RISK_REVIEW_THRESHOLD: int = 80
    RISK_MULTI_RULE_BONUS: int = 3     # 多规则命中时, 每条额外规则加的分
    RISK_VETO_MIN_SCORE: int = 90      # 一票否决时强制的最低分

    # ---- LLM 配置 (阿里云百炼) ----
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_NAME: str = "qwen-plus"

    # ---- features 脱敏 ----
    # True: 响应里 features 返回全量 (教学/内部 admin 用)
    # False: 响应里 features={} (前端不展示, 防敏感数据外泄)
    RISK_FEATURES_FULL_RETURN: bool = True

    # ---- AI Agent chat 超时 ----
    AI_AGENT_CHAT_TIMEOUT_SEC: float = 60.0

    # ---- 案件超时自动关闭 ----
    # "待审核" 案件超过 N 小时没人审, 自动关案 (避免积压). 0 = 关闭此功能.
    CASE_AUTO_CLOSE_HOURS: int = 24

    # ---- 告警自动调度 ----
    # 告警检查的间隔 (秒). SCHEDULER_ENABLED=False 只能手动 POST /api/alerts/check
    SCHEDULER_ENABLED: bool = True
    SCHEDULER_INTERVAL_SECONDS: int = 900

    # ---- 风控告警阈值 ----
    ALERT_BACKLOG_THRESHOLD: int = 50           # 场景 1: 待审核案件积压数
    ALERT_RULE_HIT_RATE_MIN: float = 0.05       # 场景 2: 最近窗口规则命中率下限
    ALERT_BLACKLIST_HIT_RATE_MAX: float = 0.30  # 场景 3: 最近窗口撞黑比例上限

    # ---- XGBoost 双轨融合配置 ----
    XGB_MODEL_PATH: str = "app/engine/xgb_model.json"   # 相对路径, ml_model.py resolve 成绝对
    XGB_ENABLED: bool = True                              # False = 纯规则, 兜底
    # 评分融合权重 (规则占比 + XGBoost 占比 = 1.0), 当前 0.5/0.5 等权
    ML_WEIGHT_RULE: float = 0.5
    ML_WEIGHT_XGB: float = 0.5
    # ML 单维度的决策阈值 (P(拒绝) 概率 → 4 档)
    ML_PASS_THRESHOLD: float = 0.30
    ML_MARK_THRESHOLD: float = 0.60
    ML_REVIEW_THRESHOLD: float = 0.80
    # 训练数据加载: 从 risk_assessment 取最近 N 条 (按 create_time DESC)
    XGB_TRAIN_DATA_LIMIT: int = 2500
    # 训练参数 (优化正负样本比 + 早停)
    XGB_TEST_SIZE: float = 0.2                # 验证集比例 (stratify 拆分, 保持正负比)
    XGB_EARLY_STOPPING_ROUNDS: int = 10       # 早停: 验证集指标连续 N 轮不升就停
    XGB_MIN_SAMPLES: int = 1250              # 最小样本数
    XGB_MAX_SCALE_POS_WEIGHT: float = 10.0   # scale_pos_weight 上限, 防过拟合
    # 训练超参 (防假收敛)
    XGB_MAX_DEPTH: int = 6                   # 树最大深度
    XGB_LEARNING_RATE: float = 0.1           # 学习率
    XGB_MIN_CHILD_WEIGHT: int = 3            # 子节点最小权重
    XGB_REG_ALPHA: float = 0.1               # L1 正则
    XGB_REG_LAMBDA: float = 1.0              # L2 正则
    XGB_GAMMA: float = 0.0                   # 分裂最小损失下降
    XGB_SUBSAMPLE: float = 0.8               # 训练样本采样比例
    XGB_COLSAMPLE_BYTREE: float = 0.8        # 特征采样比例
    XGB_WARMUP_ROUNDS: int = 50              # 早停 warmup: 前 N 轮强制不早停
    XGB_EARLY_STOP_METRIC: str = "auc"       # 早停监控指标
    # 质量验收 (假收敛检测)
    XGB_MIN_BEST_ITER: int = 30              # 真正收敛 best_iter 应 >= 30
    XGB_MIN_VAL_AUC: float = 0.70            # val_auc < 0.70 警告模型无效
    XGB_MIN_VAL_F1: float = 0.50             # val_f1 < 0.50 警告模型无效
    XGB_MIN_POS_RATIO: float = 0.15          # 正例比例 < 15% 警告
    XGB_MAX_POS_RATIO: float = 0.60          # 正例比例 > 60% 警告

    # ---- 应用 ----
    APP_PORT: int = 8001


settings = Settings()


# ============================================================
# Demo: 看一眼项目所有关键配置 (无需 DB / 启动服务, 纯 print)
# 跑法: python -m bank_risk.app.config
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("bank_risk 全局配置 (从 .env 加载, 缺省值兜底)")
    print("=" * 60)

    sections = [
        ("数据库", ["DB_HOST", "DB_PORT", "DB_USER", "DB_NAME", "TEST_DB_NAME"]),
        ("风控决策阈值", ["RISK_PASS_THRESHOLD", "RISK_MARK_THRESHOLD",
                       "RISK_REVIEW_THRESHOLD", "RISK_MULTI_RULE_BONUS", "RISK_VETO_MIN_SCORE"]),
        ("LLM (阿里云百炼)", ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME"]),
        ("XGBoost 双轨融合", ["XGB_ENABLED", "XGB_MODEL_PATH",
                          "ML_WEIGHT_RULE", "ML_WEIGHT_XGB",
                          "ML_PASS_THRESHOLD", "ML_MARK_THRESHOLD", "ML_REVIEW_THRESHOLD"]),
        ("告警", ["ALERT_BACKLOG_THRESHOLD", "ALERT_RULE_HIT_RATE_MIN",
                "ALERT_BLACKLIST_HIT_RATE_MAX"]),
        ("调度器", ["SCHEDULER_ENABLED", "SCHEDULER_INTERVAL_SECONDS", "CASE_AUTO_CLOSE_HOURS"]),
        ("其他", ["AI_AGENT_CHAT_TIMEOUT_SEC", "RISK_FEATURES_FULL_RETURN", "APP_PORT"]),
    ]
    for sec_name, keys in sections:
        print(f"\n【{sec_name}】")
        for k in keys:
            v = getattr(settings, k, None)
            if v and "API_KEY" in k and isinstance(v, str) and len(v) > 8:
                v = v[:4] + "***" + v[-4:]   # 脱敏
            print(f"  {k:<30} = {v}")
