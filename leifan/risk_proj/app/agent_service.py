from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from typing import Any, Literal

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import ConfigDict, Field, create_model
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import AuthenticatedStaff
from app.models import (
    AuditLog,
    BlacklistExtra,
    OrderInfo,
    OrderPassenger,
    PassengerInfo,
    ReviewCase,
    RiskAssessment,
    RiskHit,
    RiskRule,
    Role,
    StaffUser,
    StaffUserRole,
    UserInfo,
)
from app.risk_engine import recalculate_all_assessments
from app.scoring import calculate_account_age_days


SYSTEM_PROMPT = """
你是“旅盾 RiskOps 管理 Agent”，只服务于当前 OTA 旅游风控项目。

你支持且仅支持以下工作：
1. 查询风险概览、订单、用户、乘客、规则命中和评分详情；
2. 查询并处置人工审核案件；
3. 查询规则组、启用或停用规则组、修改指定规则档位分数、触发全量评分重算；
4. 查询、新增和更新黑护照名单；
5. 查询审计日志和员工账号状态，启用或停用普通员工账号。

边界要求：
- 对旅游风控项目之外的闲聊、知识问答、写作、编程、旅游推荐、外部信息查询等请求，直接简短说明不支持，并列出上述可用能力。
- 不得声称执行了未通过工具执行的数据库操作，不得编造数据库内容。
- 只能调用提供的白名单工具，不得尝试生成或执行任意 SQL。
- 涉及数据变更时，准确说明变更对象、结果以及是否触发评分重算；工具报错时如实说明。
- 证件号属于敏感数据，不在回答中复述完整证件号，只展示脱敏结果。
- 回答使用简洁、清晰的中文；查询结果较多时只总结重点。
- 查询结果包含多条结构化记录时，优先使用 Markdown 表格展示；表格之后再给出简短重点总结。
- 每次请求都是独立请求，没有历史对话。不要声称记得之前的聊天；若当前输入缺少必要标识，请要求用户在本次输入中补充。
""".strip()


