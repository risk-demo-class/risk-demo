"""把已持久化的风控证据翻译成制造业解释，不重新计算风险结论。"""

from __future__ import annotations

from typing import Any

from app.industry_mapping import EVENT_MAPPINGS


FEATURE_DISPLAY_NAMES = {
    "user_total_orders": "经销商历史采购次数",
    "user_orders_30d": "经销商近30天采购次数",
    "user_orders_7d": "经销商近7天采购次数",
    "user_total_amount": "经销商历史采购总金额",
    "user_avg_order_amount": "经销商平均采购金额",
    "user_max_order_amount": "经销商最大采购金额",
    "user_refund_count": "高金额保修申请数量",
    "user_postsale_count": "保修申请总数",
    "user_refund_rate": "高金额保修占比",
    "user_postsale_rate": "设备保修申请率",
    "user_refund_amount": "历史保修申请总金额",
    "user_cancel_count": "经销商合作天数",
    "user_complaint_count": "经销商串货报告数量",
    "user_address_count": "经销商活跃区域数量",
    "order_total_amount": "当前采购或保修金额",
    "order_item_count": "当前业务对象数量槽位",
    "order_sku_count": "采购设备数或设备历史异常次数",
    "order_discount_amount": "当前金额偏离或区域异常值",
    "order_discount_rate": "当前金额异常率或区域异常标识",
    "order_pay_interval_sec": "付款账期或设备年龄（秒）",
    "order_is_night": "是否夜间发起",
    "order_category_count": "设备型号、材料或区域类别数量",
    "addr_total_count": "历史区域触点数量",
    "addr_province_count": "历史异常区域数量",
    "addr_is_new": "当前区域是否异常",
}


def explain_persisted_evidence(evidence: dict[str, Any]) -> str:
    """生成可审计解释；所有分数、动作和规则均直接取自持久化证据。"""
    internal_type = evidence.get("event_type_internal_code")
    mapping = EVENT_MAPPINGS.get(internal_type)
    display_type = mapping.display_name if mapping else (internal_type or "未知事件")
    rules = evidence.get("triggered_rules") or []
    features = evidence.get("features") or []
    feature_values = {
        item.get("name"): item.get("value")
        for item in features if item.get("name") in FEATURE_DISPLAY_NAMES
    }

    def collect_condition_fields(condition: Any) -> list[str]:
        if not isinstance(condition, dict):
            return []
        fields = [condition["field"]] if condition.get("field") else []
        for key in ("and", "or"):
            for child in condition.get(key, []) or []:
                fields.extend(collect_condition_fields(child))
        return fields

    referenced_fields: list[str] = []
    for rule in rules:
        for field in collect_condition_fields(rule.get("condition")):
            if field in feature_values and field not in referenced_fields:
                referenced_fields.append(field)
    if not referenced_fields:
        priority = (
            "addr_is_new", "order_total_amount", "user_orders_7d",
            "user_postsale_count", "user_refund_amount", "user_complaint_count",
        )
        referenced_fields = [name for name in priority if name in feature_values][:4]

    rule_text = "、".join(
        f"{rule.get('rule_id', '?')} {rule.get('rule_name', '')}".strip()
        for rule in rules
    ) or "未命中 JSON 风控规则"
    feature_text = "；".join(
        f"{FEATURE_DISPLAY_NAMES[name]}（{name}）={feature_values[name]}"
        for name in referenced_fields
    ) or "未找到可展示的关键特征"
    ml_score = evidence.get("ml_score")
    ml_text = "未记录" if ml_score is None else f"{float(ml_score):.4f}"

    return (
        f"结论：{display_type}的真实评估动作为“{evidence.get('decision')}”，"
        f"风险等级“{evidence.get('risk_level')}”，最终分 {evidence.get('final_score')}。"
        f"证据：命中规则 {rule_text}；XGBoost 拒绝概率 ml_score={ml_text}；"
        f"关键制造业特征：{feature_text}。"
    )
