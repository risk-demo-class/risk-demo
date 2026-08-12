"""制造业风控项目的 MySQL 查询和写入封装。"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import pymysql

from app.config import settings


@contextmanager
def connection() -> Iterator[pymysql.connections.Connection]:
    database = pymysql.connect(host=settings.db_host, port=settings.db_port, user=settings.db_user, password=settings.db_password, database=settings.db_name, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, autocommit=True)
    try:
        yield database
    finally:
        database.close()


def fetch_all(sql: str, params: tuple | None = None) -> list[dict]:
    with connection() as database:
        with database.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())


def fetch_one(sql: str, params: tuple | None = None) -> dict | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple) -> int:
    with connection() as database:
        with database.cursor() as cursor:
            return cursor.execute(sql, params)


def dashboard_summary() -> dict:
    return fetch_one("""SELECT
      (SELECT COUNT(*) FROM risk_event WHERE handled_status = 'OPEN') AS open_events,
      (SELECT COUNT(*) FROM risk_event WHERE decision IN ('HOLD','REJECT','ESCALATE')) AS critical_events,
      (SELECT COUNT(*) FROM supplier WHERE qualification_expire_at < %s OR qualification_status <> 'VALID') AS supplier_attention,
      (SELECT COUNT(*) FROM equipment WHERE maintenance_due_at < %s OR calibration_due_at < %s OR status IN ('ALARM','STOPPED')) AS equipment_attention,
      (SELECT COUNT(*) FROM work_order WHERE status IN ('HOLD','IN_PROGRESS')) AS active_work_orders,
      (SELECT COUNT(*) FROM shipment WHERE quality_status <> 'PASSED' OR released_by IS NULL) AS blocked_shipments""", (date(2026, 8, 12),) * 3) or {}


def risk_events(status: str | None = None, decision: str | None = None, limit: int = 100) -> list[dict]:
    filters, params = [], []
    if status:
        filters.append("re.handled_status = %s"); params.append(status)
    if decision:
        filters.append("re.decision = %s"); params.append(decision)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(limit)
    return fetch_all(f"""SELECT re.risk_event_id, re.entity_type, re.entity_id, re.risk_category, re.risk_score, re.decision, re.event_at, re.handled_status, re.reason, rr.rule_id, rr.rule_name, rr.event_type
      FROM risk_event re LEFT JOIN risk_rule rr ON rr.rule_id = re.rule_id {where}
      ORDER BY re.risk_score DESC, re.event_at DESC LIMIT %s""", tuple(params))


def rules() -> list[dict]:
    return fetch_all("SELECT * FROM risk_rule ORDER BY score DESC, rule_id")


def work_orders() -> list[dict]:
    return fetch_all("""SELECT wo.work_order_id, wo.planned_qty, wo.completed_qty, wo.status, wo.planned_end_at, m.material_name, p.plant_name, p.workshop_name,
      COALESCE(fg.quality_status, 'PENDING') AS quality_status, COALESCE(MAX(ip.result), 'PENDING') AS ipqc_status,
      COALESCE(MAX(eq.status), 'UNKNOWN') AS equipment_status, COALESCE(MAX(sh.quality_status), 'PENDING') AS shipment_status
      FROM work_order wo JOIN material m ON m.material_id = wo.material_id JOIN plant p ON p.plant_id = wo.plant_id
      LEFT JOIN finished_goods fg ON fg.work_order_id = wo.work_order_id LEFT JOIN ipqc_inspection ip ON ip.work_order_id = wo.work_order_id
      LEFT JOIN equipment eq ON eq.equipment_id = ip.equipment_id LEFT JOIN shipment sh ON sh.sales_order_id = wo.sales_order_id
      GROUP BY wo.work_order_id, wo.planned_qty, wo.completed_qty, wo.status, wo.planned_end_at, m.material_name, p.plant_name, p.workshop_name, fg.quality_status
      ORDER BY FIELD(wo.status, 'HOLD', 'IN_PROGRESS', 'PLANNED', 'COMPLETED'), wo.planned_end_at LIMIT 120""")


def update_risk_event_status(risk_event_id: str, handled_status: str) -> bool:
    return execute("UPDATE risk_event SET handled_status = %s WHERE risk_event_id = %s", (handled_status, risk_event_id)) == 1


def assessment_history(limit: int = 100) -> list[dict]:
    return fetch_all("""SELECT assessment_id, source_id, rule_score, ml_score, final_score, decision,
      rule_hit_count, create_time, hit_rule_json FROM risk_assessment ORDER BY create_time DESC LIMIT %s""", (limit,))


def risk_cases(limit: int = 100) -> list[dict]:
    return fetch_all("""SELECT case_id, assessment_id, source_id, risk_level, status, owner_team,
      summary, create_time, update_time FROM risk_case ORDER BY create_time DESC LIMIT %s""", (limit,))


def update_case_status(case_id: str, status: str) -> bool:
    return execute("UPDATE risk_case SET status = %s, update_time = NOW() WHERE case_id = %s", (status, case_id)) == 1

BUSINESS_ENTITY_CONFIG: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "supplier": ("supplier", "supplier_id", ("qualification_status", "qualification_expire_at", "risk_level")),
    "equipment": ("equipment", "equipment_id", ("status", "maintenance_due_at", "calibration_due_at")),
    "work_order": ("work_order", "work_order_id", ("planned_qty", "completed_qty", "status")),
    "ipqc_inspection": ("ipqc_inspection", "ipqc_id", ("measured_value", "result")),
    "shipment": ("shipment", "shipment_id", ("quality_status", "released_by")),
}


def business_data() -> dict[str, list[dict]]:
    """返回数据管理页需要的可编辑业务数据。"""
    return {
        "supplier": fetch_all("SELECT supplier_id, supplier_name, supplier_level, qualification_status, qualification_expire_at, risk_level FROM supplier ORDER BY supplier_id"),
        "equipment": fetch_all("SELECT equipment_id, equipment_name, equipment_type, criticality, status, maintenance_due_at, calibration_due_at FROM equipment ORDER BY equipment_id"),
        "work_order": fetch_all("SELECT wo.work_order_id, wo.planned_qty, wo.completed_qty, wo.status, wo.planned_end_at, m.material_name FROM work_order wo JOIN material m ON m.material_id = wo.material_id ORDER BY wo.work_order_id"),
        "ipqc_inspection": fetch_all("SELECT ip.ipqc_id, ip.work_order_id, ip.measured_value, ip.lsl, ip.usl, ip.result, ip.equipment_id, ip.inspected_at FROM ipqc_inspection ip ORDER BY ip.ipqc_id"),
        "shipment": fetch_all("SELECT shipment_id, sales_order_id, quality_status, released_by, ship_qty, ship_at FROM shipment ORDER BY shipment_id"),
    }


def update_business_record(entity: str, record_id: str, changes: dict[str, object]) -> bool:
    """按实体白名单更新可演示的业务字段。"""
    config = BUSINESS_ENTITY_CONFIG.get(entity)
    if not config:
        raise ValueError(f"不支持维护的业务实体：{entity}")
    table_name, key_name, allowed_fields = config
    safe_changes = {field: value for field, value in changes.items() if field in allowed_fields}
    if not safe_changes:
        raise ValueError("未提供可更新的字段")
    if not fetch_one(f"SELECT {key_name} FROM {table_name} WHERE {key_name} = %s", (record_id,)):
        return False
    assignments = ", ".join(f"{field} = %s" for field in safe_changes)
    execute(f"UPDATE {table_name} SET {assignments} WHERE {key_name} = %s", tuple(safe_changes.values()) + (record_id,))
    return True


def affected_work_orders(entity: str, record_id: str) -> list[str]:
    """返回数据修改后需要重新风险检查的关联工单。"""
    query_by_entity = {
        "work_order": ("SELECT work_order_id FROM work_order WHERE work_order_id = %s",),
        "ipqc_inspection": ("SELECT work_order_id FROM ipqc_inspection WHERE ipqc_id = %s",),
        "shipment": ("SELECT wo.work_order_id FROM shipment sh JOIN work_order wo ON wo.sales_order_id = sh.sales_order_id WHERE sh.shipment_id = %s",),
        "supplier": ("SELECT wo.work_order_id FROM purchase_order po JOIN work_order wo ON po.purchase_order_id = CONCAT('PO', LPAD(CAST(SUBSTRING(wo.work_order_id, 3) AS UNSIGNED), 4, '0')) WHERE po.supplier_id = %s ORDER BY wo.work_order_id",),
        "equipment": ("SELECT DISTINCT work_order_id FROM ipqc_inspection WHERE equipment_id = %s ORDER BY work_order_id",),
    }
    queries = query_by_entity.get(entity)
    if not queries:
        return []
    rows = fetch_all(queries[0], (record_id,))
    return [str(row["work_order_id"]) for row in rows]