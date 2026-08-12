"""一次风险检查的完整闭环：特征、规则、评估快照和人工案件。"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.decision import calculate_decision
from app.engine.feature import compute_all_features
from app.engine.ml_model import is_model_loaded, predict
from app.engine.rule import load_enabled_rules, match_rules
from app.models_business import EducationCredential, LiveReward, OrderInfo, RefundRequest, UserInfo
from app.models_risk import RiskAssessment, RiskCase, RiskEvent, RiskFeature
from app.schemas import RiskCheckRequest
from app.service.errors import NotFoundError, ValidationError


CONTEXT_REQUIRED = {
    "报名支付成功": "order_id",
    "退费申请提交": "refund_id",
    "退款成功": "refund_id",
    "直播打赏变更": "live_session_id",
}


def validate_request(db: Session, request: RiskCheckRequest) -> None:
    if db.get(UserInfo, request.user_id) is None:
        raise NotFoundError("用户不存在", code="USER_NOT_FOUND")
    required = CONTEXT_REQUIRED.get(request.event_type)
    if required and not getattr(request, required):
        raise ValidationError(f"事件 {request.event_type} 必须提供 {required}", code="MISSING_EVENT_CONTEXT")
    if request.order_id:
        order = db.get(OrderInfo, request.order_id)
        if not order:
            raise NotFoundError("订单不存在", code="ORDER_NOT_FOUND")
        if request.user_id not in (order.user_id, order.learner_user_id):
            raise ValidationError("订单与用户不匹配", code="ORDER_USER_MISMATCH")
    if request.refund_id:
        refund = db.get(RefundRequest, request.refund_id)
        if not refund:
            raise NotFoundError("退费申请不存在", code="REFUND_NOT_FOUND")
        order = db.get(OrderInfo, refund.order_id)
        if not order or request.user_id not in (refund.requested_by_user_id, order.user_id, order.learner_user_id):
            raise ValidationError("退费申请与用户不匹配", code="REFUND_USER_MISMATCH")
        if request.order_id and request.order_id != refund.order_id:
            raise ValidationError("退费申请与订单不匹配", code="REFUND_ORDER_MISMATCH")
    if request.live_session_id:
        exists = db.scalar(select(LiveReward.reward_id).where(
            LiveReward.user_id == request.user_id,
            LiveReward.live_session_id == request.live_session_id,
        ).limit(1))
        if request.event_type == "直播打赏变更" and not exists:
            raise NotFoundError("未找到该用户的直播打赏流水", code="LIVE_REWARD_NOT_FOUND")
    if request.event_type == "学历核验完成":
        exists = db.scalar(select(EducationCredential.credential_id).where(
            EducationCredential.user_id == request.user_id
        ).limit(1))
        if not exists:
            raise NotFoundError("学历认证记录不存在", code="CREDENTIAL_NOT_FOUND")


def run_risk_check(db: Session, request: RiskCheckRequest) -> dict:
    validate_request(db, request)

    try:
        occurred_at = datetime.now()
        features = compute_all_features(
            db, request.user_id, order_id=request.order_id, refund_id=request.refund_id,
            live_session_id=request.live_session_id, as_of=occurred_at,
        )
        rules = load_enabled_rules(db, request.event_type)
        hits = match_rules(rules, features)
        # ML 轨道: 模型已加载则推理; 未加载(无模型/加载失败) -> ml=None, 走纯规则
        ml = predict(features) if is_model_loaded() else None
        result = calculate_decision(hits, ml=ml)
        event_id = f"EVT-{uuid4().hex[:20]}"
        assessment_id = f"ASMT-{uuid4().hex[:20]}"
        source_id = request.source_id or request.refund_id or request.order_id or request.live_session_id or request.user_id
        blocked_by = "学号" if any(hit.rule_id == "R030" for hit in hits) else None

        db.add(RiskEvent(
            event_id=event_id, event_type=request.event_type,
            event_source_id=source_id, user_id=request.user_id,
            event_data=request.event_data or {}, occurred_at=occurred_at,
        ))
        db.flush()
        db.add_all([
            RiskFeature(
                event_id=event_id, entity_type="用户", entity_id=request.user_id,
                feature_name=name, feature_value=value, data_as_of=occurred_at,
            ) for name, value in features.items()
        ])
        hit_data = [hit.to_dict() for hit in hits]
        db.add(RiskAssessment(
            assessment_id=assessment_id, event_id=event_id, user_id=request.user_id,
            feature_snapshot=features, rule_results=hit_data, rule_count=len(hits),
            final_score=result.score, risk_level=result.risk_level,
            decision=result.decision, blocked_by=blocked_by,
            ml_score=result.ml_score, ml_decision=result.ml_decision,
        ))
        db.flush()
        if result.decision == "人工审核":
            db.add(RiskCase(
                case_id=f"CASE-{uuid4().hex[:20]}", assessment_id=assessment_id,
                user_id=request.user_id, case_category=request.event_type,
                risk_detail={"rule_ids": [hit.rule_id for hit in hits], "features": features},
            ))
        db.commit()
        return {
            "assessment_id": assessment_id, "event_id": event_id,
            "user_id": request.user_id, "final_score": result.score,
            "risk_level": result.risk_level, "decision": result.decision,
            "rule_count": len(hits), "triggered_rules": hit_data,
            "features": features, "blocked_by": blocked_by,
            "ml_score": result.ml_score, "ml_decision": result.ml_decision,
        }
    except Exception:
        db.rollback()
        raise
