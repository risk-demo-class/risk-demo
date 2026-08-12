"""P1 医疗规则初始定义；阈值仅用于教学演示。"""


def c(feature: str, op: str, value):
    return {"feature": feature, "op": op, "value": value}


RULE_DEFINITIONS = [
    ("MR001", "医保卡多院高频使用", "医保结算异常", "医保结算", {"all": [c("patient_hospital_count_7d", ">=", 3), c("patient_claim_count_24h", ">=", 3)]}, "极高", 95, "拒绝"),
    ("MR002", "短期跨省高频就医", "医保结算异常", "医保结算", c("patient_cross_province_count_30d", ">=", 3), "高", 75, "人工审核"),
    ("MR003", "单次医保结算金额异常", "医保结算异常", "医保结算", c("event_total_amount", ">=", 20000), "高", 75, "人工审核"),
    ("MR004", "医保支付占比异常", "医保结算异常", "医保结算", {"all": [c("claim_insurance_ratio", ">=", 0.98), c("event_total_amount", ">=", 5000)]}, "中", 50, "标记"),
    ("MR005", "同类药品重复开方", "处方合规", "处方开立", c("patient_same_drug_count_30d", ">=", 3), "极高", 95, "拒绝"),
    ("MR006", "单次超长供药", "处方合规", "处方开立", c("prescription_max_days_supply", ">", 90), "高", 75, "人工审核"),
    ("MR007", "特殊管理药品异常", "处方合规", "处方开立", c("prescription_controlled_drug_count", ">=", 2), "极高", 95, "拒绝"),
    ("MR008", "医生单日大处方", "处方合规", "处方开立", c("doctor_prescription_amount_1d", ">=", 100000), "高", 75, "人工审核"),
    ("MR009", "高价药占比异常", "处方合规", "处方开立", {"all": [c("prescription_high_value_ratio", ">=", 0.8), c("event_total_amount", ">=", 5000)]}, "中", 50, "标记"),
    ("MR010", "高频挂号疑似黄牛", "挂号行为", "挂号申请", c("patient_registration_count_7d", ">=", 8), "高", 75, "人工审核"),
    ("MR011", "高频退号疑似占号", "挂号行为", "挂号退号", {"all": [c("patient_cancel_count_30d", ">=", 5), c("patient_cancel_rate_30d", ">=", 0.7)]}, "高", 75, "人工审核"),
    ("MR012", "设备关联多患者", "挂号行为", "挂号申请", c("device_patient_count_7d", ">=", 5), "极高", 95, "拒绝"),
    ("MR013", "新账号高额结算", "医保结算异常", "医保结算", {"all": [c("patient_account_age_days", "<", 7), c("event_total_amount", ">=", 10000)]}, "中", 50, "标记"),
    ("MR014", "医生执业状态异常", "处方合规", "处方开立", c("doctor_license_abnormal", ">=", 1), "极高", 100, "拒绝"),
    ("MR015", "夜间异常密集业务", "通用", "通用", {"all": [c("event_is_night", ">=", 1), c("patient_claim_count_24h", ">=", 3)]}, "中", 50, "标记"),
]


BLACKLIST_RULE = {
    "rule_id": "MR016",
    "rule_name": "黑名单主体拦截",
    "rule_category": "通用",
    "risk_level": "极高",
    "risk_score": 100,
    "action": "拒绝",
    "description": "患者、证件、医保卡、手机、医生、设备或医院命中有效黑名单",
}
