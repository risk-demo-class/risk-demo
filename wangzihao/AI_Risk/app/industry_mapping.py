"""制造业展示语义与核心风控兼容码的唯一映射来源。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndustryEventMapping:
    """一个内部事件码对应的制造业业务来源和上下文字段。"""

    internal_event_type: str
    display_name: str
    source_entity: str
    source_table: str
    source_id_field: str
    event_data_id_field: str


EVENT_MAPPINGS: dict[str, IndustryEventMapping] = {
    "下单": IndustryEventMapping(
        internal_event_type="下单",
        display_name="经销商采购提交",
        source_entity="purchase_order",
        source_table="purchase_order",
        source_id_field="po_id",
        event_data_id_field="purchase_order_id",
    ),
    "支付": IndustryEventMapping(
        internal_event_type="支付",
        display_name="采购付款",
        source_entity="purchase_order",
        source_table="purchase_order",
        source_id_field="po_id",
        event_data_id_field="purchase_order_id",
    ),
    "售后申请": IndustryEventMapping(
        internal_event_type="售后申请",
        display_name="设备保修申请",
        source_entity="warranty_claim",
        source_table="warranty_claim",
        source_id_field="claim_id",
        event_data_id_field="warranty_claim_id",
    ),
    "物流投诉": IndustryEventMapping(
        internal_event_type="物流投诉",
        display_name="串货举报",
        source_entity="cross_region_report",
        source_table="cross_region_report",
        source_id_field="report_id",
        event_data_id_field="cross_region_report_id",
    ),
}


EXTERNAL_EVENT_ALIASES: dict[str, str] = {
    "经销商采购提交": "下单",
    "采购付款": "支付",
    "采购确认": "支付",
    "设备保修申请": "售后申请",
    "串货举报": "物流投诉",
    "跨区域检查": "物流投诉",
}


def normalize_event_type(value: object) -> object:
    """把制造业展示名称归一为核心 ENUM 可保存的内部事件码。"""
    if not isinstance(value, str):
        return value
    return EXTERNAL_EVENT_ALIASES.get(value, value)


def get_event_mapping(event_type: str) -> IndustryEventMapping:
    """返回内部事件码对应的制造业来源定义。"""
    try:
        return EVENT_MAPPINGS[event_type]
    except KeyError as exc:
        raise ValueError(f"不支持的事件类型: {event_type}") from exc
