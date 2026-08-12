"""第一版 20 条银行规则的唯一种子数据源。"""

from typing import Any

from app.models import Decision, RiskLevel, RuleEventType
from app.models_risk import RuleCategory


def _single(field: str, op: str, value: object) -> dict[str, object]:
    return {"field": field, "op": op, "value": value}


def _and(*conditions: dict[str, object]) -> dict[str, object]:
    return {"and": list(conditions)}


def _or(*conditions: dict[str, object]) -> dict[str, object]:
    return {"or": list(conditions)}


PRESET_RULES: tuple[dict[str, Any], ...] = (
    {
        "rule_id": "B001", "rule_name": "24小时失败登录过多",
        "rule_category": RuleCategory.ACCOUNT_SECURITY, "event_type": RuleEventType.LOGIN,
        "rule_condition": _single("user_failed_login_count_24h", ">=", 5),
        "risk_level": RiskLevel.HIGH, "risk_score": 65, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B002", "rule_name": "新设备且代理IP",
        "rule_category": RuleCategory.DEVICE_RISK, "event_type": RuleEventType.LOGIN,
        "rule_condition": _and(_single("device_is_new", "==", 1), _single("ip_is_proxy", "==", 1)),
        "risk_level": RiskLevel.HIGH, "risk_score": 75, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B003", "rule_name": "短时超远距离登录",
        "rule_category": RuleCategory.IP_GEO_RISK, "event_type": RuleEventType.LOGIN,
        "rule_condition": _single("login_geo_jump_km", ">=", 1000),
        "risk_level": RiskLevel.EXTREME, "risk_score": 90, "action": Decision.REJECT,
    },
    {
        "rule_id": "B004", "rule_name": "异地大额转账",
        "rule_category": RuleCategory.TRANSFER_FRAUD, "event_type": RuleEventType.TRANSFER,
        "rule_condition": _and(_single("txn_cross_city", "==", 1), _single("txn_amount", ">=", 50000)),
        "risk_level": RiskLevel.EXTREME, "risk_score": 90, "action": Decision.REJECT,
    },
    {
        "rule_id": "B005", "rule_name": "凌晨密集交易",
        "rule_category": RuleCategory.TRANSFER_FRAUD, "event_type": RuleEventType.TRANSFER,
        "rule_condition": _and(_single("txn_is_night", "==", 1), _single("txn_count_1h", ">=", 3)),
        "risk_level": RiskLevel.HIGH, "risk_score": 70, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B006", "rule_name": "新设备大额转账",
        "rule_category": RuleCategory.DEVICE_RISK, "event_type": RuleEventType.TRANSFER,
        "rule_condition": _and(_single("device_is_new", "==", 1), _single("txn_amount", ">=", 30000)),
        "risk_level": RiskLevel.HIGH, "risk_score": 75, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B007", "rule_name": "金额远超个人均值",
        "rule_category": RuleCategory.TRANSFER_FRAUD, "event_type": RuleEventType.TRANSFER,
        "rule_condition": _single("txn_amount_vs_avg_ratio", ">=", 5),
        "risk_level": RiskLevel.HIGH, "risk_score": 70, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B008", "rule_name": "陌生收款人大额转账",
        "rule_category": RuleCategory.TRANSFER_FRAUD, "event_type": RuleEventType.TRANSFER,
        "rule_condition": _and(_single("txn_is_new_beneficiary", "==", 1), _single("txn_amount", ">=", 20000)),
        "risk_level": RiskLevel.HIGH, "risk_score": 70, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B009", "rule_name": "多账户向单一账户归集",
        "rule_category": RuleCategory.TRANSFER_FRAUD, "event_type": RuleEventType.TRANSFER,
        "rule_condition": _single("txn_beneficiary_payer_count_1h", ">=", 5),
        "risk_level": RiskLevel.EXTREME, "risk_score": 95, "action": Decision.REJECT,
    },
    {
        "rule_id": "B010", "rule_name": "24小时累计超大额",
        "rule_category": RuleCategory.TRANSFER_FRAUD, "event_type": RuleEventType.TRANSFER,
        "rule_condition": _single("txn_amount_24h", ">=", 200000),
        "risk_level": RiskLevel.EXTREME, "risk_score": 90, "action": Decision.REJECT,
    },
    {
        "rule_id": "B011", "rule_name": "高额度使用率大额消费",
        "rule_category": RuleCategory.CARD_RISK, "event_type": RuleEventType.CARD_PAYMENT,
        "rule_condition": _and(_single("card_utilization_rate", ">=", 0.95), _single("txn_amount", ">=", 10000)),
        "risk_level": RiskLevel.HIGH, "risk_score": 75, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B012", "rule_name": "凌晨连续刷卡",
        "rule_category": RuleCategory.CARD_RISK, "event_type": RuleEventType.CARD_PAYMENT,
        "rule_condition": _and(_single("txn_is_night", "==", 1), _single("txn_count_1h", ">=", 4)),
        "risk_level": RiskLevel.HIGH, "risk_score": 70, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B013", "rule_name": "新设备信用卡大额交易",
        "rule_category": RuleCategory.DEVICE_RISK, "event_type": RuleEventType.CARD_PAYMENT,
        "rule_condition": _and(_single("device_is_new", "==", 1), _single("txn_amount", ">=", 10000)),
        "risk_level": RiskLevel.HIGH, "risk_score": 70, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B014", "rule_name": "消费金额显著偏离均值",
        "rule_category": RuleCategory.CARD_RISK, "event_type": RuleEventType.CARD_PAYMENT,
        "rule_condition": _single("txn_amount_vs_avg_ratio", ">=", 8),
        "risk_level": RiskLevel.HIGH, "risk_score": 75, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B015", "rule_name": "高负债率申请",
        "rule_category": RuleCategory.CREDIT_RISK, "event_type": RuleEventType.LOAN_APPLICATION,
        "rule_condition": _single("loan_debt_ratio", ">=", 0.70),
        "risk_level": RiskLevel.EXTREME, "risk_score": 90, "action": Decision.REJECT,
    },
    {
        "rule_id": "B016", "rule_name": "低信用分申请",
        "rule_category": RuleCategory.CREDIT_RISK, "event_type": RuleEventType.LOAN_APPLICATION,
        "rule_condition": _single("user_credit_score", "<", 550),
        "risk_level": RiskLevel.HIGH, "risk_score": 70, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B017", "rule_name": "低KYC大额申请",
        "rule_category": RuleCategory.CREDIT_RISK, "event_type": RuleEventType.LOAN_APPLICATION,
        "rule_condition": _and(_single("user_kyc_level", "<=", 1), _single("loan_amount", ">=", 50000)),
        "risk_level": RiskLevel.HIGH, "risk_score": 75, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B018", "rule_name": "30天多头借贷",
        "rule_category": RuleCategory.CREDIT_RISK, "event_type": RuleEventType.LOAN_APPLICATION,
        "rule_condition": _single("loan_institution_count_30d", ">=", 3),
        "risk_level": RiskLevel.HIGH, "risk_score": 80, "action": Decision.MANUAL_REVIEW,
    },
    {
        "rule_id": "B019", "rule_name": "同一设备多人共用",
        "rule_category": RuleCategory.DEVICE_RISK, "event_type": RuleEventType.COMMON,
        "rule_condition": _single("device_user_count_30d", ">=", 5),
        "risk_level": RiskLevel.MEDIUM, "risk_score": 50, "action": Decision.FLAG,
    },
    {
        "rule_id": "B020", "rule_name": "代理或Tor访问",
        "rule_category": RuleCategory.IP_GEO_RISK, "event_type": RuleEventType.COMMON,
        "rule_condition": _or(_single("ip_is_proxy", "==", 1), _single("ip_is_tor", "==", 1)),
        "risk_level": RiskLevel.MEDIUM, "risk_score": 50, "action": Decision.FLAG,
    },
)


def validate_preset_rules() -> None:
    ids = [rule["rule_id"] for rule in PRESET_RULES]
    if len(PRESET_RULES) != 20 or len(set(ids)) != 20:
        raise RuntimeError("预置规则必须恰好为20条且ID唯一")


validate_preset_rules()

