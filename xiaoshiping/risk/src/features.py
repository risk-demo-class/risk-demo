"""制造业工单风险特征定义。"""
from __future__ import annotations

FEATURE_COLUMNS = [
    "supplier_risk_level", "supplier_qualification_days", "iqc_defect_rate",
    "inventory_hold_flag", "material_critical_flag", "issue_over_bom_ratio",
    "work_order_progress_ratio", "scrap_rate", "process_parameter_deviation",
    "equipment_maintenance_overdue_days", "equipment_calibration_overdue_days",
    "equipment_alarm_flag", "quality_hold_flag", "shipment_release_gap_flag",
    "customer_complaint_count_30d", "complaint_claim_amount",
]
