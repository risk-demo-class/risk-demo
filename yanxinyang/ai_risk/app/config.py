# -*- coding: utf-8 -*-
"""配置系统 —— 对应教学宝典《第 12 章：配置系统》

设计哲学（宝典 12.3）：
    默认值兜底 → 测试可环境变量覆盖 → 错类型启动报错

宝典原文用 Pydantic ``Settings(BaseSettings)`` + ``env_file=".env"``。
本项目为"零依赖可直接运行"版本，用标准库实现**等价语义**：
    1. 字段声明式定义（带类型 + 默认值）
    2. 自动从 .env 加载
    3. 环境变量优先级高于 .env
    4. 类型转换失败 → 启动即报错（ConfigError）

只有 config.py 被所有人 import —— **单一配置源**（宝典第 14 章关键解读）。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, get_type_hints

# ---------------------------------------------------------------- 路径常量
BASE_DIR = Path(__file__).resolve().parent.parent          # 项目根 ai_risk/
APP_DIR = BASE_DIR / "app"
WEB_DIR = BASE_DIR / "web"
LOG_DIR = BASE_DIR / "logs"
MODEL_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
for _d in (LOG_DIR, MODEL_DIR, DATA_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class ConfigError(RuntimeError):
    """配置类型错误 —— 启动即失败，绝不带着脏配置上线。"""


def _load_env_file(path: Path) -> Dict[str, str]:
    """极简 .env 解析（等价 pydantic 的 env_file）。"""
    result: Dict[str, str] = {}
    if not path.exists():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        result[key.strip()] = value
    return result


def _cast(name: str, raw: Any, target: type) -> Any:
    """字符串 → 目标类型，失败即 ConfigError（对应"错类型启动报错"）。"""
    if raw is None:
        return None
    if isinstance(raw, target) and not isinstance(raw, bool) or target is str and isinstance(raw, str):
        return raw
    try:
        if target is bool:
            if isinstance(raw, bool):
                return raw
            return str(raw).strip().lower() in ("1", "true", "yes", "on", "y")
        if target is int:
            return int(float(str(raw)))
        if target is float:
            return float(str(raw))
        return target(raw)  # type: ignore[call-arg]
    except (TypeError, ValueError) as exc:  # noqa: PERF203
        raise ConfigError(f"配置项 {name}={raw!r} 无法转换为 {target.__name__}: {exc}") from exc


class Settings:
    """全局配置（字段名与教学宝典完全一致）。"""

    # ============================== 应用 ==============================
    APP_NAME: str = "智学安·教育风控平台（教学版）"
    APP_VERSION: str = "v3.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True

    # ============================== 数据库（宝典第 13 章）==============================
    # 宝典生产栈：MySQL 8.0 + SQLAlchemy 2.x 异步 + aiomysql（utf8mb4）
    # 教学零依赖栈：SQLite（同一套 DDL 语义 / 同一套事务边界 / 同一套连接池参数）
    DB_DIALECT: str = "sqlite"          # sqlite | mysql（mysql 需装 SQLAlchemy+aiomysql）
    DB_PATH: str = str(DATA_DIR / "ai_risk.db")
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "root"
    DB_NAME: str = "ai_risk"
    DB_CHARSET: str = "utf8mb4"         # FAQ 6：数据库中文乱码 → 必须 utf8mb4
    DB_POOL_SIZE: int = 10              # 宝典 13.1 pool_size=10
    DB_MAX_OVERFLOW: int = 20           # 宝典 13.1 max_overflow=20
    DB_POOL_RECYCLE: int = 3600         # 宝典 13.1 避 MySQL wait_timeout

    # ============================== 决策阈值（宝典 12.2 第 1 类）==============================
    RISK_PASS_THRESHOLD: int = 30       # < 30            → 低 / 通过
    RISK_MARK_THRESHOLD: int = 60       # [30, 60)        → 中 / 标记
    RISK_REVIEW_THRESHOLD: int = 80     # [60, 80)        → 高 / 人工审核
    RISK_VETO_MIN_SCORE: int = 90       # 一票否决强制下限 → final = max(final, 90)

    # ============================== 融合参数（宝典 12.2 第 2 类）==============================
    ML_WEIGHT_RULE: float = 0.5         # α
    ML_WEIGHT_XGB: float = 0.5          # β
    ML_PASS_THRESHOLD: float = 0.30     # P<0.30       → 通过
    ML_MARK_THRESHOLD: float = 0.60     # [0.30,0.60)  → 标记
    ML_REVIEW_THRESHOLD: float = 0.80   # [0.60,0.80)  → 人工审核；≥0.80 → 拒绝

    # ============================== 告警阈值（宝典 12.2 第 3 类）==============================
    ALERT_PENDING_CASE_THRESHOLD: int = 50      # 待审核案件堆积
    ALERT_RULE_HIT_RATE_MIN: float = 5.0        # 规则命中率下限 %
    ALERT_BLACKLIST_HIT_RATE_MAX: float = 30.0  # 黑名单命中率上限 %
    ALERT_CHECK_WINDOW_HOURS: int = 1           # 告警检查窗口

    # ============================== P4-L3 新增（宝典 12.3）==============================
    CASE_TIMEOUT_HOURS: int = 24                # 案件超时自动关闭（0=关）
    ALERT_SCHEDULER_INTERVAL_MIN: int = 15      # 告警自动调度间隔（0=关）

    # ============================== XGBoost（宝典第 7 章）==============================
    XGB_ENABLED: bool = True
    XGB_MODEL_PATH: str = str(MODEL_DIR / "xgb_model.json")   # 官方原生 JSON，非 joblib
    # —— 5 个关键参数（宝典 7.3）
    XGB_N_ESTIMATORS: int = 300
    XGB_MAX_DEPTH: int = 4
    XGB_LEARNING_RATE: float = 0.08
    XGB_SUBSAMPLE: float = 0.8
    XGB_COLSAMPLE_BYTREE: float = 0.8
    # —— 训练 4 必做（宝典 7.7）
    XGB_TEST_SIZE: float = 0.2                  # 80/20 stratify 拆分
    XGB_EARLY_STOPPING_ROUNDS: int = 10         # 早停
    XGB_MIN_SAMPLES: int = 1250                 # 25 维 × 50
    XGB_MAX_SCALE_POS_WEIGHT: float = 10.0      # scale_pos_weight 上限
    # —— 5 件套抗假收敛（宝典 7.7）
    XGB_EARLY_STOP_METRIC: str = "auc"          # ① 早停指标换 auc
    XGB_WARMUP_ROUNDS: int = 50                 # ② warmup 50 轮强制不早停
    XGB_REG_ALPHA: float = 0.1                  # ③ L1
    XGB_REG_LAMBDA: float = 1.0                 # ③ L2
    XGB_MIN_CHILD_WEIGHT: float = 3.0           # ③ 最小子节点权重
    # —— 假收敛 3 信号阈值（宝典 7.7）
    XGB_MIN_BEST_ITER: int = 30
    XGB_MIN_VAL_AUC: float = 0.70
    XGB_MIN_VAL_F1: float = 0.50
    XGB_BASELINE_ACC_MARGIN: float = 0.02       # acc 必须 > baseline + 2%
    # —— 最佳 F1 阈值扫描（宝典 7.8）
    XGB_THRESHOLD_SCAN_START: float = 0.10
    XGB_THRESHOLD_SCAN_END: float = 0.85
    XGB_THRESHOLD_SCAN_STEP: float = 0.05
    XGB_LABEL_SCORE_THRESHOLD: int = 80         # 规则反推 label：final_score >= 80 为正样本

    # ============================== AI Agent（宝典第 11 章）==============================
    # 大模型供应商（OpenAI 兼容协议）：siliconflow（硅基流动）/ dashscope（阿里云百炼）/ openai
    # 密钥请放到 .env（或环境变量 LLM_API_KEY），勿硬编码进源码。
    AI_AGENT_ENABLED: bool = True
    LLM_PROVIDER: str = "siliconflow"                   # 硅基流动
    LLM_API_KEY: str = ""                               # 在 .env 中配置，勿硬编码进源码
    LLM_BASE_URL: str = "https://api.siliconflow.cn/v1" # 硅基流动 OpenAI 兼容地址
    LLM_MODEL: str = "Qwen/Qwen3-8B"                    # 硅基流动模型名（含组织前缀）
    LLM_TEMPERATURE: float = 0.1                # 宝典 11.3：温度 0.1，业务要稳定
    AI_AGENT_CHAT_TIMEOUT_SEC: int = 60         # 宝典 11.3：防 LLM 卡死
    AI_AGENT_MAX_HISTORY: int = 20

    # ============================== 日志 ==============================
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = str(LOG_DIR / "server.log")

    # ------------------------------------------------------------------
    def __init__(self, env_file: str = ".env", **overrides: Any) -> None:
        env_values = _load_env_file(BASE_DIR / env_file)
        hints = get_type_hints(type(self))
        for name, target in hints.items():
            if name.startswith("_"):
                continue
            default = getattr(type(self), name)
            raw = overrides.get(name, os.environ.get(name, env_values.get(name, default)))
            setattr(self, name, _cast(name, raw, target))
        self._validate()

    def _validate(self) -> None:
        """跨字段一致性校验（阈值必须单调递增，权重必须和为 1）。"""
        if not (0 < self.RISK_PASS_THRESHOLD < self.RISK_MARK_THRESHOLD
                < self.RISK_REVIEW_THRESHOLD <= 100):
            raise ConfigError(
                "决策阈值必须满足 0 < PASS < MARK < REVIEW <= 100，"
                f"当前为 {self.RISK_PASS_THRESHOLD}/{self.RISK_MARK_THRESHOLD}/{self.RISK_REVIEW_THRESHOLD}"
            )
        if not (0 < self.ML_PASS_THRESHOLD < self.ML_MARK_THRESHOLD < self.ML_REVIEW_THRESHOLD <= 1):
            raise ConfigError("ML 阈值必须满足 0 < PASS < MARK < REVIEW <= 1")
        total = round(self.ML_WEIGHT_RULE + self.ML_WEIGHT_XGB, 6)
        if abs(total - 1.0) > 1e-6:
            raise ConfigError(f"融合权重 α+β 必须为 1.0，当前 {total}")

    # ------------------------------------------------------------------
    def get_database_url_async(self) -> str:
        """宝典 13.1 的 ``settings.get_database_url_async()``。"""
        if self.DB_DIALECT == "mysql":
            return (f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
                    f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset={self.DB_CHARSET}")
        return f"sqlite+aiosqlite:///{self.DB_PATH}"

    def get_database_url(self) -> str:
        if self.DB_DIALECT == "mysql":
            return (f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
                    f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset={self.DB_CHARSET}")
        return f"sqlite:///{self.DB_PATH}"

    def as_dict(self) -> Dict[str, Any]:
        """给 /api/system/config 用（脱敏）。"""
        hints = get_type_hints(type(self))
        out: Dict[str, Any] = {}
        for name in hints:
            value = getattr(self, name)
            if "KEY" in name or "PASSWORD" in name:
                value = ("*" * 8 + str(value)[-4:]) if value else ""
            out[name] = value
        return out

    def config_groups(self) -> Dict[str, list]:
        """宝典 12.2 的"三大类阈值"分组，前端配置页直接渲染。"""
        def item(field: str, label: str, note: str = "") -> Dict[str, Any]:
            return {"field": field, "label": label, "value": getattr(self, field), "note": note}

        return {
            "决策阈值": [
                item("RISK_PASS_THRESHOLD", "通过阈值", "final_score < 30 → 低 / 通过"),
                item("RISK_MARK_THRESHOLD", "标记阈值", "30-59 → 中 / 标记"),
                item("RISK_REVIEW_THRESHOLD", "审核阈值", "60-79 → 高 / 人工审核；80+ → 极高 / 拒绝"),
                item("RISK_VETO_MIN_SCORE", "一票否决下限", "存在极高规则 → final = max(final, 90)"),
            ],
            "融合参数": [
                item("ML_WEIGHT_RULE", "规则权重 α", "final = α×rule + β×ml"),
                item("ML_WEIGHT_XGB", "模型权重 β", "默认 0.5，可调"),
                item("ML_PASS_THRESHOLD", "ML 通过阈值", "P < 0.30 → 通过"),
                item("ML_MARK_THRESHOLD", "ML 标记阈值", "0.30-0.60 → 标记"),
                item("ML_REVIEW_THRESHOLD", "ML 审核阈值", "0.60-0.80 → 人工审核；≥0.80 → 拒绝"),
            ],
            "告警阈值": [
                item("ALERT_PENDING_CASE_THRESHOLD", "待审核案件堆积", "超过则告警"),
                item("ALERT_RULE_HIT_RATE_MIN", "规则命中率下限 %", "过低说明规则失效"),
                item("ALERT_BLACKLIST_HIT_RATE_MAX", "黑名单命中率上限 %", "过高说明被攻击"),
                item("ALERT_CHECK_WINDOW_HOURS", "告警检查窗口 h", ""),
            ],
            "P4-L3 新增": [
                item("CASE_TIMEOUT_HOURS", "案件超时自动关闭 h", "0 = 关闭此功能"),
                item("ALERT_SCHEDULER_INTERVAL_MIN", "告警调度间隔 min", "0 = 关闭"),
                item("XGB_TEST_SIZE", "训练集拆分", "80/20 stratify"),
                item("XGB_EARLY_STOPPING_ROUNDS", "早停轮数", "验证集指标连续 N 轮不升即停"),
                item("XGB_MIN_SAMPLES", "最小样本量", "25 维 × 50 = 1250"),
                item("XGB_MAX_SCALE_POS_WEIGHT", "scale_pos_weight 上限", "防极端不平衡过拟合"),
            ],
            "抗假收敛 5 件套": [
                item("XGB_EARLY_STOP_METRIC", "① 早停指标", "auc 对不平衡敏感"),
                item("XGB_WARMUP_ROUNDS", "② warmup 轮数", "前 N 轮强制不早停"),
                item("XGB_REG_ALPHA", "③ L1 正则", ""),
                item("XGB_REG_LAMBDA", "③ L2 正则", ""),
                item("XGB_MIN_CHILD_WEIGHT", "③ min_child_weight", ""),
                item("XGB_MIN_BEST_ITER", "④ best_iter 下限", "< 30 视为假收敛"),
                item("XGB_MIN_VAL_AUC", "④ val_auc 下限", "< 0.70 视为假收敛"),
                item("XGB_MIN_VAL_F1", "④ val_f1 下限", "< 0.50 视为假收敛"),
                item("XGB_BASELINE_ACC_MARGIN", "⑤ baseline 余量", "acc 必须 > baseline + 2%"),
            ],
        }


settings = Settings()
