"""教育业务名称与老师风控核心枚举之间的兼容映射。"""

EDUCATION_TO_CORE_EVENT = {
    "课程报名": "下单",
    "退费申请": "售后申请",
    "直播打赏": "支付",
    "学习行为": "物流投诉",
}
CORE_TO_EDUCATION_EVENT = {
    value: key for key, value in EDUCATION_TO_CORE_EVENT.items()
}

EDUCATION_TO_CORE_CATEGORY = {
    "报名异常": "订单欺诈",
    "退费滥用": "售后滥用",
    "账号风险": "账户风险",
    "学习异常": "物流风险",
    "打赏风险": "支付风险",
    "设备风险": "地址风险",
}
CORE_TO_EDUCATION_CATEGORY = {
    value: key for key, value in EDUCATION_TO_CORE_CATEGORY.items()
}


def to_core_event(value: str | None) -> str | None:
    return EDUCATION_TO_CORE_EVENT.get(value, value)


def to_education_event(value: str | None) -> str | None:
    return CORE_TO_EDUCATION_EVENT.get(value, value)


def to_core_category(value: str | None) -> str | None:
    return EDUCATION_TO_CORE_CATEGORY.get(value, value)


def to_education_category(value: str | None) -> str | None:
    return CORE_TO_EDUCATION_CATEGORY.get(value, value)
