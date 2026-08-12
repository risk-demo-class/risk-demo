from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthenticatedStaff, require_permission
from app.database import get_db
from app.models import (
    AuditLog,
    BlacklistExtra,
    BookingFlight,
    BookingHotel,
    BookingTour,
    OrderInfo,
    OrderPassenger,
    PassengerInfo,
    PaymentAccount,
    ReviewCase,
    RiskAssessment,
    RiskHit,
    RiskRule,
    UserInfo,
    VisaApplication,
)
from app.scoring import calculate_account_age_days
from app.risk_engine import recalculate_all_assessments


router = APIRouter(prefix="/api")
ORDER_TYPES = {"FLIGHT", "HOTEL", "VISA", "TOUR"}


def sort_expression(column, sort_order: Literal["asc", "desc"]):
    return column.asc() if sort_order == "asc" else column.desc()


class ReviewDecisionRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=2, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class RuleUpdateRequest(BaseModel):
    risk_score: int | None = Field(default=None, ge=0, le=100)
    is_enabled: bool | None = None
    applicable_order_types: list[str] | None = None
    condition_json: dict[str, Any] | None = None
    description: str | None = Field(default=None, max_length=500)

    @field_validator("applicable_order_types")
    @classmethod
    def validate_order_types(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        normalized = list(dict.fromkeys(item.upper() for item in value))
        invalid = set(normalized) - ORDER_TYPES
        if invalid:
            raise ValueError(f"unsupported order types: {', '.join(sorted(invalid))}")
        if not normalized:
            raise ValueError("at least one order type is required")
        return normalized


class RuleTierUpdateRequest(BaseModel):
    rule_id: int
    risk_score: int = Field(ge=0, le=100)
    condition_json: dict[str, Any]


class RuleGroupUpdateRequest(BaseModel):
    is_enabled: bool
    applicable_order_types: list[str]
    tiers: list[RuleTierUpdateRequest] = Field(min_length=1)

    @field_validator("applicable_order_types")
    @classmethod
    def validate_group_order_types(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.upper() for item in value))
        invalid = set(normalized) - ORDER_TYPES
        if invalid or not normalized:
            raise ValueError("请选择至少一种有效业务类型")
        return normalized


