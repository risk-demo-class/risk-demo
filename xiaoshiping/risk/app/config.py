"""制造业风控项目配置与业务事件枚举。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class BusinessEventType(StrEnum):
    SUPPLIER_QUALIFICATION_EXPIRED = "supplier_qualification_expired"
    PURCHASE_ORDER_CREATED = "purchase_order_created"
    MATERIAL_RECEIVED = "material_received"
    IQC_COMPLETED = "iqc_completed"
    MATERIAL_ISSUED = "material_issued"
    PRODUCTION_REPORTED = "production_reported"
    PROCESS_PARAMETER_OUT_OF_LIMIT = "process_parameter_out_of_limit"
    FINISHED_GOODS_PUTAWAY = "finished_goods_putaway"
    SHIPMENT_RELEASED = "shipment_released"
    CUSTOMER_COMPLAINT_CREATED = "customer_complaint_created"
    MAINTENANCE_DUE = "maintenance_due"
    SAFETY_PERMIT_MISSING = "safety_permit_missing"


BLACKLIST_TYPES = frozenset({
    "SUPPLIER", "MATERIAL_LOT", "WORK_ORDER", "EQUIPMENT", "CUSTOMER", "EMPLOYEE",
})


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("MFG_DB_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("MFG_DB_PORT", "9999"))
    db_user: str = os.getenv("MFG_DB_USER", "root")
    db_password: str = os.getenv("MFG_DB_PASSWORD", "123456")
    db_name: str = os.getenv("MFG_DB_NAME", "manufacturing_risk")
    risk_blacklist_types: frozenset[str] = BLACKLIST_TYPES
    business_event_types: tuple[str, ...] = tuple(item.value for item in BusinessEventType)


settings = Settings()
