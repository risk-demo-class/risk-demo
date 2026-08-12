"""制造业业务事件校验派发表。

每个校验器只处理一个业务事件，返回风险原因列表；空列表表示可继续执行。
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from app.config import BusinessEventType

ValidationResult = list[str]
Validator = Callable[[dict[str, Any]], ValidationResult]


def validate_supplier_qualification(payload: dict[str, Any]) -> ValidationResult:
    expire_at = payload.get("qualification_expire_at")
    status = payload.get("qualification_status")
    if status != "VALID":
        return ["供应商资质状态不是 VALID"]
    if expire_at and date.fromisoformat(str(expire_at)) < date.today():
        return ["供应商资质已过期"]
    return []


def validate_material_issue(payload: dict[str, Any]) -> ValidationResult:
    reasons: ValidationResult = []
    if payload.get("quality_status") not in {"PASSED", "CONCESSION"}:
        reasons.append("物料尚未通过 IQC 或仍处于冻结状态")
    planned_qty = float(payload.get("planned_qty") or 0)
    issue_qty = float(payload.get("issue_qty") or 0)
    allowed_ratio = float(payload.get("allowed_issue_ratio") or 1.10)
    if planned_qty and issue_qty > planned_qty * allowed_ratio:
        reasons.append("领料数量超过计划/BOM 容差")
    return reasons


def validate_process_parameter(payload: dict[str, Any]) -> ValidationResult:
    measured = float(payload.get("measured_value") or 0)
    lsl = float(payload.get("lsl") or 0)
    usl = float(payload.get("usl") or 0)
    if measured < lsl or measured > usl:
        return ["关键过程参数超出规格上下限"]
    return []


def validate_shipment_release(payload: dict[str, Any]) -> ValidationResult:
    reasons: ValidationResult = []
    if payload.get("quality_status") != "PASSED":
        reasons.append("成品质量状态不是 PASSED")
    if not payload.get("released_by"):
        reasons.append("发运缺少质量放行人")
    return reasons


def validate_maintenance(payload: dict[str, Any]) -> ValidationResult:
    reasons: ValidationResult = []
    if payload.get("loto_required") and not payload.get("loto_completed"):
        reasons.append("需要 LOTO 的维护作业未完成能量隔离")
    if payload.get("acceptance_status") != "ACCEPTED":
        reasons.append("维修工单未完成验收")
    return reasons


VALIDATOR_DISPATCH: dict[str, Validator] = {
    BusinessEventType.SUPPLIER_QUALIFICATION_EXPIRED.value: validate_supplier_qualification,
    BusinessEventType.MATERIAL_ISSUED.value: validate_material_issue,
    BusinessEventType.PROCESS_PARAMETER_OUT_OF_LIMIT.value: validate_process_parameter,
    BusinessEventType.SHIPMENT_RELEASED.value: validate_shipment_release,
    BusinessEventType.MAINTENANCE_DUE.value: validate_maintenance,
    BusinessEventType.SAFETY_PERMIT_MISSING.value: validate_maintenance,
}


def validate_event(event_type: str, payload: dict[str, Any]) -> ValidationResult:
    """按事件类型派发校验器；未配置校验器的事件默认通过。"""
    validator = VALIDATOR_DISPATCH.get(event_type)
    return validator(payload) if validator else []
