"""P1 医疗风控 REST API。"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_async
from app.engine.ml_model import model_status
from app.engine.feature import FEATURE_COLUMNS
from app.engine.rule_definitions import BLACKLIST_RULE
from app.models_auth import AppUser
from app.models_business import (
    MedicalInsuranceClaim,
    MedicalPatient,
    MedicalPrescription,
    MedicalRegistration,
)
from app.agent.readonly_assistant import answer_question
from app.models_risk import (
    RiskActionLog, RiskAlert, RiskAssessment, RiskBlacklist, RiskCase,
    RiskEvent, RiskFeature, RiskRule, RiskUserProfile,
)
from app.schemas import (
    AgentChatRequest,
    AgentChatResponse,
    AlertResolveRequest,
    BlacklistCreateRequest,
    CaseReviewRequest,
    RiskCheckRequest,
    RiskCheckResponse,
    RuleCreateRequest,
    RuleUpdateRequest,
    CaseAssignRequest,
    CaseReopenRequest,
)
from app.service.event import process_event
from app.service.auth import get_current_user, require_roles


api_router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


def _operator(request: Request) -> str:
    return (request.session.get("username") or "local-user")[:50]


def _ip(request: Request) -> str | None:
    return request.client.host[:50] if request.client else None


@api_router.post("/risk/check", response_model=RiskCheckResponse, tags=["风险检查"])
async def risk_check(
    request: RiskCheckRequest,
    db: AsyncSession = Depends(get_db_async),
    _user: AppUser = Depends(require_roles("admin", "reviewer", "analyst")),
):
    return await process_event(db, request)


@api_router.get("/rules", tags=["规则管理"])
async def list_rules(db: AsyncSession = Depends(get_db_async)):
    rows = (await db.execute(select(RiskRule).where(RiskRule.deleted_at.is_(None)).order_by(RiskRule.rule_id))).scalars().all()
    result = [{
        "rule_id": row.rule_id, "rule_name": row.rule_name,
        "rule_category": row.rule_category, "event_type": row.event_type,
        "condition": row.condition_dict, "risk_level": row.risk_level,
        "risk_score": row.risk_score, "action": row.action,
        "is_enabled": bool(row.is_enabled), "runtime": False,
        "description": row.description or "", "priority": row.priority,
    } for row in rows]
    result.append({
        **BLACKLIST_RULE,
        "event_type": "通用",
        "condition": {"runtime": "有效医疗主体黑名单命中"},
        "is_enabled": True,
        "runtime": True,
    })
    return result


@api_router.post("/rules/{rule_id}/toggle", tags=["规则管理"])
async def toggle_rule(
    rule_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db_async),
    _admin: AppUser = Depends(require_roles("admin")),
):
    rule = await db.get(RiskRule, rule_id)
    if rule is None or rule.deleted_at is not None:
        raise HTTPException(404, "规则不存在")
    before = bool(rule.is_enabled)
    rule.is_enabled = 0 if rule.is_enabled else 1
    db.add(RiskActionLog(
        operator=_operator(request), action_type="TOGGLE_RULE", target_type="rule", target_id=rule_id,
        before_value=json.dumps({"is_enabled": before}, ensure_ascii=False),
        after_value=json.dumps({"is_enabled": bool(rule.is_enabled)}, ensure_ascii=False),
        ip=_ip(request), remark="医疗规则启停",
    ))
    await db.commit()
    return {"rule_id": rule_id, "is_enabled": bool(rule.is_enabled)}


def _validate_rule_condition(condition: dict) -> None:
    if "all" in condition or "any" in condition:
        key = "all" if "all" in condition else "any"
        children = condition.get(key)
        if not isinstance(children, list) or not children:
            raise HTTPException(400, f"条件 {key} 必须是非空数组")
        for child in children:
            if not isinstance(child, dict):
                raise HTTPException(400, "组合条件项必须是对象")
            _validate_rule_condition(child)
        return
    feature = condition.get("feature")
    if feature not in FEATURE_COLUMNS:
        raise HTTPException(400, "规则特征不在允许的 25 维特征中")
    if condition.get("op") not in {">", ">=", "<", "<=", "==", "!=", "in"}:
        raise HTTPException(400, "规则运算符不受支持")
    if "value" not in condition:
        raise HTTPException(400, "规则条件缺少 value")


@api_router.post("/rules", tags=["规则管理"])
async def create_rule(
    data: RuleCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_async),
    _admin: AppUser = Depends(require_roles("admin")),
):
    if data.rule_id == "MR016":
        raise HTTPException(409, "MR016 是保留的运行时黑名单规则")
    existing = await db.get(RiskRule, data.rule_id)
    if existing is not None and existing.deleted_at is None:
        raise HTTPException(409, "规则 ID 已存在")
    _validate_rule_condition(data.condition)
    values = {
        "rule_name": data.rule_name,
        "rule_category": data.rule_category,
        "event_type": data.event_type,
        "rule_condition": json.dumps(data.condition, ensure_ascii=False),
        "risk_level": data.risk_level,
        "risk_score": data.risk_score,
        "action": data.action,
        "is_enabled": 1,
        "priority": data.priority,
        "description": data.description,
        "deleted_at": None,
    }
    if existing is None:
        rule = RiskRule(rule_id=data.rule_id, **values)
        db.add(rule)
    else:
        rule = existing
        for field, value in values.items():
            setattr(rule, field, value)
    db.add(RiskActionLog(
        operator=_operator(request), action_type="CREATE_RULE", target_type="rule", target_id=data.rule_id,
        before_value=None,
        after_value=json.dumps({"rule_name": data.rule_name, "condition": data.condition}, ensure_ascii=False),
        ip=_ip(request), remark="人工新增医疗风控规则",
    ))
    await db.commit()
    return {"rule_id": data.rule_id, "created": existing is None, "restored": existing is not None}


@api_router.put("/rules/{rule_id}", tags=["规则管理"])
async def update_rule(
    rule_id: str,
    data: RuleUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_async),
    _admin: AppUser = Depends(require_roles("admin")),
):
    if rule_id == "MR016":
        raise HTTPException(409, "运行时黑名单规则不能修改")
    rule = await db.get(RiskRule, rule_id)
    if rule is None or rule.deleted_at is not None:
        raise HTTPException(404, "规则不存在")
    _validate_rule_condition(data.condition)
    before = {
        "rule_name": rule.rule_name, "rule_category": rule.rule_category,
        "event_type": rule.event_type, "condition": rule.condition_dict,
        "risk_level": rule.risk_level, "risk_score": rule.risk_score,
        "action": rule.action, "description": rule.description, "priority": rule.priority,
    }
    rule.rule_name = data.rule_name
    rule.rule_category = data.rule_category
    rule.event_type = data.event_type
    rule.rule_condition = json.dumps(data.condition, ensure_ascii=False)
    rule.risk_level = data.risk_level
    rule.risk_score = data.risk_score
    rule.action = data.action
    rule.description = data.description
    rule.priority = data.priority
    after = data.model_dump()
    db.add(RiskActionLog(
        operator=_operator(request), action_type="UPDATE_RULE", target_type="rule", target_id=rule_id,
        before_value=json.dumps(before, ensure_ascii=False),
        after_value=json.dumps(after, ensure_ascii=False),
        ip=_ip(request), remark="人工修改医疗风控规则",
    ))
    await db.commit()
    return {"rule_id": rule_id, "updated": True}


@api_router.delete("/rules/{rule_id}", tags=["规则管理"])
async def delete_rule(
    rule_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db_async),
    _admin: AppUser = Depends(require_roles("admin")),
):
    if rule_id == "MR016":
        raise HTTPException(409, "运行时黑名单规则不能删除")
    rule = await db.get(RiskRule, rule_id)
    if rule is None or rule.deleted_at is not None:
        raise HTTPException(404, "规则不存在")
    rule.deleted_at = datetime.now()
    rule.is_enabled = 0
    db.add(RiskActionLog(
        operator=_operator(request), action_type="DELETE_RULE", target_type="rule", target_id=rule_id,
        before_value=json.dumps({"rule_name": rule.rule_name, "is_enabled": True}, ensure_ascii=False),
        after_value=json.dumps({"deleted": True}, ensure_ascii=False),
        ip=_ip(request), remark="人工软删除医疗风控规则",
    ))
    await db.commit()
    return {"rule_id": rule_id, "deleted": True}


@api_router.get("/cases", tags=["案件管理"])
async def list_cases(
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    query = select(RiskCase)
    if status == "pending":
        query = query.where(RiskCase.case_status.in_(("待审核", "审核中")))
    elif status:
        query = query.where(RiskCase.case_status == status)
    rows = (await db.execute(query.order_by(RiskCase.create_time.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in rows]


@api_router.post("/cases/{case_id}/review", tags=["案件管理"])
async def review_case(
    case_id: str,
    data: CaseReviewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_async),
    _reviewer: AppUser = Depends(require_roles("admin", "reviewer")),
):
    case = await db.get(RiskCase, case_id)
    if case is None:
        raise HTTPException(404, "案件不存在")
    allowed = {
        "待审核": {"审核中", "已通过", "已拒绝", "已关闭"},
        "审核中": {"已通过", "已拒绝", "已关闭"},
    }
    if data.case_status not in allowed.get(case.case_status, set()):
        raise HTTPException(409, f"案件不能从 {case.case_status} 流转到 {data.case_status}")
    before_status = case.case_status
    case.case_status = data.case_status
    case.reviewer = data.reviewer
    case.review_comment = data.review_comment
    case.review_time = datetime.now()
    db.add(RiskActionLog(
        operator=_operator(request), action_type="REVIEW_CASE", target_type="case", target_id=case_id,
        before_value=json.dumps({"case_status": before_status}, ensure_ascii=False),
        after_value=json.dumps({
            "case_status": data.case_status,
            "reviewer": data.reviewer,
            "has_comment": bool(data.review_comment),
        }, ensure_ascii=False),
        ip=_ip(request), remark="人工审核医疗风险案件",
    ))
    await db.commit()
    return {"case_id": case_id, "case_status": case.case_status}


@api_router.post("/cases/{case_id}/assign", tags=["案件管理"])
async def assign_case(
    case_id: str,
    data: CaseAssignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_async),
    _reviewer: AppUser = Depends(require_roles("admin", "reviewer")),
):
    case = await db.get(RiskCase, case_id)
    if case is None:
        raise HTTPException(404, "案件不存在")
    if case.case_status not in ("待审核", "审核中"):
        raise HTTPException(409, "终态案件请先发起重新审核")
    before = {"case_status": case.case_status, "reviewer": case.reviewer}
    case.case_status = "审核中"
    case.reviewer = data.reviewer
    case.review_comment = data.comment
    case.review_time = datetime.now()
    db.add(RiskActionLog(
        operator=_operator(request), action_type="ASSIGN_CASE", target_type="case", target_id=case_id,
        before_value=json.dumps(before, ensure_ascii=False),
        after_value=json.dumps({"case_status": "审核中", "reviewer": data.reviewer}, ensure_ascii=False),
        ip=_ip(request), remark="指定案件人工审核人",
    ))
    await db.commit()
    return {"case_id": case_id, "case_status": case.case_status, "reviewer": case.reviewer}


@api_router.post("/cases/{case_id}/reopen", tags=["案件管理"])
async def reopen_case(
    case_id: str,
    data: CaseReopenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_async),
    _reviewer: AppUser = Depends(require_roles("admin", "reviewer")),
):
    case = await db.get(RiskCase, case_id)
    if case is None:
        raise HTTPException(404, "案件不存在")
    if case.case_status not in ("已通过", "已拒绝", "已关闭"):
        raise HTTPException(409, "只有终态案件可以重新发起审核")
    before_status = case.case_status
    case.case_status = "审核中"
    case.reviewer = data.reviewer
    case.review_comment = f"重新审核原因：{data.reason}"
    case.review_time = datetime.now()
    db.add(RiskActionLog(
        operator=_operator(request), action_type="REOPEN_CASE", target_type="case", target_id=case_id,
        before_value=json.dumps({"case_status": before_status}, ensure_ascii=False),
        after_value=json.dumps({"case_status": "审核中", "reviewer": data.reviewer, "reason": data.reason}, ensure_ascii=False),
        ip=_ip(request), remark="终态案件重新发起人工审核",
    ))
    await db.commit()
    return {"case_id": case_id, "case_status": case.case_status, "reviewer": case.reviewer}


@api_router.get("/assessments", tags=["评估历史"])
async def list_assessments(
    patient_id: str | None = None,
    event_type: str | None = None,
    decision: str | None = None,
    high_risk: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    query = select(RiskAssessment, RiskEvent.event_type).join(
        RiskEvent, RiskEvent.event_id == RiskAssessment.event_id
    )
    if patient_id:
        query = query.where(RiskAssessment.user_id == patient_id)
    if event_type:
        query = query.where(RiskEvent.event_type == event_type)
    if decision:
        query = query.where(RiskAssessment.decision == decision)
    if high_risk:
        query = query.where(RiskAssessment.decision.in_(("人工审核", "拒绝")))
    rows = (await db.execute(query.order_by(RiskAssessment.create_time.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return [{
        "assessment_id": assessment.assessment_id, "event_id": assessment.event_id,
        "patient_id": assessment.user_id, "event_type": row_event_type,
        "final_score": assessment.final_score,
        "risk_level": assessment.risk_level, "decision": assessment.decision,
        "rule_count": assessment.rule_count,
        "ml_score": float(assessment.ml_score) if assessment.ml_score is not None else None,
        "ml_decision": assessment.ml_decision, "create_time": assessment.create_time,
    } for assessment, row_event_type in rows]


@api_router.get("/assessments/{assessment_id}", tags=["评估历史"])
async def assessment_detail(assessment_id: str, db: AsyncSession = Depends(get_db_async)):
    assessment = await db.get(RiskAssessment, assessment_id)
    if assessment is None:
        raise HTTPException(404, "评估不存在")
    event = await db.get(RiskEvent, assessment.event_id)
    feature_rows = list((await db.execute(select(RiskFeature).where(
        RiskFeature.event_id == assessment.event_id
    ).order_by(RiskFeature.feature_name))).scalars().all())
    case = (await db.execute(select(RiskCase).where(
        RiskCase.assessment_id == assessment_id
    ).order_by(RiskCase.create_time.desc()).limit(1))).scalar_one_or_none()
    return {
        "assessment_id": assessment.assessment_id,
        "event_id": assessment.event_id,
        "patient_id": assessment.user_id,
        "event": None if event is None else {
            "event_type": event.event_type,
            "source_id": event.event_source_id,
            "event_data": json.loads(event.event_data or "{}"),
            "create_time": event.create_time,
        },
        "final_score": assessment.final_score,
        "risk_level": assessment.risk_level,
        "decision": assessment.decision,
        "rule_count": assessment.rule_count,
        "triggered_rules": json.loads(assessment.rule_results or "[]"),
        "features": {row.feature_name: float(row.feature_value or 0) for row in feature_rows},
        "ml_score": float(assessment.ml_score) if assessment.ml_score is not None else None,
        "ml_decision": assessment.ml_decision,
        "case": None if case is None else {
            "case_id": case.case_id,
            "case_status": case.case_status,
            "reviewer": case.reviewer,
            "review_comment": case.review_comment,
        },
        "create_time": assessment.create_time,
    }


@api_router.get("/blacklist", tags=["黑名单"])
async def list_blacklist(db: AsyncSession = Depends(get_db_async)):
    rows = (await db.execute(select(RiskBlacklist).where(RiskBlacklist.deleted_at.is_(None)).order_by(RiskBlacklist.create_time.desc()))).scalars().all()
    return [{
        "blacklist_id": row.blacklist_id, "blacklist_type": row.blacklist_type,
        "blacklist_value_masked": row.blacklist_value[:8] + "***",
        "reason": row.reason, "expire_time": row.expire_time,
    } for row in rows]


@api_router.post("/blacklist", tags=["黑名单"])
async def add_blacklist(
    data: BlacklistCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_async),
    _analyst: AppUser = Depends(require_roles("admin", "analyst")),
):
    existing = (await db.execute(select(RiskBlacklist).where(
        RiskBlacklist.blacklist_type == data.blacklist_type,
        RiskBlacklist.blacklist_value == data.blacklist_value,
    ))).scalar_one_or_none()
    if existing:
        existing.deleted_at = None
        existing.reason = data.reason
        existing.expire_time = data.expire_time
        row = existing
    else:
        row = RiskBlacklist(**data.model_dump())
        db.add(row)
    await db.flush()
    masked = data.blacklist_value[:8] + "***"
    db.add(RiskActionLog(
        operator=_operator(request), action_type="ADD_BLACKLIST", target_type="blacklist",
        target_id=str(row.blacklist_id), before_value=None,
        after_value=json.dumps({"blacklist_type": data.blacklist_type, "value_masked": masked}, ensure_ascii=False),
        ip=_ip(request), remark="新增或恢复医疗主体黑名单",
    ))
    await db.commit()
    await db.refresh(row)
    return {"blacklist_id": row.blacklist_id}


@api_router.delete("/blacklist/{blacklist_id}", tags=["黑名单"])
async def remove_blacklist(
    blacklist_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db_async),
    _analyst: AppUser = Depends(require_roles("admin", "analyst")),
):
    row = await db.get(RiskBlacklist, blacklist_id)
    if row is None or row.deleted_at is not None:
        raise HTTPException(404, "黑名单记录不存在")
    row.deleted_at = datetime.now()
    db.add(RiskActionLog(
        operator=_operator(request), action_type="REMOVE_BLACKLIST", target_type="blacklist",
        target_id=str(blacklist_id),
        before_value=json.dumps({"blacklist_type": row.blacklist_type, "active": True}, ensure_ascii=False),
        after_value=json.dumps({"active": False}, ensure_ascii=False),
        ip=_ip(request), remark="软删除医疗主体黑名单",
    ))
    await db.commit()
    return {"removed": True}


@api_router.get("/medical/sources", tags=["医疗数据"])
async def medical_sources(event_type: str, limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db_async)):
    mapping = {
        "挂号申请": (MedicalRegistration, MedicalRegistration.registration_id),
        "挂号退号": (MedicalRegistration, MedicalRegistration.registration_id),
        "处方开立": (MedicalPrescription, MedicalPrescription.prescription_id),
        "医保结算": (MedicalInsuranceClaim, MedicalInsuranceClaim.claim_id),
    }
    if event_type not in mapping:
        raise HTTPException(400, "不支持的医疗事件类型")
    model, id_column = mapping[event_type]
    rows = (await db.execute(select(model).order_by(id_column).limit(limit))).scalars().all()
    return [{"source_id": getattr(row, id_column.key), "patient_id": row.patient_id} for row in rows]


@api_router.get("/medical/patients", tags=["医疗数据"])
async def medical_patients(
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    query = select(MedicalPatient, RiskUserProfile).outerjoin(
        RiskUserProfile, RiskUserProfile.user_id == MedicalPatient.patient_id
    )
    if keyword:
        escaped = keyword.strip().replace("%", "\\%").replace("_", "\\_")
        query = query.where(or_(
            MedicalPatient.patient_id.like(f"%{escaped}%", escape="\\"),
            MedicalPatient.name_masked.like(f"%{escaped}%", escape="\\"),
        ))
    rows = (await db.execute(query.order_by(
        MedicalPatient.patient_id
    ).offset((page - 1) * page_size).limit(page_size))).all()
    return [{
        "patient_id": patient.patient_id,
        "name_masked": patient.name_masked,
        "gender": patient.gender,
        "birth_year": patient.birth_year,
        "insured_province": patient.insured_province,
        "real_name_status": patient.real_name_status,
        "risk_score": profile.risk_score if profile else 0,
        "risk_level": profile.risk_level if profile else "低",
        "assessment_count": profile.assessment_count if profile else 0,
        "last_assessment_time": profile.last_assessment_time if profile else None,
    } for patient, profile in rows]


@api_router.get("/dashboard/overview", tags=["仪表盘"])
async def dashboard_overview(db: AsyncSession = Depends(get_db_async)):
    assessments = (await db.execute(select(func.count()).select_from(RiskAssessment))).scalar_one()
    high_risk = (await db.execute(select(func.count()).select_from(RiskAssessment).where(RiskAssessment.decision.in_(("人工审核", "拒绝"))))).scalar_one()
    pending = (await db.execute(select(func.count()).select_from(RiskCase).where(RiskCase.case_status.in_(("待审核", "审核中"))))).scalar_one()
    patients = (await db.execute(select(func.count()).select_from(MedicalPatient))).scalar_one()
    return {
        "assessment_count": assessments,
        "high_risk_count": high_risk,
        "pending_case_count": pending,
        "patient_count": patients,
        "ml_model": model_status(),
    }


@api_router.post("/agent/chat", response_model=AgentChatResponse, tags=["AI 风控助手"])
async def agent_chat(data: AgentChatRequest, db: AsyncSession = Depends(get_db_async)):
    result = await answer_question(db, data.question)
    return AgentChatResponse(answer=result.answer, intent=result.intent, llm_used=result.llm_used)


@api_router.get("/alerts", tags=["系统告警"])
async def list_alerts(
    status: str | None = None,
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    query = select(RiskAlert)
    if status:
        query = query.where(RiskAlert.status == status)
    rows = list((await db.execute(query.order_by(RiskAlert.create_time.desc()).limit(page_size))).scalars().all())
    return [{
        "alert_id": row.alert_id, "alert_type": row.alert_type, "alert_level": row.alert_level,
        "alert_title": row.alert_title, "alert_content": row.alert_content,
        "metric_name": row.metric_name,
        "metric_value": float(row.metric_value) if row.metric_value is not None else None,
        "threshold": float(row.threshold) if row.threshold is not None else None,
        "status": row.status, "handler": row.handler, "create_time": row.create_time,
    } for row in rows]


@api_router.post("/alerts/{alert_id}/resolve", tags=["系统告警"])
async def resolve_alert(
    alert_id: int,
    data: AlertResolveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_async),
    _analyst: AppUser = Depends(require_roles("admin", "analyst")),
):
    row = await db.get(RiskAlert, alert_id)
    if row is None:
        raise HTTPException(404, "告警不存在")
    row.status = data.status
    row.handler = data.handler
    row.resolve_time = datetime.now() if data.status in ("RESOLVED", "IGNORED") else None
    await db.commit()
    return {"alert_id": alert_id, "status": row.status, "operator": _operator(request)}


@api_router.get("/action-logs", tags=["操作审计"])
async def list_action_logs(
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db_async),
):
    rows = list((await db.execute(select(RiskActionLog).order_by(
        RiskActionLog.create_time.desc()
    ).limit(page_size))).scalars().all())
    return [{
        "log_id": row.log_id, "operator": row.operator, "action_type": row.action_type,
        "target_type": row.target_type, "target_id": row.target_id,
        "remark": row.remark, "create_time": row.create_time,
    } for row in rows]
