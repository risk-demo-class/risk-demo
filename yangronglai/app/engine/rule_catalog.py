"""The eight mandatory bank rules from the project brief."""

from typing import Any


RULE_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "rule_id": "R001",
        "rule_name": "异地大额转账",
        "scenarios": ["TRANSFER"],
        "condition": {
            "and": [
                {"field": "amount", "op": ">", "value": 50000},
                {"field": "current_city", "op": "!=", "value_field": "usual_city"},
            ]
        },
        "risk_level": "极高",
        "risk_score": 100,
        "decision": "拒绝",
        "priority": 100,
        "description": "当前登录城市与常用城市不同，且转账金额超过 5 万元。",
        "version": "1.0.0",
    },
    {
        "rule_id": "R002",
        "rule_name": "凌晨密集操作",
        "scenarios": ["CARD", "TRANSFER"],
        "condition": {
            "and": [
                {"field": "event_hour", "op": "between", "value": [0, 5]},
                {"field": "transactions_1h", "op": ">=", "value": 3},
            ]
        },
        "risk_level": "高",
        "risk_score": 70,
        "decision": "人工审核",
        "priority": 80,
        "description": "凌晨 0—5 点，用户一小时内发生至少 3 笔交易。",
        "version": "1.0.0",
    },
    {
        "rule_id": "R005",
        "rule_name": "新设备大额",
        "scenarios": ["CARD", "TRANSFER"],
        "condition": {
            "and": [
                {"field": "device_age_days", "op": "<", "value": 7},
                {"field": "amount", "op": ">", "value": 30000},
            ]
        },
        "risk_level": "高",
        "risk_score": 75,
        "decision": "人工审核",
        "priority": 85,
        "description": "设备首次出现不足 7 天，且单笔金额超过 3 万元。",
        "version": "1.0.0",
    },
    {
        "rule_id": "R008",
        "rule_name": "多卡归集",
        "scenarios": ["TRANSFER"],
        "condition": {"field": "distinct_from_cards_1h", "op": ">=", "value": 3},
        "risk_level": "极高",
        "risk_score": 100,
        "decision": "拒绝",
        "priority": 100,
        "description": "一小时内至少 3 张不同银行卡向同一收款卡转账。",
        "version": "1.0.0",
    },
    {
        "rule_id": "R012",
        "rule_name": "信贷申请突击",
        "scenarios": ["LOAN"],
        "condition": {"field": "loan_institution_count_month", "op": ">=", "value": 3},
        "risk_level": "高",
        "risk_score": 75,
        "decision": "人工审核",
        "priority": 85,
        "description": "当月向至少 3 家不同机构提交贷款申请。",
        "version": "1.0.0",
    },
    {
        "rule_id": "R018",
        "rule_name": "设备多人共用",
        "scenarios": ["CARD", "LOAN", "TRANSFER", "LOGIN"],
        "condition": {"field": "device_user_count", "op": ">=", "value": 5},
        "risk_level": "中",
        "risk_score": 40,
        "decision": "标记",
        "priority": 50,
        "description": "同一设备指纹关联至少 5 个不同用户。",
        "version": "1.0.0",
    },
    {
        "rule_id": "R025",
        "rule_name": "IP 代理或秒拨",
        "scenarios": ["LOGIN"],
        "condition": {
            "or": [
                {"field": "is_proxy", "op": "==", "value": True},
                {"field": "is_tor", "op": "==", "value": True},
            ]
        },
        "risk_level": "中",
        "risk_score": 40,
        "decision": "标记",
        "priority": 55,
        "description": "登录 IP 命中代理、秒拨或 Tor 出口情报。",
        "version": "1.0.0",
    },
    {
        "rule_id": "R030",
        "rule_name": "黑卡拦截",
        "scenarios": ["TRANSFER"],
        "condition": {"field": "beneficiary_blacklisted", "op": "==", "value": True},
        "risk_level": "极高",
        "risk_score": 100,
        "decision": "拒绝",
        "priority": 110,
        "description": "收款卡号或其哈希命中有效银行卡黑名单。",
        "version": "1.0.0",
    },
)


DEMO_EVENTS: tuple[dict[str, str], ...] = (
    {"rule_id": "SAFE", "scenario": "TRANSFER", "source_id": "TXN_SAFE", "user_id": "U_SAFE"},
    {"rule_id": "R001", "scenario": "TRANSFER", "source_id": "TXN_R001", "user_id": "U_R001"},
    {"rule_id": "R002", "scenario": "CARD", "source_id": "TXN_R002_3", "user_id": "U_R002"},
    {"rule_id": "R005", "scenario": "TRANSFER", "source_id": "TXN_R005", "user_id": "U_R005"},
    {"rule_id": "R008", "scenario": "TRANSFER", "source_id": "TXN_R008_3", "user_id": "U_R008_C"},
    {"rule_id": "R012", "scenario": "LOAN", "source_id": "LOAN_R012_3", "user_id": "U_R012"},
    {"rule_id": "R018", "scenario": "LOGIN", "source_id": "LOGIN_R018", "user_id": "U_SHARED_1"},
    {"rule_id": "R025", "scenario": "LOGIN", "source_id": "LOGIN_R025", "user_id": "U_R025"},
    {"rule_id": "R030", "scenario": "TRANSFER", "source_id": "TXN_R030", "user_id": "U_R030"},
)

