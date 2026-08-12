from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ml_model import load_feature_context, load_risk_model
from app.models import (
    AuditLog,
    BlacklistExtra,
    BookingFlight,
    OrderInfo,
    OrderPassenger,
    PassengerInfo,
    ReviewCase,
    RiskAssessment,
    RiskHit,
    RiskRule,
    UserInfo,
    VisaApplication,
)
from app.scoring import calculate_account_age_days, calculate_risk_score


ENGINE_VERSION = "hybrid-rules-xgb-1.0"


@dataclass(frozen=True, slots=True)
class RecalculationResult:
    total_orders: int
    changed_assessments: int
    generated_hits: int
    created_review_cases: int
    cancelled_review_cases: int
    reopened_review_cases: int
    decisions: dict[str, int]
    model_version: str | None
    duration_ms: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compare(value: Decimal | float | int, operator: str, threshold: Any) -> bool:
    target = Decimal(str(threshold)) if isinstance(value, Decimal) else float(threshold)
    if operator == "gte":
        return value >= target
    if operator == "lte":
        return value <= target
    if operator == "gt":
        return value > target
    if operator == "lt":
        return value < target
    if operator == "eq":
        return value == target
    return False


def _hour_in_window(hour: int, start: int, end_exclusive: int) -> bool:
    if start < end_exclusive:
        return start <= hour < end_exclusive
    return hour >= start or hour < end_exclusive


def _match_rule(
    rule: RiskRule,
    order: OrderInfo,
    user: UserInfo,
    visas: list[VisaApplication],
    flight: BookingFlight | None,
    flight_events: dict[tuple[int, str, date], list[tuple[datetime, int]]],
    current_passengers: list[PassengerInfo],
    historical_passenger_ids: set[int],
    active_blacklist: set[str],
) -> dict[str, Any] | None:
    condition = rule.condition_json
    metric = condition.get("metric")

    if metric == "visa_reject_count":
        window_days = int(condition["window_days"])
        count = sum(
            1
            for application in visas
            if application.application_status == "REJECTED"
            and application.decided_at is not None
            and order.order_time - timedelta(days=window_days)
            <= application.decided_at
            < order.order_time
        )
        if _compare(count, condition.get("operator", "gte"), condition["threshold"]):
            return {"reject_count": count, "window_days": window_days}

    elif metric == "distinct_visa_countries":
        window_days = int(condition["window_days"])
        countries = {
            application.dest_country
            for application in visas
            if order.order_time - timedelta(days=window_days)
            <= application.submit_time
            <= order.order_time
        }
        if _compare(
            len(countries), condition.get("operator", "gte"), condition["threshold"]
        ):
            return {"country_count": len(countries), "countries": sorted(countries)}

    elif metric == "cross_border_order_amount":
        amount = Decimal(order.total_amount)
        currency = condition.get("currency")
        if (
            order.is_cross_border
            and (not currency or order.currency == currency)
            and _compare(amount, condition.get("operator", "gte"), condition["threshold"])
        ):
            return {"amount": str(amount), "currency": order.currency}

    elif metric == "same_payment_same_flight_tickets" and flight is not None:
        window_hours = int(condition["window_hours"])
        key = (order.payment_account_id, flight.flight_no, flight.flight_date)
        window_start = order.order_time - timedelta(hours=window_hours)
        historical_tickets = sum(
            ticket_count
            for event_time, ticket_count in flight_events[key]
            if window_start <= event_time <= order.order_time
        )
        ticket_count = historical_tickets + flight.ticket_count
        if _compare(
            ticket_count, condition.get("operator", "gte"), condition["threshold"]
        ):
            return {
                "payment_account_id": order.payment_account_id,
                "flight_no": flight.flight_no,
                "flight_date": flight.flight_date.isoformat(),
                "ticket_count": ticket_count,
                "window_hours": window_hours,
            }

    elif metric == "night_order_departure_interval" and order.depart_date is not None:
        start = int(condition["hour_start"])
        end = int(condition["hour_end_exclusive"])
        interval_days = (order.depart_date - order.order_time.date()).days
        if _hour_in_window(order.order_time.hour, start, end) and interval_days <= int(
            condition["interval_days_lte"]
        ):
            return {"order_hour": order.order_time.hour, "interval_days": interval_days}

    elif metric == "historical_passenger_match_rate" and historical_passenger_ids:
        current_ids = {passenger.passenger_id for passenger in current_passengers}
        if current_ids:
            matched = len(current_ids & historical_passenger_ids)
            match_rate = round((matched / len(current_ids)) * 100, 2)
            if _compare(
                match_rate,
                condition.get("operator", "lte"),
                condition["threshold_percent"],
            ):
                return {
                    "match_rate_percent": match_rate,
                    "matched_passengers": matched,
                    "current_passengers": len(current_ids),
                }

    elif metric == "account_age_and_order_amount":
        amount = Decimal(order.total_amount)
        account_age_days = calculate_account_age_days(
            user.registered_at, as_of=order.order_time
        )
        currency = condition.get("currency")
        if (
            account_age_days < int(condition["account_age_days_lt"])
            and (not currency or order.currency == currency)
            and amount > Decimal(str(condition["amount_gt"]))
        ):
            return {"account_age_days": account_age_days, "amount": str(amount)}

    elif metric == "passenger_document_blacklist":
        blacklisted = [
            passenger.id_number_masked
            for passenger in current_passengers
            if passenger.id_number_hash in active_blacklist
        ]
        if blacklisted:
            return {"matched_passports": blacklisted, "match_count": len(blacklisted)}

    return None


