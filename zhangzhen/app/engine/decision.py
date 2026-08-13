"""七步风险决策流水线及原子落库。"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import ulid
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.feature import compute_features
from app.engine.ml_model import ml_model
from app.engine.rule import load_active_rules, match_rules
from app.engine.scoring import DecisionResult, make_decision
from app.models import Decision, EventType, RuleEventType
from app.models_business import (
    BankTransaction,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
)
from app.models_risk import (
    CaseStatus,
    FeatureEntityType,
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeature,
    RiskUserProfile,
)
from app.schemas import RiskCheckResponse, TriggeredRule
from app.service.context import RiskContext


def _now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _new_id(prefix: str) -> str:
    return f"{prefix}{ulid.new().str.lower()}"


def _feature_entity(feature_name: str, context: RiskContext) -> tuple[FeatureEntityType, str]:
    if feature_name.startswith("user_"):
        return FeatureEntityType.USER, context.request.user_id
    if feature_name.startswith("txn_"):
        return FeatureEntityType.TRANSACTION, context.request.source_id
    if feature_name.startswith(("device_", "ip_", "login_")):
        return FeatureEntityType.DEVICE, context.device_id or context.request.user_id
    return FeatureEntityType.CREDIT, context.request.source_id


async def _create_case_if_needed(
    db: AsyncSession,
    context: RiskContext,
    assessment_id: str,
    result: DecisionResult,
    triggered_rules: list[TriggeredRule],
    decision_time: datetime,
) -> None:
    if result.decision not in {Decision.MANUAL_REVIEW, Decision.REJECT}:
        return

    existing_result = await db.execute(
        select(RiskCase.case_id).where(
            RiskCase.source_id == context.request.source_id,
            RiskCase.event_type == context.request.event_type,
            RiskCase.case_status.in_((CaseStatus.PENDING, CaseStatus.REVIEWING)),
        ).limit(1)
    )
    if existing_result.scalar_one_or_none() is not None:
        return

    rejected = result.decision is Decision.REJECT
    db.add(
        RiskCase(
            case_id=_new_id("cas"),
            assessment_id=assessment_id,
            user_id=context.request.user_id,
            case_status=CaseStatus.REJECTED if rejected else CaseStatus.PENDING,
            case_category=context.request.event_type.value,
            risk_detail={
                "final_score": result.final_score,
                "rule_score": result.rule_score,
                "vetoed": result.vetoed,
                "triggered_rule_ids": [rule.rule_id for rule in triggered_rules],
            },
            source_id=context.request.source_id,
            event_type=context.request.event_type,
            reviewer="system" if rejected else None,
            review_comment="极高风险规则一票否决" if result.vetoed else None,
            review_time=decision_time if rejected else None,
            create_time=decision_time,
            update_time=decision_time,
        )
    )


async def _profile_window_summaries(
    db: AsyncSession,
    context: RiskContext,
) -> tuple[int, int, int, int]:
    start_30d = context.event_time - timedelta(days=30)
    failed_result = await db.execute(
        select(func.count(LoginLog.login_id)).where(
            LoginLog.user_id == context.request.user_id,
            LoginLog.success.is_(False),
            LoginLog.login_at >= start_30d,
            LoginLog.login_at <= context.event_time,
        )
    )
    device_result = await db.execute(
        select(func.count(func.distinct(DeviceFingerprint.device_id))).where(
            DeviceFingerprint.user_id == context.request.user_id,
            DeviceFingerprint.first_seen <= context.event_time,
        )
    )
    loan_result = await db.execute(
        select(func.count(LoanApplication.loan_id)).where(
            LoanApplication.user_id == context.request.user_id,
            LoanApplication.apply_at >= start_30d,
            LoanApplication.apply_at <= context.event_time,
        )
    )

    risky_ips = select(IpGeoLocation.ip).where(
        or_(IpGeoLocation.is_proxy.is_(True), IpGeoLocation.is_tor.is_(True))
    )
    login_ip_result = await db.execute(
        select(func.count(LoginLog.login_id)).where(
            LoginLog.user_id == context.request.user_id,
            LoginLog.login_at >= start_30d,
            LoginLog.login_at <= context.event_time,
            LoginLog.ip.in_(risky_ips),
        )
    )
    transaction_ip_result = await db.execute(
        select(func.count(BankTransaction.txn_id)).where(
            BankTransaction.user_id == context.request.user_id,
            BankTransaction.txn_time >= start_30d,
            BankTransaction.txn_time <= context.event_time,
            BankTransaction.ip.in_(risky_ips),
        )
    )
    loan_ip_result = await db.execute(
        select(func.count(LoanApplication.loan_id)).where(
            LoanApplication.user_id == context.request.user_id,
            LoanApplication.apply_at >= start_30d,
            LoanApplication.apply_at <= context.event_time,
            LoanApplication.ip.in_(risky_ips),
        )
    )
    high_risk_ip_count = sum(
        int(value.scalar_one() or 0)
        for value in (login_ip_result, transaction_ip_result, loan_ip_result)
    )
    return (
        int(failed_result.scalar_one() or 0),
        int(device_result.scalar_one() or 0),
        int(loan_result.scalar_one() or 0),
        high_risk_ip_count,
    )


async def _upsert_profile(
    db: AsyncSession,
    context: RiskContext,
    features: dict[str, float],
    result: DecisionResult,
    decision_time: datetime,
) -> None:
    failed_logins, device_count, loan_count, risky_ip_count = await _profile_window_summaries(
        db, context
    )
    profile = await db.get(RiskUserProfile, context.request.user_id)
    if profile is None:
        profile = RiskUserProfile(user_id=context.request.user_id)
        db.add(profile)

    profile.risk_score = result.final_score
    profile.risk_level = result.risk_level
    profile.txn_count_30d = int(features["user_txn_count_30d"])
    profile.txn_amount_30d = Decimal(str(round(features["user_txn_amount_30d"], 2)))
    profile.failed_login_count_30d = failed_logins
    profile.device_count = device_count
    profile.high_risk_ip_count_30d = risky_ip_count
    profile.loan_application_count_30d = loan_count
    if context.loan is not None:
        profile.debt_ratio = context.loan.debt_ratio
    profile.assessment_count = (profile.assessment_count or 0) + 1
    profile.last_assessment_time = decision_time
    profile.profile_data = {
        "last_event_type": context.request.event_type.value,
        "last_source_id": context.request.source_id,
        "last_rule_score": result.rule_score,
        "last_vetoed": result.vetoed,
    }
    profile.update_time = decision_time


async def run_risk_check(
    db: AsyncSession,
    context: RiskContext,
    *,
    decision_time: datetime | None = None,
) -> RiskCheckResponse:
    """执行七步流水线；调用方负责包裹同一个数据库事务。"""

    # 实时请求使用当前时间；历史数据回放显式传入业务事件时间。
    # 该参数只供内部批处理使用，不暴露给 HTTP 调用方，避免伪造审计时间。
    decision_time = decision_time or _now_utc_naive()

    # 1-2. 构造上下文后写入事件快照。
    event_id = _new_id("evt")
    db.add(
        RiskEvent(
            event_id=event_id,
            event_type=context.request.event_type,
            event_source_id=context.request.source_id,
            user_id=context.request.user_id,
            event_data=jsonable_encoder(context.safe_event_snapshot()),
            create_time=decision_time,
        )
    )
    await db.flush()

    # 3-4. 计算并逐维保存固定 25 个特征。
    features = await compute_features(db, context)
    for name, value in features.items():
        entity_type, entity_id = _feature_entity(name, context)
        db.add(
            RiskFeature(
                event_id=event_id,
                entity_type=entity_type,
                entity_id=entity_id,
                feature_name=name,
                feature_value=Decimal(str(value)),
                compute_time=decision_time,
            )
        )

    # 5. 加载当前事件和通用规则并执行 JSON 条件树。
    rule_event_type = RuleEventType(context.request.event_type.value)
    active_rules = await load_active_rules(db, rule_event_type)
    triggered_rules = match_rules(active_rules, features)

    # 6. 模型不存在/失败时 predict 返回 None，自动走纯规则。
    ml_probability = ml_model.predict(features)
    result = make_decision(triggered_rules, ml_probability)

    # 7. 同一事务写评估、可选案件和画像。
    assessment_id = _new_id("ast")
    db.add(
        RiskAssessment(
            assessment_id=assessment_id,
            event_id=event_id,
            user_id=context.request.user_id,
            rule_results=[rule.model_dump(mode="json") for rule in triggered_rules],
            rule_count=len(triggered_rules),
            final_score=result.final_score,
            risk_level=result.risk_level,
            decision=result.decision,
            ml_score=(Decimal(str(result.ml_probability)) if result.ml_probability is not None else None),
            ml_decision=result.ml_decision.value if result.ml_decision else None,
            create_time=decision_time,
        )
    )
    await _create_case_if_needed(
        db, context, assessment_id, result, triggered_rules, decision_time
    )
    await _upsert_profile(db, context, features, result, decision_time)
    await db.flush()

    return RiskCheckResponse(
        assessment_id=assessment_id,
        event_id=event_id,
        user_id=context.request.user_id,
        rule_score=result.rule_score,
        ml_risk_score=result.ml_risk_score,
        rule_weight=result.rule_weight,
        ml_weight=result.ml_weight,
        fusion_score=result.fusion_score,
        final_score=result.final_score,
        risk_level=result.risk_level,
        decision=result.decision,
        rule_count=len(triggered_rules),
        triggered_rules=triggered_rules,
        features=features,
        ml_score=result.ml_probability,
        ml_decision=result.ml_decision,
        vetoed=result.vetoed,
        message=(None if result.ml_probability is not None else "XGBoost未加载，本次使用纯规则决策"),
        create_time=decision_time,
    )
