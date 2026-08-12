"""制造业风控特征工程：供应链、生产质量、设备交付三大特征族。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.config import settings
from src.features import FEATURE_COLUMNS

AS_OF_DATE = date(2026, 8, 12)


def _fetch_one(work_order_id: str) -> dict[str, Any]:
    import pymysql

    connection = pymysql.connect(
        host=settings.db_host, port=settings.db_port, user=settings.db_user,
        password=settings.db_password, database=settings.db_name, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT
              CASE s.risk_level WHEN 'LOW' THEN 0 WHEN 'MEDIUM' THEN 0.5 ELSE 1 END supplier_risk_level,
              DATEDIFF(s.qualification_expire_at, %s) supplier_qualification_days,
              COALESCE(iqc.defect_qty / NULLIF(iqc.sample_qty, 0), 0) iqc_defect_rate,
              CASE WHEN inv.quality_status IN ('HOLD','FAILED') THEN 1 ELSE 0 END inventory_hold_flag,
              raw.is_critical material_critical_flag,
              mi.issue_qty / NULLIF(wo.planned_qty * 0.25, 0) issue_over_bom_ratio,
              wo.completed_qty / NULLIF(wo.planned_qty, 0) work_order_progress_ratio,
              opr.scrap_qty / NULLIF(opr.good_qty + opr.scrap_qty, 0) scrap_rate,
              ABS(ip.measured_value - ((ip.lsl + ip.usl) / 2)) / NULLIF((ip.usl - ip.lsl) / 2, 0) process_parameter_deviation,
              GREATEST(DATEDIFF(%s, eq.maintenance_due_at), 0) equipment_maintenance_overdue_days,
              GREATEST(DATEDIFF(%s, eq.calibration_due_at), 0) equipment_calibration_overdue_days,
              CASE WHEN eq.status IN ('ALARM','STOPPED') THEN 1 ELSE 0 END equipment_alarm_flag,
              CASE WHEN fg.quality_status IN ('HOLD','FAILED') THEN 1 ELSE 0 END quality_hold_flag,
              CASE WHEN sh.quality_status <> 'PASSED' OR sh.released_by IS NULL THEN 1 ELSE 0 END shipment_release_gap_flag,
              COALESCE(cc.complaint_count, 0) customer_complaint_count_30d,
              COALESCE(cc.claim_amount, 0) complaint_claim_amount
            FROM work_order wo
            JOIN sales_order so ON so.sales_order_id = wo.sales_order_id
            JOIN purchase_order po ON po.purchase_order_id = CONCAT('PO', LPAD(CAST(SUBSTRING(wo.work_order_id, 3) AS UNSIGNED), 4, '0'))
            JOIN supplier s ON s.supplier_id = po.supplier_id
            JOIN material raw ON raw.material_id = po.material_id
            JOIN material_issue mi ON mi.work_order_id = wo.work_order_id
            JOIN inventory inv ON inv.lot_no = mi.lot_no
            JOIN receipt rc ON rc.purchase_order_id = po.purchase_order_id
            JOIN iqc_inspection iqc ON iqc.receipt_id = rc.receipt_id
            JOIN operation_report opr ON opr.work_order_id = wo.work_order_id
            JOIN ipqc_inspection ip ON ip.work_order_id = wo.work_order_id
            JOIN equipment eq ON eq.equipment_id = ip.equipment_id
            JOIN finished_goods fg ON fg.work_order_id = wo.work_order_id
            JOIN shipment sh ON sh.sales_order_id = so.sales_order_id
            LEFT JOIN (SELECT shipment_id, COUNT(*) complaint_count, SUM(claim_amount) claim_amount FROM customer_complaint GROUP BY shipment_id) cc ON cc.shipment_id = sh.shipment_id
            WHERE wo.work_order_id = %s LIMIT 1""", (AS_OF_DATE, AS_OF_DATE, AS_OF_DATE, work_order_id))
            row = cursor.fetchone()
    finally:
        connection.close()
    if not row:
        raise ValueError(f"工单不存在或缺少关联业务数据：{work_order_id}")
    return {name: float(row.get(name) or 0) for name in FEATURE_COLUMNS}


def _family_features(feature_row: dict[str, float], names: tuple[str, ...] | list[str]) -> dict[str, float]:
    return {name: feature_row[name] for name in names}


def compute_supplier_features(work_order_id: str, feature_row: dict[str, float] | None = None) -> dict[str, float]:
    """供应链/来料特征：供应商准入、IQC、批次库存、关键物料。"""
    row = feature_row or _fetch_one(work_order_id)
    return _family_features(row, FEATURE_COLUMNS[:5])


def compute_production_quality_features(work_order_id: str, feature_row: dict[str, float] | None = None) -> dict[str, float]:
    """生产质量特征：领料偏离、工单进度、报废、参数、成品冻结。"""
    row = feature_row or _fetch_one(work_order_id)
    return _family_features(row, FEATURE_COLUMNS[5:9] + ["quality_hold_flag"])


def compute_equipment_delivery_features(work_order_id: str, feature_row: dict[str, float] | None = None) -> dict[str, float]:
    """设备/交付特征：维护校准、报警、放行、客诉和索赔。"""
    row = feature_row or _fetch_one(work_order_id)
    return _family_features(row, FEATURE_COLUMNS[9:12] + FEATURE_COLUMNS[13:])


def compute_all_features(work_order_id: str) -> dict[str, float]:
    """汇总三大特征族，严格按训练特征列返回且只读取一次数据库。"""
    row = _fetch_one(work_order_id)
    features = {}
    features.update(compute_supplier_features(work_order_id, row))
    features.update(compute_production_quality_features(work_order_id, row))
    features.update(compute_equipment_delivery_features(work_order_id, row))
    return {name: float(features.get(name, 0.0)) for name in FEATURE_COLUMNS}