"""系统设置接口 — 查看/更新阈值配置"""
from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api/settings", tags=["系统设置"])


@router.get("")
async def get_settings():
    """查看当前生效配置(教学: 只读展示,改 .env 后重启生效)。"""
    return {
        "decision_thresholds": {
            "pass": settings.RISK_PASS_THRESHOLD,
            "mark": settings.RISK_MARK_THRESHOLD,
            "review": settings.RISK_REVIEW_THRESHOLD,
            "veto_min": settings.RISK_VETO_MIN_SCORE,
        },
        "fusion": {
            "alpha_rule": settings.ML_WEIGHT_RULE,
            "beta_ml": settings.ML_WEIGHT_XGB,
        },
        "alerts": {
            "pending_case_threshold": settings.ALERT_PENDING_CASE_THRESHOLD,
            "rule_hit_rate_min": settings.ALERT_RULE_HIT_RATE_MIN,
            "blacklist_hit_rate_max": settings.ALERT_BLACKLIST_HIT_RATE_MAX,
            "check_window_hours": settings.ALERT_CHECK_WINDOW_HOURS,
        },
        "case_timeout_hours": settings.CASE_TIMEOUT_HOURS,
        "xgb": {
            "enabled": settings.XGB_ENABLED,
            "model_path": settings.XGB_MODEL_PATH,
        },
    }