# Deep Agents includes filesystem, shell, task-list and sub-agent tools by
# default. This project deliberately exposes only the database tools below.
DEEP_AGENT_EXCLUDED_TOOLS = frozenset(
    {
        "write_todos",
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete_file",
        "glob",
        "grep",
        "execute",
        "task",
    }
)
register_harness_profile(
    "openai",
    HarnessProfile(
        excluded_tools=DEEP_AGENT_EXCLUDED_TOOLS,
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ),
)


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_risk_overview",
        "description": "查询订单量、交易金额、决策分布、待审核数和启用规则数等平台概览。",
        "parameters": _object_schema({}, []),
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_orders",
        "description": "按订单号或用户名、业务类型、决策和风险分范围查询订单。",
        "parameters": _object_schema(
            {
                "query": {"type": ["string", "null"], "description": "订单号或用户名关键词"},
                "order_type": {
                    "type": ["string", "null"],
                    "enum": ["FLIGHT", "HOTEL", "VISA", "TOUR", None],
                },
                "decision": {
                    "type": ["string", "null"],
                    "enum": ["PASS", "REVIEW", "REJECT", None],
                },
                "min_score": {"type": ["integer", "null"], "minimum": 0, "maximum": 100},
                "max_score": {"type": ["integer", "null"], "minimum": 0, "maximum": 100},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            ["query", "order_type", "decision", "min_score", "max_score", "limit"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_order_detail",
        "description": "通过订单ID或订单号查询订单、用户、乘客、最终评分和命中规则详情。",
        "parameters": _object_schema(
            {
                "order_id": {"type": ["integer", "null"], "minimum": 1},
                "order_no": {"type": ["string", "null"]},
            },
            ["order_id", "order_no"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_users",
        "description": "按用户ID或姓名查询用户实名状态、VIP等级、动态账号年龄和订单数。",
        "parameters": _object_schema(
            {
                "query": {"type": ["string", "null"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            ["query", "limit"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "list_review_cases",
        "description": "查询待审核、已放行或已拒绝的人工审核案件。",
        "parameters": _object_schema(
            {
                "status": {
                    "type": ["string", "null"],
                    "enum": ["PENDING", "APPROVED", "REJECTED", "CANCELLED", None],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            ["status", "limit"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "decide_review_case",
        "description": "将一个待审核案件人工放行或拒绝，并更新订单状态和审计日志。",
        "parameters": _object_schema(
            {
                "case_id": {"type": ["integer", "null"], "minimum": 1},
                "case_no": {"type": ["string", "null"]},
                "decision": {"type": "string", "enum": ["APPROVED", "REJECTED"]},
                "reason": {"type": "string", "minLength": 2, "maxLength": 500},
            },
            ["case_id", "case_no", "decision", "reason"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "list_rule_groups",
        "description": "查询全部风险规则组、适用业务、启停状态和各档位条件及分值。",
        "parameters": _object_schema({}, []),
        "strict": True,
    },
    {
        "type": "function",
        "name": "set_rule_group_enabled",
        "description": "启用或停用一个规则组，并立即重算所有订单评分和状态。",
        "parameters": _object_schema(
            {
                "group_code": {"type": "string", "minLength": 1, "maxLength": 50},
                "enabled": {"type": "boolean"},
            },
            ["group_code", "enabled"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "update_rule_tier_score",
        "description": "修改一个指定规则档位的风险分，并立即重算所有订单评分和状态。",
        "parameters": _object_schema(
            {
                "rule_id": {"type": "integer", "minimum": 1},
                "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            ["rule_id", "risk_score"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "recalculate_all_scores",
        "description": "使用当前启用规则和XGBoost模型重算全部订单最终分、决策和审核案件状态。",
        "parameters": _object_schema(
            {"reason": {"type": "string", "minLength": 2, "maxLength": 200}},
            ["reason"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "search_blacklist",
        "description": "按脱敏证件号或原因查询黑护照名单。",
        "parameters": _object_schema(
            {
                "query": {"type": ["string", "null"]},
                "status": {"type": ["string", "null"], "enum": ["ACTIVE", "INACTIVE", None]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            ["query", "status", "limit"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "add_passport_to_blacklist",
        "description": "将护照号以哈希加脱敏形式加入黑名单，不保存证件明文。",
        "parameters": _object_schema(
            {
                "document_number": {"type": "string", "minLength": 4, "maxLength": 128},
                "reason": {"type": "string", "minLength": 2, "maxLength": 500},
                "expire_at": {"type": ["string", "null"], "description": "ISO 8601时间或null"},
            },
            ["document_number", "reason", "expire_at"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "update_blacklist_entry",
        "description": "更新黑名单记录的启停状态、原因和到期时间。",
        "parameters": _object_schema(
            {
                "entry_id": {"type": "integer", "minimum": 1},
                "status": {"type": "string", "enum": ["ACTIVE", "INACTIVE"]},
                "reason": {"type": "string", "minLength": 2, "maxLength": 500},
                "expire_at": {"type": ["string", "null"], "description": "ISO 8601时间或null"},
            },
            ["entry_id", "status", "reason", "expire_at"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_audit_logs",
        "description": "查询数据库写操作的审计日志。",
        "parameters": _object_schema(
            {
                "action": {"type": ["string", "null"]},
                "operator": {"type": ["string", "null"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            ["action", "operator", "limit"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "list_staff_accounts",
        "description": "查询员工账号、角色、启停状态和最近登录时间。",
        "parameters": _object_schema(
            {
                "query": {"type": ["string", "null"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            ["query", "limit"],
        ),
        "strict": True,
    },
    {
        "type": "function",
        "name": "set_staff_account_status",
        "description": "启用或停用普通员工账号；不能停用主管理员或当前操作账号。",
        "parameters": _object_schema(
            {
                "username": {"type": "string", "minLength": 3, "maxLength": 64},
                "active": {"type": "boolean"},
            },
            ["username", "active"],
        ),
        "strict": True,
    },
]


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError("时间必须使用 ISO 8601 格式，例如 2027-01-31T23:59:59") from exc


def _audit(
    db: Session,
    staff: AuthenticatedStaff,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    now = datetime.now()
    db.add(
        AuditLog(
            operator=staff.username,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_data=before,
            after_data=after,
            request_id=f"AGENT-{action}-{entity_id}-{int(now.timestamp())}",
            created_at=now,
        )
    )


def _risk_overview(db: Session) -> dict[str, Any]:
    total_orders, total_amount = db.execute(
        select(func.count(OrderInfo.order_id), func.coalesce(func.sum(OrderInfo.total_amount), 0))
    ).one()
    decisions = dict(
        db.execute(
            select(RiskAssessment.decision, func.count())
            .group_by(RiskAssessment.decision)
        ).all()
    )
    return {
        "total_orders": total_orders,
        "total_amount": float(total_amount),
        "decisions": decisions,
        "pending_reviews": db.scalar(
            select(func.count()).select_from(ReviewCase).where(ReviewCase.status == "PENDING")
        ) or 0,
        "active_rule_tiers": db.scalar(
            select(func.count()).select_from(RiskRule).where(RiskRule.is_enabled.is_(True))
        ) or 0,
        "active_blacklist_entries": db.scalar(
            select(func.count()).select_from(BlacklistExtra).where(BlacklistExtra.status == "ACTIVE")
        ) or 0,
    }


def _search_orders(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    conditions = []
    if args["query"]:
        keyword = f"%{args['query'].strip()}%"
        conditions.append(or_(OrderInfo.order_no.like(keyword), UserInfo.name.like(keyword)))
    if args["order_type"]:
        conditions.append(OrderInfo.order_type == args["order_type"])
    if args["decision"]:
        conditions.append(RiskAssessment.decision == args["decision"])
    if args["min_score"] is not None:
        conditions.append(RiskAssessment.risk_score >= args["min_score"])
    if args["max_score"] is not None:
        conditions.append(RiskAssessment.risk_score <= args["max_score"])
    rows = db.execute(
        select(OrderInfo, UserInfo, RiskAssessment)
        .join(UserInfo, UserInfo.user_id == OrderInfo.user_id)
        .join(RiskAssessment, RiskAssessment.order_id == OrderInfo.order_id)
        .where(*conditions)
        .order_by(OrderInfo.order_time.desc(), OrderInfo.order_id.desc())
        .limit(args["limit"])
    ).all()
    return {
        "count": len(rows),
        "items": [
            {
                "order_id": order.order_id,
                "order_no": order.order_no,
                "user_name": user.name,
                "order_type": order.order_type,
                "amount": float(order.total_amount),
                "destination": order.dest_country,
                "order_status": order.order_status,
                "rule_score": assessment.raw_score,
                "model_score": assessment.model_score,
                "final_score": assessment.risk_score,
                "decision": assessment.decision,
                "order_time": _iso(order.order_time),
            }
            for order, user, assessment in rows
        ],
    }


def _order_detail(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    if args["order_id"] is None and not args["order_no"]:
        raise ValueError("必须提供 order_id 或 order_no")
    condition = (
        OrderInfo.order_id == args["order_id"]
        if args["order_id"] is not None
        else OrderInfo.order_no == args["order_no"].strip()
    )
    row = db.execute(
        select(OrderInfo, UserInfo, RiskAssessment)
        .join(UserInfo, UserInfo.user_id == OrderInfo.user_id)
        .join(RiskAssessment, RiskAssessment.order_id == OrderInfo.order_id)
        .where(condition)
    ).one_or_none()
    if row is None:
        raise ValueError("订单不存在")
    order, user, assessment = row
    passengers = db.execute(
        select(PassengerInfo, OrderPassenger)
        .join(OrderPassenger, OrderPassenger.passenger_id == PassengerInfo.passenger_id)
        .where(OrderPassenger.order_id == order.order_id)
        .order_by(OrderPassenger.is_primary.desc(), PassengerInfo.passenger_id)
    ).all()
    hits = list(
        db.scalars(
            select(RiskHit)
            .where(RiskHit.assessment_id == assessment.assessment_id)
            .order_by(RiskHit.score_snapshot.desc())
        )
    )
    return {
        "order": {
            "order_id": order.order_id,
            "order_no": order.order_no,
            "order_type": order.order_type,
            "amount": float(order.total_amount),
            "destination": order.dest_country,
            "passenger_count": order.passenger_count,
            "order_status": order.order_status,
            "order_time": _iso(order.order_time),
        },
        "user": {
            "user_id": user.user_id,
            "name": user.name,
            "real_name_status": user.real_name_status,
            "vip_level": user.vip_level,
            "account_age_days": calculate_account_age_days(user.registered_at),
        },
        "assessment": {
            "rule_score": assessment.raw_score,
            "model_probability": float(assessment.model_probability) if assessment.model_probability is not None else None,
            "model_score": assessment.model_score,
            "final_score": assessment.risk_score,
            "decision": assessment.decision,
            "reason": assessment.decision_reason,
            "evaluated_at": _iso(assessment.evaluated_at),
        },
        "passengers": [
            {
                "name": passenger.name,
                "id_type": passenger.id_type,
                "id_number_masked": passenger.id_number_masked,
                "nationality": passenger.nationality,
                "role": link.passenger_role,
                "is_primary": link.is_primary,
            }
            for passenger, link in passengers
        ],
        "rule_hits": [
            {
                "rule_code": hit.rule_code_snapshot,
                "rule_name": hit.rule_name_snapshot,
                "score": hit.score_snapshot,
                "evidence": hit.evidence_json,
            }
            for hit in hits
        ],
    }


def _search_users(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    query = (
        select(UserInfo, func.count(OrderInfo.order_id))
        .outerjoin(OrderInfo, OrderInfo.user_id == UserInfo.user_id)
        .group_by(UserInfo.user_id)
    )
    if args["query"]:
        keyword = args["query"].strip()
        if keyword.isdigit():
            query = query.where(or_(UserInfo.user_id == int(keyword), UserInfo.name.like(f"%{keyword}%")))
        else:
            query = query.where(UserInfo.name.like(f"%{keyword}%"))
    rows = db.execute(query.order_by(UserInfo.user_id.desc()).limit(args["limit"])).all()
    return {
        "count": len(rows),
        "items": [
            {
                "user_id": user.user_id,
                "name": user.name,
                "real_name_status": user.real_name_status,
                "vip_level": user.vip_level,
                "registered_at": _iso(user.registered_at),
                "account_age_days": calculate_account_age_days(user.registered_at),
                "order_count": order_count,
            }
            for user, order_count in rows
        ],
    }


def _list_reviews(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    conditions = [ReviewCase.status == args["status"]] if args["status"] else []
    rows = db.execute(
        select(ReviewCase, OrderInfo, UserInfo, RiskAssessment)
        .join(OrderInfo, OrderInfo.order_id == ReviewCase.order_id)
        .join(UserInfo, UserInfo.user_id == OrderInfo.user_id)
        .join(RiskAssessment, RiskAssessment.assessment_id == ReviewCase.assessment_id)
        .where(*conditions)
        .order_by(ReviewCase.created_at.desc())
        .limit(args["limit"])
    ).all()
    return {
        "count": len(rows),
        "items": [
            {
                "case_id": case.case_id,
                "case_no": case.case_no,
                "status": case.status,
                "order_no": order.order_no,
                "order_type": order.order_type,
                "amount": float(order.total_amount),
                "user_name": user.name,
                "final_score": assessment.risk_score,
                "reviewer": case.reviewer,
                "created_at": _iso(case.created_at),
            }
            for case, order, user, assessment in rows
        ],
    }


def _decide_review(db: Session, staff: AuthenticatedStaff, args: dict[str, Any]) -> dict[str, Any]:
    if args["case_id"] is None and not args["case_no"]:
        raise ValueError("必须提供 case_id 或 case_no")
    condition = (
        ReviewCase.case_id == args["case_id"]
        if args["case_id"] is not None
        else ReviewCase.case_no == args["case_no"].strip()
    )
    case = db.scalar(select(ReviewCase).where(condition).with_for_update())
    if case is None:
        raise ValueError("审核案件不存在")
    if case.status != "PENDING":
        raise ValueError(f"案件当前状态为 {case.status}，不能重复处置")
    now = datetime.now()
    before = {"status": case.status, "reviewer": case.reviewer}
    case.status = args["decision"]
    case.reviewer = staff.username
    case.decision_reason = args["reason"].strip()
    case.reviewed_at = now
    case.updated_at = now
    case.lock_version += 1
    order = db.get(OrderInfo, case.order_id)
    if order:
        order.order_status = "CONFIRMED" if case.status == "APPROVED" else "RISK_REJECTED"
        order.updated_at = now
    _audit(
        db, staff, "AGENT_REVIEW_DECIDED", "review_case", str(case.case_id), before,
        {"status": case.status, "reason": case.decision_reason},
    )
    db.flush()
    return {"case_id": case.case_id, "case_no": case.case_no, "status": case.status, "reviewer": case.reviewer}


def _list_rule_groups(db: Session) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for rule in db.scalars(select(RiskRule).order_by(RiskRule.rule_group_code, RiskRule.risk_score.desc())):
        group = groups.setdefault(
            rule.rule_group_code,
            {
                "group_code": rule.rule_group_code,
                "rule_name": rule.rule_name,
                "enabled": False,
                "order_types": rule.applicable_order_types,
                "tiers": [],
            },
        )
        group["enabled"] = group["enabled"] or rule.is_enabled
        group["tiers"].append(
            {"rule_id": rule.rule_id, "score": rule.risk_score, "condition": rule.condition_json}
        )
    return {"count": len(groups), "items": list(groups.values())}


def _set_rule_group(db: Session, staff: AuthenticatedStaff, args: dict[str, Any]) -> dict[str, Any]:
    rules = list(
        db.scalars(
            select(RiskRule)
            .where(RiskRule.rule_group_code == args["group_code"].strip())
            .with_for_update()
        )
    )
    if not rules:
        raise ValueError("规则组不存在")
    before = {"enabled": any(rule.is_enabled for rule in rules)}
    now = datetime.now()
    for rule in rules:
        rule.is_enabled = args["enabled"]
        rule.rule_version += 1
        rule.updated_at = now
    _audit(
        db, staff, "AGENT_RULE_GROUP_STATUS", "risk_rule_group", args["group_code"], before,
        {"enabled": args["enabled"], "tier_count": len(rules)},
    )
    result = recalculate_all_assessments(db, operator=staff.username, trigger=f"agent:rule_group:{args['group_code']}")
    return {"group_code": args["group_code"], "enabled": args["enabled"], "recalculation": result.as_dict()}


def _update_rule_score(db: Session, staff: AuthenticatedStaff, args: dict[str, Any]) -> dict[str, Any]:
    rule = db.scalar(select(RiskRule).where(RiskRule.rule_id == args["rule_id"]).with_for_update())
    if rule is None:
        raise ValueError("规则档位不存在")
    before = {"risk_score": rule.risk_score, "rule_version": rule.rule_version}
    rule.risk_score = args["risk_score"]
    rule.rule_version += 1
    rule.updated_at = datetime.now()
    _audit(
        db, staff, "AGENT_RULE_SCORE_UPDATED", "risk_rule", str(rule.rule_id), before,
        {"risk_score": rule.risk_score, "rule_version": rule.rule_version},
    )
    result = recalculate_all_assessments(db, operator=staff.username, trigger=f"agent:rule:{rule.rule_code}")
    return {
        "rule_id": rule.rule_id,
        "rule_name": rule.rule_name,
        "risk_score": rule.risk_score,
        "recalculation": result.as_dict(),
    }


def _recalculate(db: Session, staff: AuthenticatedStaff, args: dict[str, Any]) -> dict[str, Any]:
    result = recalculate_all_assessments(
        db,
        operator=staff.username,
        trigger=f"agent:manual:{args['reason'].strip()[:100]}",
    )
    return result.as_dict()


def _search_blacklist(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    conditions = []
    if args["query"]:
        keyword = f"%{args['query'].strip()}%"
        conditions.append(or_(BlacklistExtra.value_masked.like(keyword), BlacklistExtra.reason.like(keyword)))
    if args["status"]:
        conditions.append(BlacklistExtra.status == args["status"])
    entries = list(
        db.scalars(
            select(BlacklistExtra)
            .where(*conditions)
            .order_by(BlacklistExtra.created_at.desc())
            .limit(args["limit"])
        )
    )
    return {
        "count": len(entries),
        "items": [
            {
                "entry_id": entry.entry_id,
                "value_masked": entry.value_masked,
                "reason": entry.reason,
                "status": entry.status,
                "effective_at": _iso(entry.effective_at),
                "expire_at": _iso(entry.expire_at),
                "created_by": entry.created_by,
            }
            for entry in entries
        ],
    }


def _mask_document(value: str) -> str:
    return "*" * len(value) if len(value) <= 4 else f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def _add_blacklist(db: Session, staff: AuthenticatedStaff, args: dict[str, Any]) -> dict[str, Any]:
    normalized = args["document_number"].strip().upper()
    value_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    if db.scalar(
        select(BlacklistExtra.entry_id).where(
            BlacklistExtra.entry_type == "PASSPORT",
            BlacklistExtra.value_hash == value_hash,
        )
    ):
        raise ValueError("该证件已经存在于黑名单")
    now = datetime.now()
    entry = BlacklistExtra(
        entry_type="PASSPORT",
        value_hash=value_hash,
        value_masked=_mask_document(normalized),
        reason=args["reason"].strip(),
        status="ACTIVE",
        effective_at=now,
        expire_at=_parse_datetime(args["expire_at"]),
        created_by=staff.username,
        created_at=now,
        updated_at=now,
    )
    db.add(entry)
    db.flush()
    _audit(
        db, staff, "AGENT_BLACKLIST_CREATED", "blacklist_extra", str(entry.entry_id), None,
        {"value_masked": entry.value_masked, "reason": entry.reason, "status": entry.status},
    )
    return {"entry_id": entry.entry_id, "value_masked": entry.value_masked, "status": entry.status}


def _update_blacklist(db: Session, staff: AuthenticatedStaff, args: dict[str, Any]) -> dict[str, Any]:
    entry = db.scalar(
        select(BlacklistExtra).where(BlacklistExtra.entry_id == args["entry_id"]).with_for_update()
    )
    if entry is None:
        raise ValueError("黑名单记录不存在")
    before = {"status": entry.status, "reason": entry.reason, "expire_at": _iso(entry.expire_at)}
    entry.status = args["status"]
    entry.reason = args["reason"].strip()
    entry.expire_at = _parse_datetime(args["expire_at"])
    entry.updated_at = datetime.now()
    after = {"status": entry.status, "reason": entry.reason, "expire_at": _iso(entry.expire_at)}
    _audit(db, staff, "AGENT_BLACKLIST_UPDATED", "blacklist_extra", str(entry.entry_id), before, after)
    db.flush()
    return {"entry_id": entry.entry_id, **after}


def _audit_logs(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    conditions = []
    if args["action"]:
        conditions.append(AuditLog.action == args["action"].strip().upper())
    if args["operator"]:
        conditions.append(AuditLog.operator == args["operator"].strip())
    logs = list(
        db.scalars(
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.created_at.desc(), AuditLog.log_id.desc())
            .limit(args["limit"])
        )
    )
    return {
        "count": len(logs),
        "items": [
            {
                "log_id": log.log_id,
                "operator": log.operator,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "before": log.before_data,
                "after": log.after_data,
                "created_at": _iso(log.created_at),
            }
            for log in logs
        ],
    }


def _staff_accounts(db: Session, args: dict[str, Any]) -> dict[str, Any]:
    query = (
        select(StaffUser, Role)
        .outerjoin(StaffUserRole, StaffUserRole.staff_user_id == StaffUser.staff_user_id)
        .outerjoin(Role, Role.role_id == StaffUserRole.role_id)
    )
    if args["query"]:
        keyword = f"%{args['query'].strip()}%"
        query = query.where(or_(StaffUser.username.like(keyword), StaffUser.display_name.like(keyword)))
    rows = db.execute(query.order_by(StaffUser.staff_user_id).limit(args["limit"])).all()
    return {
        "count": len(rows),
        "items": [
            {
                "username": user.username,
                "display_name": user.display_name,
                "active": user.is_active,
                "role": role.role_name if role else None,
                "last_login_at": _iso(user.last_login_at),
            }
            for user, role in rows
        ],
    }


def _set_staff_status(db: Session, staff: AuthenticatedStaff, args: dict[str, Any]) -> dict[str, Any]:
    user = db.scalar(
        select(StaffUser).where(StaffUser.username == args["username"].strip()).with_for_update()
    )
    if user is None:
        raise ValueError("员工账号不存在")
    if user.username == "administer" and not args["active"]:
        raise ValueError("主管理员账号不可停用")
    if user.staff_user_id == staff.staff_user_id and not args["active"]:
        raise ValueError("不能停用当前登录账号")
    before = {"active": user.is_active, "session_version": user.session_version}
    user.is_active = args["active"]
    if not user.is_active:
        user.session_version += 1
    user.updated_at = datetime.now()
    after = {"active": user.is_active, "session_version": user.session_version}
    _audit(db, staff, "AGENT_STAFF_STATUS", "staff_user", str(user.staff_user_id), before, after)
    db.flush()
    return {"username": user.username, **after}


def execute_tool(
    db: Session,
    staff: AuthenticatedStaff,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if name == "get_risk_overview":
        return _risk_overview(db)
    if name == "search_orders":
        return _search_orders(db, arguments)
    if name == "get_order_detail":
        return _order_detail(db, arguments)
    if name == "search_users":
        return _search_users(db, arguments)
    if name == "list_review_cases":
        return _list_reviews(db, arguments)
    if name == "decide_review_case":
        return _decide_review(db, staff, arguments)
    if name == "list_rule_groups":
        return _list_rule_groups(db)
    if name == "set_rule_group_enabled":
        return _set_rule_group(db, staff, arguments)
    if name == "update_rule_tier_score":
        return _update_rule_score(db, staff, arguments)
    if name == "recalculate_all_scores":
        return _recalculate(db, staff, arguments)
    if name == "search_blacklist":
        return _search_blacklist(db, arguments)
    if name == "add_passport_to_blacklist":
        return _add_blacklist(db, staff, arguments)
    if name == "update_blacklist_entry":
        return _update_blacklist(db, staff, arguments)
    if name == "get_audit_logs":
        return _audit_logs(db, arguments)
    if name == "list_staff_accounts":
        return _staff_accounts(db, arguments)
    if name == "set_staff_account_status":
        return _set_staff_status(db, staff, arguments)
    raise ValueError(f"不支持的工具：{name}")


def _tool_input_model(tool_definition: dict[str, Any]) -> type:
    """Convert the existing strict JSON schema into a Pydantic tool model."""
    schema = tool_definition["parameters"]
    fields: dict[str, tuple[Any, Any]] = {}
    for field_name, field_schema in schema["properties"].items():
        declared_type = field_schema.get("type", "string")
        type_names = declared_type if isinstance(declared_type, list) else [declared_type]
        nullable = "null" in type_names
        enum_values = [value for value in field_schema.get("enum", []) if value is not None]

        if enum_values:
            annotation = Literal.__getitem__(tuple(enum_values))
        else:
            python_type = next((item for item in type_names if item != "null"), "string")
            annotation = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "object": dict[str, Any],
                "array": list[Any],
            }[python_type]
        if nullable:
            annotation = annotation | None

        field_options: dict[str, Any] = {}
        option_names = {
            "description": "description",
            "minimum": "ge",
            "maximum": "le",
            "minLength": "min_length",
            "maxLength": "max_length",
        }
        for schema_name, field_name_option in option_names.items():
            if schema_name in field_schema:
                field_options[field_name_option] = field_schema[schema_name]
        fields[field_name] = (annotation, Field(default=..., **field_options))

    model_name = "".join(part.title() for part in tool_definition["name"].split("_")) + "Input"
    return create_model(
        model_name,
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


def build_agent_tools(
    db: Session,
    staff: AuthenticatedStaff,
    trace: list[dict[str, str]],
) -> list[StructuredTool]:
    """Bind the current request's DB session to the Deep Agent tool set."""

    def make_handler(tool_name: str):
        def handle(**arguments: Any) -> str:
            try:
                # A failed tool rolls back only its own work. Earlier successful
                # tools stay pending until the Agent produces its final answer.
                with db.begin_nested():
                    result = execute_tool(db, staff, tool_name, arguments)
                trace.append({"name": tool_name, "status": "success"})
                payload = {"ok": True, "result": result}
            except Exception as exc:
                trace.append({"name": tool_name, "status": "error"})
                payload = {"ok": False, "error": str(exc)}
            return json.dumps(payload, ensure_ascii=False, default=str)

        handle.__name__ = tool_name
        return handle

    return [
        StructuredTool.from_function(
            func=make_handler(tool_definition["name"]),
            name=tool_definition["name"],
            description=tool_definition["description"],
            args_schema=_tool_input_model(tool_definition),
            infer_schema=False,
        )
        for tool_definition in AGENT_TOOLS
    ]


def _final_answer(messages: list[Any]) -> str:
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        if isinstance(message.content, str):
            return message.content
        if isinstance(message.content, list):
            text_parts: list[str] = []
            for block in message.content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text") or block.get("content")
                    if isinstance(text, str):
                        text_parts.append(text)
            if text_parts:
                return "\n".join(text_parts)
    return "任务已执行，但模型没有返回可展示的结果。"


def run_agent(
    message: str,
    db: Session,
    staff: AuthenticatedStaff,
) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("尚未配置 OPENAI_API_KEY，请先在 .env 中配置")

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    if not base_url:
        raise RuntimeError("OPENAI_BASE_URL 不能为空，请检查 .env 配置")
    model_name = os.getenv("OPENAI_MODEL", "gpt-5.6").strip() or "gpt-5.6"
    model = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        timeout=60.0,
        max_retries=1,
        store=False,
        use_previous_response_id=False,
        model_kwargs={"parallel_tool_calls": False},
    )
    trace: list[dict[str, str]] = []
    agent = create_deep_agent(
        model=model,
        tools=build_agent_tools(db, staff, trace),
        system_prompt=SYSTEM_PROMPT,
        subagents=[],
        memory=None,
        checkpointer=None,
        store=None,
        name="risk_operations_agent",
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": message}]},
        config={"recursion_limit": 24},
    )
    db.commit()
    return {
        "answer": _final_answer(result.get("messages", [])),
        "tools": trace,
        "model": model_name,
    }
