"""
银行风控系统 - 全局配置 (全量移植自 AI_Risk, 语义替换为银行域)

从 .env 文件加载, 支持环境变量覆盖.
关键差异 (vs 基线电商 AI_Risk):
  - 业务事件类型: 电商(下单/支付/售后申请/物流投诉) → 银行(transfer/loan_apply/card_txn/repay/login)
  - 规则分类: 电商(订单欺诈/支付风险/...) → 银行(账户风险/交易风险/信贷风险/反洗钱/设备风险/登录风险)
  - 黑名单维度: 电商(用户/地址/手机号) → 银行(account/device/ip/phone/id_card/merchant/beneficiary)
  - 决策: 银行 5 级 (pass/review/reject/freeze/report)
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置, 自动从 .env 文件和环境变量加载"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # ---- 数据库配置 (MySQL + aiomysql 异步驱动) ----
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "bank_risk"

    def get_database_url_async(self, db_name: str | None = None) -> str:
        """构建异步 MySQL 连接 URL (用于 aiomysql 驱动)"""
        name = db_name or self.DB_NAME
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{name}?charset=utf8mb4"
        )

    # ---- 风控决策阈值 (评分 0-100, 5 档决策) ----
    # 评分 < PASS → 通过, < MARK → 标记, < REVIEW → 人工审核, < FREEZE → 拒绝, >= FREEZE → 冻结
    RISK_PASS_THRESHOLD: int = 30
    RISK_MARK_THRESHOLD: int = 60
    RISK_REVIEW_THRESHOLD: int = 80
    RISK_FREEZE_THRESHOLD: int = 90      # 一票否决 / 冻结线
    RISK_MULTI_RULE_BONUS: int = 3       # 多规则命中时, 每条额外规则加的分
    RISK_VETO_MIN_SCORE: int = 90        # 一票否决时强制的最低分

    # 按 event_type 拆的阈值 (银行场景: 转账/登录 比 还款 严)
    RISK_EVENT_THRESHOLDS: dict[str, dict[str, int]] = {
        "transfer":   {"pass": 30, "mark": 60, "review": 80, "freeze": 90},  # 电诈资金链核心
        "loan_apply": {"pass": 25, "mark": 55, "review": 75, "freeze": 90},  # 信贷审查
        "card_txn":   {"pass": 30, "mark": 60, "review": 80, "freeze": 90},  # 伪冒盗刷
        "repay":      {"pass": 40, "mark": 65, "review": 85, "freeze": 92},  # 贷后回款
        "login":      {"pass": 25, "mark": 55, "review": 80, "freeze": 90},  # 账户安全
        "通用":       {"pass": 30, "mark": 60, "review": 80, "freeze": 90},
    }

    # ---- 风险等级 ↔ 分数 映射 ----
    RISK_LEVEL_SCORE_MAP: dict[str, tuple[int, int]] = {
        "低":   (0, 29),
        "中":   (30, 59),
        "高":   (60, 84),
        "极高": (85, 100),
    }

    def get_event_thresholds(self, event_type: str) -> dict[str, int]:
        return self.RISK_EVENT_THRESHOLDS.get(
            event_type,
            {"pass": self.RISK_PASS_THRESHOLD, "mark": self.RISK_MARK_THRESHOLD,
             "review": self.RISK_REVIEW_THRESHOLD, "freeze": self.RISK_FREEZE_THRESHOLD},
        )

    # ---- LLM 配置 (真实大模型 API, 阿里云百炼) ----
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_NAME: str = "qwen-plus"

    # ---- features 脱敏 ----
    RISK_FEATURES_FULL_RETURN: bool = True

    # ---- AI Agent chat 超时 ----
    AI_AGENT_CHAT_TIMEOUT_SEC: float = 60.0

    # ---- 案件超时自动关闭 ----
    CASE_TIMEOUT_HOURS: int = 24

    # ---- 告警自动调度 ----
    ALERT_SCHEDULER_INTERVAL_MIN: int = 15
    ALERT_PENDING_CASE_THRESHOLD: int = 50
    ALERT_RULE_HIT_RATE_MIN: float = 5.0
    ALERT_BLACKLIST_HIT_RATE_MAX: float = 30.0
    ALERT_CHECK_WINDOW_HOURS: int = 1

    # ---- XGBoost 双轨融合配置 (11 维银行特征) ----
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
    XGB_MIN_SAMPLES: int = 550       # 11 维 × 50 倍
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


# ---- 模块级语义常量 (供 from app.config import 直接引用) ----
# 黑名单类型集合 (银行域)
BLACKLIST_TYPES: dict[str, str] = {
    "account": "涉案/失信账户黑名单",
    "device": "设备指纹黑名单 (群控/模拟器)",
    "ip": "IP 黑名单 (代理/境外跳板)",
    "phone": "手机号黑名单 (涉案/营销号)",
    "id_card": "证件号黑名单 (失信被执行人)",
    "merchant": "商户黑名单 (非法收单/洗钱通道)",
    "beneficiary": "受益人黑名单 (资金归集终端)",
}
BLACKLIST_TYPE_KEYS: tuple[str, ...] = tuple(BLACKLIST_TYPES.keys())

# 业务事件类型枚举 (银行 event_type)
BANK_EVENT_TYPES: tuple[str, ...] = ("transfer", "loan_apply", "card_txn", "repay", "login")

# 5 档银行决策枚举
DECISION_PASS: str = "pass"
DECISION_REVIEW: str = "review"
DECISION_REJECT: str = "reject"
DECISION_FREEZE: str = "freeze"
DECISION_REPORT: str = "report"

# 一票否决触发的最低规则严重度
VETO_SEVERITY: int = 3

# 银行规则链阈值 (validator.py 硬编码规则使用, 与 5 档评分阈值分离)
BANK_RULE_THRESHOLDS: dict[str, dict[str, float]] = {
    "transfer": {
        "amt_report": 200000.0,    # 单笔 >=20万 大额报送
        "amt_suspect": 50000.0,    # 单笔 >=5万 模型复核
        "peer_cnt_1h": 10,         # 近 1h 交易对手数 >=10 疑似资金归集
    },
    "card_txn": {
        "amt_report": 200000.0,
        "amt_suspect": 50000.0,
        "peer_cnt_1h": 10,
    },
    "loan_apply": {
        "credit_query_30d": 10,    # 近 30 日征信查询 >=10 多头借贷
        "multi_loan_platforms": 5, # 申贷平台数 >=5 借名骗贷
    },
    "login": {
        "fail_5m": 5,              # 5 分钟登录失败 >=5 疑似撞库
    },
    "repay": {},
}


settings = Settings()


if __name__ == "__main__":
    print("=" * 60)
    print("Bank-Risk 全局配置 (从 .env 加载, 缺省值兜底)")
    print("=" * 60)
    sections = [
        ("数据库", ["DB_HOST", "DB_PORT", "DB_USER", "DB_NAME"]),
        ("风控决策阈值", ["RISK_PASS_THRESHOLD", "RISK_MARK_THRESHOLD",
                       "RISK_REVIEW_THRESHOLD", "RISK_FREEZE_THRESHOLD", "RISK_VETO_MIN_SCORE"]),
        ("LLM (阿里云百炼)", ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_NAME"]),
        ("XGBoost 双轨融合", ["XGB_ENABLED", "XGB_MODEL_PATH",
                          "ML_WEIGHT_RULE", "ML_WEIGHT_XGB"]),
        ("其他", ["AI_AGENT_CHAT_TIMEOUT_SEC", "RISK_FEATURES_FULL_RETURN"]),
    ]
    for sec_name, keys in sections:
        print(f"\n【{sec_name}】")
        for k in keys:
            v = getattr(settings, k, None)
            if v and "API_KEY" in k and isinstance(v, str) and len(v) > 8:
                v = v[:4] + "***" + v[-4:]
            print(f"  {k:<30} = {v}")