class BlacklistCreateRequest(BaseModel):
    document_number: str = Field(min_length=4, max_length=128)
    reason: str = Field(min_length=2, max_length=500)
    expire_at: datetime | None = None

    @field_validator("document_number", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class BlacklistUpdateRequest(BaseModel):
    status: Literal["ACTIVE", "INACTIVE"] | None = None
    reason: str | None = Field(default=None, min_length=2, max_length=500)
    expire_at: datetime | None = None


def mask_document(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def hash_document(value: str) -> str:
    return hashlib.sha256(value.strip().upper().encode("utf-8")).hexdigest()


def order_item(order: OrderInfo, user: UserInfo, assessment: RiskAssessment) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "order_no": order.order_no,
        "user_id": user.user_id,
        "user_name": user.name,
        "order_type": order.order_type,
        "total_amount": float(order.total_amount),
        "currency": order.currency,
        "dest_country": order.dest_country,
        "is_cross_border": order.is_cross_border,
        "order_time": order.order_time,
        "depart_date": order.depart_date,
        "passenger_count": order.passenger_count,
        "order_status": order.order_status,
        "risk_score": assessment.risk_score,
        "raw_score": assessment.raw_score,
        "model_probability": (
            float(assessment.model_probability)
            if assessment.model_probability is not None
            else None
        ),
        "model_score": assessment.model_score,
        "model_version": assessment.model_version,
        "decision": assessment.decision,
        "decision_reason": assessment.decision_reason,
    }


def rule_item(rule: RiskRule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "rule_code": rule.rule_code,
        "rule_group_code": rule.rule_group_code,
        "rule_name": rule.rule_name,
        "applicable_order_types": rule.applicable_order_types,
        "condition_json": rule.condition_json,
        "risk_score": rule.risk_score,
        "is_enabled": rule.is_enabled,
        "rule_version": rule.rule_version,
        "description": rule.description,
        "updated_at": rule.updated_at,
    }


def json_safe_rule_item(rule: RiskRule) -> dict[str, Any]:
    item = rule_item(rule)
    item["updated_at"] = rule.updated_at.isoformat() if rule.updated_at else None
    return item


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ok", "database": "connected"}


@router.get("/dashboard")
def dashboard(
    staff: AuthenticatedStaff = Depends(require_permission("dashboard:view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    total_orders = db.scalar(select(func.count()).select_from(OrderInfo)) or 0
    total_amount = db.scalar(select(func.coalesce(func.sum(OrderInfo.total_amount), 0))) or 0
    pending_reviews = (
        db.scalar(
            select(func.count())
            .select_from(ReviewCase)
            .where(ReviewCase.status == "PENDING")
        )
        or 0
    )

    decision_rows = db.execute(
        select(RiskAssessment.decision, func.count())
        .group_by(RiskAssessment.decision)
        .order_by(RiskAssessment.decision)
    ).all()
    decisions = {decision: count for decision, count in decision_rows}

    type_rows = db.execute(
        select(OrderInfo.order_type, func.count(), func.sum(OrderInfo.total_amount))
        .group_by(OrderInfo.order_type)
        .order_by(OrderInfo.order_type)
    ).all()
    order_types = [
        {"order_type": order_type, "count": count, "amount": float(amount or 0)}
        for order_type, count, amount in type_rows
    ]

    risk_amount = (
        db.scalar(
            select(func.coalesce(func.sum(OrderInfo.total_amount), 0))
            .join(RiskAssessment, RiskAssessment.order_id == OrderInfo.order_id)
            .where(RiskAssessment.decision.in_(("REVIEW", "REJECT")))
        )
        or 0
    )

    top_rule_rows = db.execute(
        select(
            RiskHit.rule_code_snapshot,
            RiskHit.rule_name_snapshot,
            func.count().label("hit_count"),
        )
        .group_by(RiskHit.rule_code_snapshot, RiskHit.rule_name_snapshot)
        .order_by(func.count().desc())
        .limit(6)
    ).all()
    top_rules = [
        {"rule_code": code, "rule_name": name, "hit_count": count}
        for code, name, count in top_rule_rows
    ]

    max_order_time = db.scalar(select(func.max(OrderInfo.order_time)))
    trend: list[dict[str, Any]] = []
    if max_order_time:
        start_date = max_order_time.date() - timedelta(days=13)
        trend_rows = db.execute(
            select(
                func.date(OrderInfo.order_time).label("day"),
                func.count().label("orders"),
                func.sum(RiskAssessment.decision == "REJECT").label("rejected"),
                func.sum(RiskAssessment.decision == "REVIEW").label("reviewed"),
            )
            .join(RiskAssessment, RiskAssessment.order_id == OrderInfo.order_id)
            .where(func.date(OrderInfo.order_time) >= start_date)
            .group_by(func.date(OrderInfo.order_time))
            .order_by(func.date(OrderInfo.order_time))
        ).all()
        trend = [
            {
                "date": day,
                "orders": int(orders),
                "rejected": int(rejected or 0),
                "reviewed": int(reviewed or 0),
            }
            for day, orders, rejected, reviewed in trend_rows
        ]

    recent_rows = db.execute(
        select(OrderInfo, UserInfo, RiskAssessment)
        .join(UserInfo, UserInfo.user_id == OrderInfo.user_id)
        .join(RiskAssessment, RiskAssessment.order_id == OrderInfo.order_id)
        .order_by(OrderInfo.order_time.desc())
        .limit(6)
    ).all()

    return {
        "summary": {
            "total_orders": total_orders,
            "total_amount": float(total_amount),
            "risk_amount": float(risk_amount),
            "pending_reviews": pending_reviews,
            "reject_rate": round((decisions.get("REJECT", 0) / total_orders * 100), 1)
            if total_orders
            else 0,
        },
        "decisions": decisions,
        "order_types": order_types,
        "top_rules": top_rules,
        "trend": trend,
        "recent_orders": [order_item(*row) for row in recent_rows],
    }


@router.get("/orders")
def list_orders(
    q: str | None = None,
    order_type: str | None = None,
    decision: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: Literal[
        "order_no",
        "user_name",
        "order_type",
        "dest_country",
        "total_amount",
        "passenger_count",
        "risk_score",
        "decision",
        "order_time",
    ] = Query(default="order_time"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    staff: AuthenticatedStaff = Depends(require_permission("orders:view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    conditions = []
    if q:
        keyword = f"%{q.strip()}%"
        conditions.append(or_(OrderInfo.order_no.like(keyword), UserInfo.name.like(keyword)))
    if order_type:
        conditions.append(OrderInfo.order_type == order_type.upper())
    if decision:
        conditions.append(RiskAssessment.decision == decision.upper())

    base = (
        select(OrderInfo, UserInfo, RiskAssessment)
        .join(UserInfo, UserInfo.user_id == OrderInfo.user_id)
        .join(RiskAssessment, RiskAssessment.order_id == OrderInfo.order_id)
        .where(*conditions)
    )
    count_query = (
        select(func.count())
        .select_from(OrderInfo)
        .join(UserInfo, UserInfo.user_id == OrderInfo.user_id)
        .join(RiskAssessment, RiskAssessment.order_id == OrderInfo.order_id)
        .where(*conditions)
    )
    total = db.scalar(count_query) or 0
    sort_column = {
        "order_no": OrderInfo.order_no,
        "user_name": UserInfo.name,
        "order_type": OrderInfo.order_type,
        "dest_country": OrderInfo.dest_country,
        "total_amount": OrderInfo.total_amount,
        "passenger_count": OrderInfo.passenger_count,
        "risk_score": RiskAssessment.risk_score,
        "decision": RiskAssessment.decision,
        "order_time": OrderInfo.order_time,
    }[sort_by]
    rows = db.execute(
        base.order_by(sort_expression(sort_column, sort_order), OrderInfo.order_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [order_item(*row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


@router.get("/orders/{order_id}")
def order_detail(
    order_id: int,
    staff: AuthenticatedStaff = Depends(require_permission("orders:view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.execute(
        select(OrderInfo, UserInfo, PaymentAccount, RiskAssessment)
        .join(UserInfo, UserInfo.user_id == OrderInfo.user_id)
        .join(PaymentAccount, PaymentAccount.payment_account_id == OrderInfo.payment_account_id)
        .join(RiskAssessment, RiskAssessment.order_id == OrderInfo.order_id)
        .where(OrderInfo.order_id == order_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    order, user, payment, assessment = row

    passenger_rows = db.execute(
        select(PassengerInfo, OrderPassenger)
        .join(OrderPassenger, OrderPassenger.passenger_id == PassengerInfo.passenger_id)
        .where(OrderPassenger.order_id == order_id)
        .order_by(OrderPassenger.is_primary.desc(), PassengerInfo.passenger_id)
    ).all()
    passengers = [
        {
            "passenger_id": passenger.passenger_id,
            "name": passenger.name,
            "id_type": passenger.id_type,
            "id_number_masked": passenger.id_number_masked,
            "nationality": passenger.nationality,
            "birth_date": passenger.birth_date,
            "gender": passenger.gender,
            "passenger_role": association.passenger_role,
            "is_primary": association.is_primary,
        }
        for passenger, association in passenger_rows
    ]

    hit_rows = db.execute(
        select(RiskHit)
        .where(RiskHit.assessment_id == assessment.assessment_id)
        .order_by(RiskHit.score_snapshot.desc())
    ).scalars()
    hits = [
        {
            "hit_id": hit.hit_id,
            "rule_code": hit.rule_code_snapshot,
            "rule_name": hit.rule_name_snapshot,
            "score": hit.score_snapshot,
            "condition": hit.condition_snapshot,
            "evidence": hit.evidence_json,
        }
        for hit in hit_rows
    ]

    review = db.scalar(
        select(ReviewCase).where(ReviewCase.assessment_id == assessment.assessment_id)
    )
    review_data = None
    if review:
        review_data = {
            "case_id": review.case_id,
            "case_no": review.case_no,
            "status": review.status,
            "reviewer": review.reviewer,
            "decision_reason": review.decision_reason,
            "reviewed_at": review.reviewed_at,
            "created_at": review.created_at,
        }

    product_detail: Any = None
    if order.order_type == "FLIGHT":
        product_detail = [
            {
                "flight_no": item.flight_no,
                "flight_date": item.flight_date,
                "depart_airport": item.depart_airport,
                "arrive_airport": item.arrive_airport,
                "cabin_class": item.cabin_class,
                "ticket_count": item.ticket_count,
                "segment_no": item.segment_no,
            }
            for item in db.scalars(
                select(BookingFlight)
                .where(BookingFlight.order_id == order_id)
                .order_by(BookingFlight.segment_no)
            )
        ]
    elif order.order_type == "HOTEL":
        item = db.scalar(select(BookingHotel).where(BookingHotel.order_id == order_id))
        if item:
            product_detail = {
                "hotel_id": item.hotel_id,
                "check_in": item.check_in,
                "check_out": item.check_out,
                "room_count": item.room_count,
                "is_refundable": item.is_refundable,
                "city_code": item.city_code,
            }
    elif order.order_type == "TOUR":
        item = db.scalar(select(BookingTour).where(BookingTour.order_id == order_id))
        if item:
            product_detail = {
                "tour_code": item.tour_code,
                "tour_name": item.tour_name,
                "route_type": item.route_type,
                "group_code": item.group_code,
                "departure_date": item.departure_date,
                "return_date": item.return_date,
                "traveler_count": item.traveler_count,
            }
    elif order.order_type == "VISA":
        product_detail = [
            {
                "visa_id": item.visa_id,
                "passenger_id": item.passenger_id,
                "dest_country": item.dest_country,
                "visa_type": item.visa_type,
                "application_status": item.application_status,
                "reject_history": item.reject_history,
                "reject_reason": item.reject_reason,
                "submit_time": item.submit_time,
                "decided_at": item.decided_at,
            }
            for item in db.scalars(
                select(VisaApplication)
                .where(VisaApplication.order_id == order_id)
                .order_by(VisaApplication.visa_id)
            )
        ]

    return {
        "order": order_item(order, user, assessment),
        "user": {
            "user_id": user.user_id,
            "name": user.name,
            "real_name_status": user.real_name_status,
            "vip_level": user.vip_level,
            "registered_at": user.registered_at,
            "account_age_days": calculate_account_age_days(user.registered_at),
        },
        "payment": {
            "payment_account_id": payment.payment_account_id,
            "account_type": payment.account_type,
            "status": payment.status,
        },
        "passengers": passengers,
        "product_detail": product_detail,
        "assessment": {
            "assessment_id": assessment.assessment_id,
            "raw_score": assessment.raw_score,
            "model_probability": (
                float(assessment.model_probability)
                if assessment.model_probability is not None
                else None
            ),
            "model_score": assessment.model_score,
            "model_version": assessment.model_version,
            "risk_score": assessment.risk_score,
            "decision": assessment.decision,
            "decision_reason": assessment.decision_reason,
            "evaluated_at": assessment.evaluated_at,
            "engine_version": assessment.engine_version,
        },
        "hits": hits,
        "review_case": review_data,
    }


@router.get("/reviews")
def list_reviews(
    case_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: Literal[
        "case_no",
        "order_no",
        "user_name",
        "order_type",
        "total_amount",
        "risk_score",
        "status",
        "created_at",
    ] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    staff: AuthenticatedStaff = Depends(require_permission("reviews:view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    conditions = []
    if case_status:
        conditions.append(ReviewCase.status == case_status.upper())
    base = (
        select(ReviewCase, OrderInfo, UserInfo, RiskAssessment)
        .join(OrderInfo, OrderInfo.order_id == ReviewCase.order_id)
        .join(UserInfo, UserInfo.user_id == OrderInfo.user_id)
        .join(RiskAssessment, RiskAssessment.assessment_id == ReviewCase.assessment_id)
        .where(*conditions)
    )
    count_query = select(func.count()).select_from(ReviewCase).where(*conditions)
    total = db.scalar(count_query) or 0
    sort_column = {
        "case_no": ReviewCase.case_no,
        "order_no": OrderInfo.order_no,
        "user_name": UserInfo.name,
        "order_type": OrderInfo.order_type,
        "total_amount": OrderInfo.total_amount,
        "risk_score": RiskAssessment.risk_score,
        "status": ReviewCase.status,
        "created_at": ReviewCase.created_at,
    }[sort_by]
    rows = db.execute(
        base.order_by(sort_expression(sort_column, sort_order), ReviewCase.case_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [
            {
                "case_id": case.case_id,
                "case_no": case.case_no,
                "status": case.status,
                "reviewer": case.reviewer,
                "decision_reason": case.decision_reason,
                "reviewed_at": case.reviewed_at,
                "created_at": case.created_at,
                "order_id": order.order_id,
                "order_no": order.order_no,
                "order_type": order.order_type,
                "total_amount": float(order.total_amount),
                "user_name": user.name,
                "risk_score": assessment.risk_score,
                "decision_reason_summary": assessment.decision_reason,
            }
            for case, order, user, assessment in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


@router.post("/reviews/{case_id}/decision")
def decide_review(
    case_id: int,
    payload: ReviewDecisionRequest,
    staff: AuthenticatedStaff = Depends(require_permission("reviews:decide")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    case = db.scalar(
        select(ReviewCase).where(ReviewCase.case_id == case_id).with_for_update()
    )
    if case is None:
        raise HTTPException(status_code=404, detail="审核案件不存在")
    if case.status != "PENDING":
        raise HTTPException(status_code=409, detail="该案件已经完成处置")

    before = {"status": case.status, "reviewer": case.reviewer}
    now = datetime.now()
    case.status = payload.decision
    case.reviewer = staff.username
    case.decision_reason = payload.reason
    case.reviewed_at = now
    case.updated_at = now
    case.lock_version += 1

    order = db.get(OrderInfo, case.order_id)
    if order:
        order.order_status = "CONFIRMED" if payload.decision == "APPROVED" else "RISK_REJECTED"
        order.updated_at = now

    db.add(
        AuditLog(
            operator=staff.username,
            action="REVIEW_DECIDED",
            entity_type="review_case",
            entity_id=str(case.case_id),
            before_data=before,
            after_data={"status": case.status, "decision_reason": case.decision_reason},
            request_id=f"WEB-REVIEW-{case.case_id}-{int(now.timestamp())}",
            created_at=now,
        )
    )
    db.commit()
    return {"case_id": case.case_id, "status": case.status, "reviewer": case.reviewer}


@router.get("/rules")
def list_rules(
    staff: AuthenticatedStaff = Depends(require_permission("rules:view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rules = db.scalars(
        select(RiskRule).order_by(RiskRule.rule_group_code, RiskRule.risk_score.desc())
    )
    return {"items": [rule_item(rule) for rule in rules]}


@router.patch("/rules/{rule_id}")
def update_rule(
    rule_id: int,
    payload: RuleUpdateRequest,
    staff: AuthenticatedStaff = Depends(require_permission("rules:manage")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not payload.model_fields_set:
        raise HTTPException(status_code=422, detail="至少提供一个需要更新的字段")
    rule = db.scalar(select(RiskRule).where(RiskRule.rule_id == rule_id).with_for_update())
    if rule is None:
        raise HTTPException(status_code=404, detail="规则不存在")
    before = json_safe_rule_item(rule)
    for field_name in payload.model_fields_set:
        setattr(rule, field_name, getattr(payload, field_name))
    rule.rule_version += 1
    rule.updated_at = datetime.now()
    after = json_safe_rule_item(rule)
    db.add(
        AuditLog(
            operator=staff.username,
            action="RULE_UPDATED",
            entity_type="risk_rule",
            entity_id=str(rule.rule_id),
            before_data=before,
            after_data=after,
            request_id=f"WEB-RULE-{rule.rule_id}-{rule.rule_version}",
            created_at=datetime.now(),
        )
    )
    db.flush()
    recalculation = recalculate_all_assessments(
        db,
        operator=staff.username,
        trigger=f"rule:{rule.rule_code}",
    )
    db.commit()
    response = rule_item(rule)
    response["recalculation"] = recalculation.as_dict()
    return response


@router.get("/rule-groups")
def list_rule_groups(
    staff: AuthenticatedStaff = Depends(require_permission("rules:view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rules = list(
        db.scalars(
            select(RiskRule).order_by(RiskRule.rule_group_code, RiskRule.risk_score.desc())
        )
    )
    groups: dict[str, dict[str, Any]] = {}
    for rule in rules:
        group = groups.setdefault(
            rule.rule_group_code,
            {
                "group_code": rule.rule_group_code,
                "rule_name": rule.rule_name,
                "is_enabled": False,
                "applicable_order_types": rule.applicable_order_types,
                "description": rule.description,
                "tiers": [],
            },
        )
        group["is_enabled"] = group["is_enabled"] or rule.is_enabled
        group["tiers"].append(
            {
                "rule_id": rule.rule_id,
                "risk_score": rule.risk_score,
                "condition_json": rule.condition_json,
            }
        )
    return {"items": list(groups.values())}


@router.patch("/rule-groups/{group_code}")
def update_rule_group(
    group_code: str,
    payload: RuleGroupUpdateRequest,
    staff: AuthenticatedStaff = Depends(require_permission("rules:manage")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rules = list(
        db.scalars(
            select(RiskRule)
            .where(RiskRule.rule_group_code == group_code)
            .with_for_update()
        )
    )
    if not rules:
        raise HTTPException(status_code=404, detail="规则组不存在")
    by_id = {rule.rule_id: rule for rule in rules}
    tier_ids = [tier.rule_id for tier in payload.tiers]
    if len(tier_ids) != len(set(tier_ids)) or set(tier_ids) != set(by_id):
        raise HTTPException(status_code=422, detail="规则档位与当前规则组不一致")
    before = [json_safe_rule_item(rule) for rule in rules]
    tier_map = {tier.rule_id: tier for tier in payload.tiers}
    now = datetime.now()
    for rule in rules:
        tier = tier_map[rule.rule_id]
        rule.risk_score = tier.risk_score
        rule.condition_json = tier.condition_json
        rule.is_enabled = payload.is_enabled
        rule.applicable_order_types = payload.applicable_order_types
        rule.rule_version += 1
        rule.updated_at = now
    after = [json_safe_rule_item(rule) for rule in rules]
    db.add(
        AuditLog(
            operator=staff.username,
            action="RULE_GROUP_UPDATED",
            entity_type="risk_rule_group",
            entity_id=group_code,
            before_data={"tiers": before},
            after_data={"tiers": after},
            request_id=f"WEB-RULE-GROUP-{group_code}-{int(now.timestamp())}",
            created_at=now,
        )
    )
    db.flush()
    recalculation = recalculate_all_assessments(
        db,
        operator=staff.username,
        trigger=f"rule_group:{group_code}",
    )
    db.commit()
    return {
        "group_code": group_code,
        "updated_tiers": len(rules),
        "recalculation": recalculation.as_dict(),
    }


@router.get("/blacklist")
def list_blacklist(
    q: str | None = None,
    entry_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: Literal[
        "entry_id",
        "value_masked",
        "reason",
        "status",
        "effective_at",
        "expire_at",
        "created_by",
        "created_at",
    ] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    staff: AuthenticatedStaff = Depends(require_permission("blacklist:view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    conditions = []
    if q:
        keyword = f"%{q.strip()}%"
        conditions.append(
            or_(BlacklistExtra.value_masked.like(keyword), BlacklistExtra.reason.like(keyword))
        )
    if entry_status:
        conditions.append(BlacklistExtra.status == entry_status.upper())
    total = (
        db.scalar(select(func.count()).select_from(BlacklistExtra).where(*conditions)) or 0
    )
    sort_column = {
        "entry_id": BlacklistExtra.entry_id,
        "value_masked": BlacklistExtra.value_masked,
        "reason": BlacklistExtra.reason,
        "status": BlacklistExtra.status,
        "effective_at": BlacklistExtra.effective_at,
        "expire_at": BlacklistExtra.expire_at,
        "created_by": BlacklistExtra.created_by,
        "created_at": BlacklistExtra.created_at,
    }[sort_by]
    entries = db.scalars(
        select(BlacklistExtra)
        .where(*conditions)
        .order_by(sort_expression(sort_column, sort_order), BlacklistExtra.entry_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [
            {
                "entry_id": entry.entry_id,
                "entry_type": entry.entry_type,
                "value_masked": entry.value_masked,
                "reason": entry.reason,
                "status": entry.status,
                "effective_at": entry.effective_at,
                "expire_at": entry.expire_at,
                "created_by": entry.created_by,
                "created_at": entry.created_at,
            }
            for entry in entries
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


@router.post("/blacklist", status_code=status.HTTP_201_CREATED)
def create_blacklist_entry(
    payload: BlacklistCreateRequest,
    staff: AuthenticatedStaff = Depends(require_permission("blacklist:manage")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    normalized = payload.document_number.upper()
    value_hash = hash_document(normalized)
    duplicate = db.scalar(
        select(BlacklistExtra).where(
            BlacklistExtra.entry_type == "PASSPORT",
            BlacklistExtra.value_hash == value_hash,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="该证件号已存在于名单中")
    now = datetime.now()
    entry = BlacklistExtra(
        entry_type="PASSPORT",
        value_hash=value_hash,
        value_masked=mask_document(normalized),
        reason=payload.reason,
        status="ACTIVE",
        effective_at=now,
        expire_at=payload.expire_at,
        created_by=staff.username,
        created_at=now,
        updated_at=now,
    )
    db.add(entry)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="该证件号已存在于名单中") from exc
    db.add(
        AuditLog(
            operator=staff.username,
            action="BLACKLIST_CREATED",
            entity_type="blacklist_extra",
            entity_id=str(entry.entry_id),
            before_data=None,
            after_data={
                "value_masked": entry.value_masked,
                "reason": entry.reason,
                "status": entry.status,
            },
            request_id=f"WEB-BLACKLIST-{entry.entry_id}",
            created_at=now,
        )
    )
    db.commit()
    return {"entry_id": entry.entry_id, "value_masked": entry.value_masked, "status": entry.status}


@router.patch("/blacklist/{entry_id}")
def update_blacklist_entry(
    entry_id: int,
    payload: BlacklistUpdateRequest,
    staff: AuthenticatedStaff = Depends(require_permission("blacklist:manage")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not payload.model_fields_set:
        raise HTTPException(status_code=422, detail="至少提供一个需要更新的字段")
    entry = db.scalar(
        select(BlacklistExtra).where(BlacklistExtra.entry_id == entry_id).with_for_update()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="名单记录不存在")
    before = {
        "status": entry.status,
        "reason": entry.reason,
        "expire_at": entry.expire_at.isoformat() if entry.expire_at else None,
    }
    for field_name in payload.model_fields_set:
        setattr(entry, field_name, getattr(payload, field_name))
    entry.updated_at = datetime.now()
    db.add(
        AuditLog(
            operator=staff.username,
            action="BLACKLIST_UPDATED",
            entity_type="blacklist_extra",
            entity_id=str(entry.entry_id),
            before_data=before,
            after_data={
                "status": entry.status,
                "reason": entry.reason,
                "expire_at": entry.expire_at.isoformat() if entry.expire_at else None,
            },
            request_id=f"WEB-BLACKLIST-UPDATE-{entry.entry_id}",
            created_at=datetime.now(),
        )
    )
    db.commit()
    return {"entry_id": entry.entry_id, "status": entry.status, "reason": entry.reason}


@router.delete("/blacklist/{entry_id}")
def delete_blacklist_entry(
    entry_id: int,
    staff: AuthenticatedStaff = Depends(require_permission("blacklist:manage")),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    entry = db.scalar(
        select(BlacklistExtra).where(BlacklistExtra.entry_id == entry_id).with_for_update()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="名单记录不存在")
    before = {
        "value_masked": entry.value_masked,
        "reason": entry.reason,
        "status": entry.status,
    }
    now = datetime.now()
    db.delete(entry)
    db.add(
        AuditLog(
            operator=staff.username,
            action="BLACKLIST_DELETED",
            entity_type="blacklist_extra",
            entity_id=str(entry.entry_id),
            before_data=before,
            after_data=None,
            request_id=f"WEB-BLACKLIST-DELETE-{entry.entry_id}",
            created_at=now,
        )
    )
    db.commit()
    return {"deleted": True}


@router.get("/audit")
def list_audit_logs(
    action: str | None = None,
    entity_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: Literal[
        "created_at",
        "operator",
        "action",
        "entity_type",
        "entity_id",
        "request_id",
    ] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    staff: AuthenticatedStaff = Depends(require_permission("audit:view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    conditions = []
    if action:
        conditions.append(AuditLog.action == action.upper())
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*conditions)) or 0
    sort_column = {
        "created_at": AuditLog.created_at,
        "operator": AuditLog.operator,
        "action": AuditLog.action,
        "entity_type": AuditLog.entity_type,
        "entity_id": AuditLog.entity_id,
        "request_id": AuditLog.request_id,
    }[sort_by]
    logs = db.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(sort_expression(sort_column, sort_order), AuditLog.log_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [
            {
                "log_id": log.log_id,
                "operator": log.operator,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "before_data": log.before_data,
                "after_data": log.after_data,
                "request_id": log.request_id,
                "created_at": log.created_at,
            }
            for log in logs
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
        "sort_by": sort_by,
        "sort_order": sort_order,
    }
