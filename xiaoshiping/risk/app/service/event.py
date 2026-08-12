"""制造业风险检查完整链路：特征 → 规则 → XGBoost → 评估历史 → 风险事件/案件。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pymysql
import xgboost as xgb

from app.config import BusinessEventType, settings
from app.engine.feature import compute_all_features
from app.engine.rule import RuleHit, evaluate_rules, rule_decision, rule_score
from src.features import FEATURE_COLUMNS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = PROJECT_ROOT / "models" / "manufacturing_xgb_model.json"
_MODEL: xgb.Booster | None = None


def _identifier(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:17]}"


def _connection() -> pymysql.connections.Connection:
    return pymysql.connect(host=settings.db_host, port=settings.db_port, user=settings.db_user, password=settings.db_password, database=settings.db_name, charset="utf8mb4", autocommit=True)


def _model_score(features: dict[str, float]) -> float | None:
    global _MODEL
    if _MODEL is None and MODEL_PATH.exists():
        _MODEL = xgb.Booster(); _MODEL.load_model(MODEL_PATH)
    if _MODEL is None:
        return None
    matrix = xgb.DMatrix(np.asarray([[features[name] for name in FEATURE_COLUMNS]], dtype=np.float32), feature_names=FEATURE_COLUMNS)
    return round(float(_MODEL.predict(matrix)[0]) * 100, 4)


def _decision(score: int, hits: list[RuleHit]) -> str:
    hard = rule_decision(hits)
    if hard:
        return hard
    return "REJECT" if score >= 90 else "HOLD" if score >= 80 else "REVIEW" if score >= 60 else "WARN" if score >= 30 else "ALLOW"


def run_risk_check(work_order_id: str) -> dict:
    features = compute_all_features(work_order_id)
    hits = evaluate_rules(features)
    current_rule_score = rule_score(hits)
    ml_score = _model_score(features)
    final_score = max(current_rule_score, round(ml_score or 0))
    decision = _decision(final_score, hits)
    now = datetime.now(); event_id = _identifier("EVT"); assessment_id = _identifier("ASM"); case_id = None
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO business_event (event_id,event_type,entity_type,entity_id,source_system,operator_id,business_at,trace_id,payload_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (event_id, BusinessEventType.PRODUCTION_REPORTED.value, "work_order", work_order_id, "RISK_ENGINE", "E003", now, f"TRACE-{event_id}", json.dumps({"trigger":"run_risk_check"})))
            cursor.execute("INSERT INTO risk_assessment (assessment_id,event_id,source_type,source_id,rule_score,ml_score,final_score,decision,rule_hit_count,feature_json,hit_rule_json,create_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (assessment_id,event_id,"work_order",work_order_id,current_rule_score,ml_score,final_score,decision,len(hits),json.dumps(features),json.dumps([hit.to_dict() for hit in hits],ensure_ascii=False),now))
            for hit in hits:
                cursor.execute("INSERT INTO risk_event (risk_event_id,event_id,entity_type,entity_id,rule_id,risk_category,risk_score,decision,event_at,handled_status,reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (_identifier("RCE"),event_id,"work_order",work_order_id,hit.rule_id,hit.category,hit.score,hit.action,now,"OPEN",hit.reason))
            if decision in {"REJECT","HOLD","ESCALATE","REVIEW"}:
                case_id = _identifier("CASE")
                summary = "; ".join(hit.reason for hit in hits[:3]) or f"模型风险分 {ml_score or 0:.1f}"
                level = "CRITICAL" if decision == "REJECT" else "HIGH" if decision in {"HOLD","ESCALATE"} else "MEDIUM"
                cursor.execute("INSERT INTO risk_case (case_id,assessment_id,source_type,source_id,risk_level,status,owner_team,summary,create_time,update_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (case_id,assessment_id,"work_order",work_order_id,level,"PENDING","质量与生产联合组",summary[:255],now,now))
    return {"assessment_id":assessment_id,"case_id":case_id,"event_id":event_id,"source_id":work_order_id,"rule_score":current_rule_score,"ml_score":ml_score,"final_score":final_score,"decision":decision,"rule_hits":[hit.to_dict() for hit in hits],"features":features}


def _resolve_work_order_id(event_type: str, source_id: str) -> str:
    """将制造现场不同业务单据归并为可评分的生产工单。"""
    resolution_sql = {
        BusinessEventType.MATERIAL_ISSUED.value: "SELECT work_order_id FROM material_issue WHERE issue_id = %s",
        BusinessEventType.PROCESS_PARAMETER_OUT_OF_LIMIT.value: "SELECT work_order_id FROM ipqc_inspection WHERE ipqc_id = %s",
        BusinessEventType.FINISHED_GOODS_PUTAWAY.value: "SELECT work_order_id FROM finished_goods WHERE completion_id = %s",
        BusinessEventType.SHIPMENT_RELEASED.value: "SELECT wo.work_order_id FROM shipment sh JOIN work_order wo ON wo.sales_order_id = sh.sales_order_id WHERE sh.shipment_id = %s",
        BusinessEventType.IQC_COMPLETED.value: "SELECT wo.work_order_id FROM iqc_inspection iq JOIN receipt rc ON rc.receipt_id = iq.receipt_id JOIN work_order wo ON rc.purchase_order_id = CONCAT('PO', LPAD(CAST(SUBSTRING(wo.work_order_id, 3) AS UNSIGNED), 4, '0')) WHERE iq.iqc_id = %s",
        BusinessEventType.MATERIAL_RECEIVED.value: "SELECT wo.work_order_id FROM receipt rc JOIN work_order wo ON rc.purchase_order_id = CONCAT('PO', LPAD(CAST(SUBSTRING(wo.work_order_id, 3) AS UNSIGNED), 4, '0')) WHERE rc.receipt_id = %s",
        BusinessEventType.CUSTOMER_COMPLAINT_CREATED.value: "SELECT wo.work_order_id FROM customer_complaint cc JOIN shipment sh ON sh.shipment_id = cc.shipment_id JOIN work_order wo ON wo.sales_order_id = sh.sales_order_id WHERE cc.complaint_id = %s",
        BusinessEventType.MAINTENANCE_DUE.value: "SELECT work_order_id FROM ipqc_inspection WHERE equipment_id = %s ORDER BY inspected_at DESC LIMIT 1",
        BusinessEventType.PURCHASE_ORDER_CREATED.value: "SELECT wo.work_order_id FROM work_order wo WHERE CONCAT('PO', LPAD(CAST(SUBSTRING(wo.work_order_id, 3) AS UNSIGNED), 4, '0')) = %s LIMIT 1",
        BusinessEventType.SUPPLIER_QUALIFICATION_EXPIRED.value: "SELECT wo.work_order_id FROM work_order wo JOIN purchase_order po ON po.purchase_order_id = CONCAT('PO', LPAD(CAST(SUBSTRING(wo.work_order_id, 3) AS UNSIGNED), 4, '0')) WHERE po.supplier_id = %s ORDER BY wo.planned_end_at DESC LIMIT 1",
    }
    if event_type == BusinessEventType.PRODUCTION_REPORTED.value:
        resolution_sql[event_type] = "SELECT work_order_id FROM work_order WHERE work_order_id = %s"
    query = resolution_sql.get(event_type)
    if not query:
        raise ValueError(f"暂不支持或无法归并工单的风险检查事件：{event_type}")
    with _connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (source_id,))
            row = cursor.fetchone()
    if not row:
        raise ValueError(f"事件 {event_type} 的业务单据 {source_id} 未找到关联工单")
    return str(row[0])


def process_event(event_type: str, source_id: str) -> dict:
    """接收 MES、QMS、WMS、ERP、EAM 事件并调用统一工单风险检查。"""
    return run_risk_check(_resolve_work_order_id(event_type, source_id))