def recalculate_all_assessments(
    session: Session,
    *,
    operator: str,
    trigger: str,
    now: datetime | None = None,
    use_model: bool = True,
) -> RecalculationResult:
    started = perf_counter()
    evaluated_at = now or datetime.now()
    session.flush()

    risk_model = load_risk_model() if use_model else None
    feature_context = (
        load_feature_context(session, as_of=evaluated_at)
        if risk_model is not None
        else None
    )

    orders = list(
        session.scalars(select(OrderInfo).order_by(OrderInfo.order_time, OrderInfo.order_id))
    )
    users = {user.user_id: user for user in session.scalars(select(UserInfo))}
    rules_by_group: dict[str, list[RiskRule]] = defaultdict(list)
    for rule in session.scalars(
        select(RiskRule).where(RiskRule.is_enabled.is_(True)).order_by(RiskRule.rule_id)
    ):
        if rule.is_enabled:
            rules_by_group[rule.rule_group_code].append(rule)

    visas_by_user: dict[int, list[VisaApplication]] = defaultdict(list)
    for application in session.scalars(select(VisaApplication)):
        visas_by_user[application.user_id].append(application)

    primary_flight_by_order: dict[int, BookingFlight] = {}
    for flight in session.scalars(
        select(BookingFlight).order_by(BookingFlight.order_id, BookingFlight.segment_no)
    ):
        primary_flight_by_order.setdefault(flight.order_id, flight)

    passengers_by_order: dict[int, list[PassengerInfo]] = defaultdict(list)
    passenger_rows = session.execute(
        select(OrderPassenger.order_id, PassengerInfo)
        .join(PassengerInfo, PassengerInfo.passenger_id == OrderPassenger.passenger_id)
        .order_by(OrderPassenger.order_id, PassengerInfo.passenger_id)
    ).all()
    for order_id, passenger in passenger_rows:
        passengers_by_order[order_id].append(passenger)

    active_blacklist = set(
        session.scalars(
            select(BlacklistExtra.value_hash).where(
                BlacklistExtra.status == "ACTIVE",
                BlacklistExtra.effective_at <= evaluated_at,
                (BlacklistExtra.expire_at.is_(None))
                | (BlacklistExtra.expire_at > evaluated_at),
            )
        )
    )

    assessments = {
        assessment.order_id: assessment
        for assessment in session.scalars(select(RiskAssessment))
    }
    cases = {
        case.assessment_id: case for case in session.scalars(select(ReviewCase))
    }
    before_distribution = Counter(
        assessment.decision for assessment in assessments.values()
    )
    session.execute(delete(RiskHit))

    changed = 0
    generated_hits = 0
    created_cases = 0
    cancelled_cases = 0
    reopened_cases = 0
    after_distribution: Counter[str] = Counter()
    flight_events: dict[tuple[int, str, date], list[tuple[datetime, int]]] = defaultdict(list)
    passenger_history: dict[int, set[int]] = defaultdict(set)

    for order in orders:
        user = users[order.user_id]
        flight = primary_flight_by_order.get(order.order_id)
        current_passengers = passengers_by_order[order.order_id]
        matched: list[tuple[RiskRule, dict[str, Any]]] = []

        for tiers in rules_by_group.values():
            candidates: list[tuple[RiskRule, dict[str, Any]]] = []
            for rule in tiers:
                if order.order_type not in rule.applicable_order_types:
                    continue
                evidence = _match_rule(
                    rule,
                    order,
                    user,
                    visas_by_user[order.user_id],
                    flight,
                    flight_events,
                    current_passengers,
                    passenger_history[order.user_id],
                    active_blacklist,
                )
                if evidence is not None:
                    candidates.append((rule, evidence))
            if candidates:
                matched.append(max(candidates, key=lambda item: (item[0].risk_score, item[0].rule_id)))

        model_margin = (
            risk_model.predict_margin(feature_context.vector(order, user))
            if risk_model is not None and feature_context is not None
            else None
        )
        score = calculate_risk_score(
            (rule.risk_score for rule, _ in matched), model_margin=model_margin
        )
        model_probability = (
            Decimal(f"{score.model_probability:.8f}")
            if score.model_probability is not None
            else None
        )
        model_version = risk_model.version if risk_model is not None else None
        after_distribution[score.decision] += 1
        assessment = assessments.get(order.order_id)
        if assessment is None:
            assessment = RiskAssessment(
                order_id=order.order_id,
                raw_score=score.raw_score,
                model_probability=model_probability,
                model_score=score.model_score if risk_model is not None else None,
                model_version=model_version,
                risk_score=score.final_score,
                decision=score.decision,
                decision_reason=None,
                evaluated_at=evaluated_at,
                engine_version=ENGINE_VERSION,
                created_at=evaluated_at,
            )
            session.add(assessment)
            session.flush()
            assessments[order.order_id] = assessment
            changed += 1
        else:
            if (
                assessment.raw_score != score.raw_score
                or assessment.model_probability != model_probability
                or assessment.model_score
                != (score.model_score if risk_model is not None else None)
                or assessment.model_version != model_version
                or assessment.risk_score != score.final_score
                or assessment.decision != score.decision
            ):
                changed += 1
            assessment.raw_score = score.raw_score
            assessment.model_probability = model_probability
            assessment.model_score = score.model_score if risk_model is not None else None
            assessment.model_version = model_version
            assessment.risk_score = score.final_score
            assessment.decision = score.decision
            assessment.evaluated_at = evaluated_at
            assessment.engine_version = ENGINE_VERSION

        rule_reason = (
            "未命中风险规则"
            if not matched
            else "命中：" + "、".join(dict.fromkeys(rule.rule_name for rule, _ in matched))
        )
        model_reason = (
            f"模型风险概率 {score.model_probability:.2%}，模型分 {score.model_score}"
            if score.model_probability is not None
            else "模型未启用"
        )
        assessment.decision_reason = (
            f"规则原始分 {score.raw_score}；{model_reason}；"
            f"融合分 {score.blended_score}；最终分 {score.final_score}；{rule_reason}"
        )[:500]

        for rule, evidence in matched:
            session.add(
                RiskHit(
                    assessment_id=assessment.assessment_id,
                    rule_id=rule.rule_id,
                    rule_code_snapshot=rule.rule_code,
                    rule_name_snapshot=rule.rule_name,
                    score_snapshot=rule.risk_score,
                    condition_snapshot=rule.condition_json,
                    evidence_json=evidence,
                    created_at=evaluated_at,
                )
            )
            generated_hits += 1

        review_case = cases.get(assessment.assessment_id)
        if score.decision == "REVIEW":
            if review_case is None:
                review_case = ReviewCase(
                    case_no=f"RC{evaluated_at:%Y%m%d}{assessment.assessment_id:08d}",
                    order_id=order.order_id,
                    assessment_id=assessment.assessment_id,
                    status="PENDING",
                    reviewer=None,
                    decision_reason=None,
                    reviewed_at=None,
                    lock_version=0,
                    created_at=evaluated_at,
                    updated_at=evaluated_at,
                )
                session.add(review_case)
                cases[assessment.assessment_id] = review_case
                created_cases += 1
            elif review_case.status != "PENDING":
                review_case.status = "PENDING"
                review_case.reviewer = None
                review_case.decision_reason = None
                review_case.reviewed_at = None
                review_case.updated_at = evaluated_at
                review_case.lock_version += 1
                reopened_cases += 1
        elif review_case is not None:
            if review_case.status != "CANCELLED":
                review_case.status = "CANCELLED"
                review_case.lock_version += 1
                cancelled_cases += 1
            review_case.reviewer = operator
            review_case.decision_reason = (
                "最终得分达到自动拒绝范围，已退出人工审核"
                if score.decision == "REJECT"
                else "最终得分达到通过范围，已退出人工审核"
            )
            review_case.reviewed_at = evaluated_at
            review_case.updated_at = evaluated_at

        if score.decision == "PASS":
            order.order_status = "CONFIRMED"
        elif score.decision == "REVIEW":
            order.order_status = "RISK_REVIEW"
        else:
            order.order_status = "RISK_REJECTED"
        order.updated_at = evaluated_at

        if flight is not None:
            key = (order.payment_account_id, flight.flight_no, flight.flight_date)
            flight_events[key].append((order.order_time, flight.ticket_count))
        passenger_history[order.user_id].update(
            passenger.passenger_id for passenger in current_passengers
        )

    result = RecalculationResult(
        total_orders=len(orders),
        changed_assessments=changed,
        generated_hits=generated_hits,
        created_review_cases=created_cases,
        cancelled_review_cases=cancelled_cases,
        reopened_review_cases=reopened_cases,
        decisions=dict(sorted(after_distribution.items())),
        model_version=risk_model.version if risk_model is not None else None,
        duration_ms=round((perf_counter() - started) * 1000),
    )
    session.add(
        AuditLog(
            operator=operator,
            action="RISK_RECALCULATED",
            entity_type="risk_assessment",
            entity_id="ALL",
            before_data={"decisions": dict(sorted(before_distribution.items()))},
            after_data={"trigger": trigger, **result.as_dict()},
            request_id=f"WEB-RECALC-{evaluated_at:%Y%m%d%H%M%S%f}",
            created_at=evaluated_at,
        )
    )
    session.flush()
    return result
