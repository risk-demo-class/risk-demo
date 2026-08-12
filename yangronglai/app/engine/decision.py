"""Stage-3 decision orchestrator with durable rule audit."""

import logging
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.engine.fusion import fuse_scores
from app.engine.graph import graph_engine
from app.engine.model_manager import model_manager
from app.engine.rule import RuleEvaluation, rule_engine
from app.models_risk import (
    RiskAssessment,
    RiskCase,
    RiskEvent,
    RiskFeatureSnapshot,
    RiskRule,
    RiskRuleHit,
)
from app.observability import classify_outcome, get_request_id, new_request_id, pseudonymize
from app.schemas import (
    AppealOption,
    ComponentScore,
    FusionBreakdown,
    RuleHitResponse,
    RiskCheckRequest,
    RiskCheckResponse,
    ScoreBreakdown,
)
from app.service.appeals import issue_appeal_token
from app.service.features import EventContext


decision_logger = logging.getLogger("bankrisk.decision")


@dataclass(slots=True)
class DecisionEngine:
    stage: str = "complete-three-layer"

    def capabilities(self) -> dict:
        return {
            "stage": self.stage,
            "scenarios": ["CARD", "LOAN", "TRANSFER", "LOGIN"],
            "business_tables": 8,
            "risk_tables": 10,
            "mandatory_rules": 8,
            "components": settings.enabled_components(),
        }

    async def assess(
        self,
        request: RiskCheckRequest,
        context: EventContext,
        session: AsyncSession,
    ) -> RiskCheckResponse:
        rules = await self._load_rules(request.scenario.value, session)
        evaluation = (
            rule_engine.evaluate(
                context.features,
                rules,
                additional_weight=settings.RULE_ADDITIONAL_WEIGHT,
            )
            if settings.ENABLE_RULE_ENGINE
            else RuleEvaluation(score=0, risk_level="低", decision="通过", hits=())
        )
        model_evaluation = (
            model_manager.score(request.scenario.value, context.features)
            if settings.ENABLE_MODEL_ENGINE
            else None
        )
        graph_evaluation = (
            await graph_engine.evaluate(request.user_id, context.features, session)
            if settings.ENABLE_GRAPH_ENGINE
            else None
        )
        component_scores: dict[str, int] = {}
        if settings.ENABLE_RULE_ENGINE:
            component_scores["rule"] = evaluation.score
        if model_evaluation is not None:
            component_scores["model"] = model_evaluation.score
        if graph_evaluation is not None:
            component_scores["graph"] = graph_evaluation.score
        fusion = fuse_scores(
            component_scores,
            additional_weight=settings.FUSION_ADDITIONAL_WEIGHT,
            minimum_decision=evaluation.decision,
            minimum_level=evaluation.risk_level,
        )
        token = uuid4().hex
        request_id = get_request_id()
        if request_id == "-":
            request_id = new_request_id()
        event_id = f"EVT_{token}"
        assessment_id = f"ASM_{token}"
        hit_payloads = [
            {
                "rule_id": hit.rule_id,
                "rule_name": hit.rule_name,
                "risk_score": hit.risk_score,
                "risk_level": hit.risk_level,
                "decision": hit.decision,
                "evidence": hit.evidence,
                "version": hit.version,
            }
            for hit in evaluation.hits
        ]
        if evaluation.hits:
            hit_names = "、".join(f"{hit.rule_id} {hit.rule_name}" for hit in evaluation.hits)
            rule_reason = (
                f"命中规则：{hit_names}；聚合分={evaluation.highest_rule_score}"
                f"+{evaluation.other_rules_score_sum}×{evaluation.additional_weight:g}"
                f"={evaluation.raw_score:g}，封顶后 {evaluation.score} 分。"
            )
        else:
            rule_reason = "未命中启用规则。"
        decision_reason = (
            f"{rule_reason} 三层分={fusion.component_scores}；融合分="
            f"{fusion.primary_score}+{fusion.other_components_score_sum}×"
            f"{fusion.additional_weight:g}={fusion.raw_score:g}，最终 {fusion.score} 分。"
        )

        event = RiskEvent(
            event_id=event_id,
            request_id=request_id,
            scenario=request.scenario.value,
            source_id=request.source_id,
            user_id=request.user_id,
            event_data=context.event_data,
            event_time=context.event_time,
        )
        session.add(event)
        audit_features = dict(context.features)
        audit_features["_model_result"] = (
            {
                "score": model_evaluation.score,
                "probability": model_evaluation.probability,
                "version": model_evaluation.version,
                "submodels": model_evaluation.submodels,
            }
            if model_evaluation
            else None
        )
        audit_features["_graph_result"] = (
            {
                "score": graph_evaluation.score,
                "version": graph_evaluation.version,
                "backend": graph_evaluation.backend,
                "signals": graph_evaluation.signals,
            }
            if graph_evaluation
            else None
        )
        audit_features["_fusion_result"] = {
            "score": fusion.score,
            "component_scores": fusion.component_scores,
            "raw_score": fusion.raw_score,
            "weight": fusion.additional_weight,
        }
        session.add(
            RiskFeatureSnapshot(
                event_id=event_id,
                feature_version=rule_engine.version,
                features=audit_features,
            )
        )
        for hit in evaluation.hits:
            session.add(
                RiskRuleHit(
                    event_id=event_id,
                    rule_id=hit.rule_id,
                    rule_name=hit.rule_name,
                    risk_score=hit.risk_score,
                    risk_level=hit.risk_level,
                    decision=hit.decision,
                    condition_snapshot=hit.condition,
                    evidence=hit.evidence,
                    rule_version=hit.version,
                )
            )
        assessment = RiskAssessment(
            assessment_id=assessment_id,
            event_id=event_id,
            user_id=request.user_id,
            scenario=request.scenario.value,
            rule_score=evaluation.score,
            model_score=model_evaluation.score if model_evaluation else None,
            graph_score=graph_evaluation.score if graph_evaluation else None,
            final_score=fusion.score,
            risk_level=fusion.risk_level,
            decision=fusion.decision,
            hit_count=len(evaluation.hits),
            rule_results=hit_payloads,
            decision_reason=decision_reason,
        )
        session.add(assessment)
        if fusion.decision == "人工审核":
            session.add(
                RiskCase(
                    case_id=f"CASE_{token}",
                    assessment_id=assessment_id,
                    source_id=request.source_id,
                    user_id=request.user_id,
                    scenario=request.scenario.value,
                    status="PENDING",
                    risk_detail={
                        "score": fusion.score,
                        "components": fusion.component_scores,
                        "rules": hit_payloads,
                        "reason": decision_reason,
                    },
                )
            )
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        if fusion.decision == "拒绝":
            appeal_token, appeal_deadline = issue_appeal_token(assessment_id)
            appeal_option = AppealOption(
                allowed=True,
                deadline=appeal_deadline,
                page_url="/appeal",
                submit_url="/api/client/appeals",
                token=appeal_token,
            )
        else:
            appeal_option = AppealOption(allowed=False)

        decision_logger.info(
            "risk_decision_completed",
            extra={
                "event_data": {
                    "outcome": classify_outcome("/api/risk/check", 200, fusion.decision),
                    "assessment_id": assessment_id,
                    "user_ref": pseudonymize(request.user_id),
                    "source_ref": pseudonymize(request.source_id),
                    "scores": {
                        "rule": evaluation.score,
                        "model": model_evaluation.score if model_evaluation else None,
                        "graph": graph_evaluation.score if graph_evaluation else None,
                        "final": fusion.score,
                    },
                    "risk_level": fusion.risk_level,
                    "decision": fusion.decision,
                    "appeal_allowed": appeal_option.allowed,
                    "hit_count": len(evaluation.hits),
                    "rule_versions": [
                        {"rule_id": hit.rule_id, "version": hit.version} for hit in evaluation.hits
                    ],
                    "component_versions": {
                        "rule": rule_engine.version,
                        "model": model_evaluation.version if model_evaluation else None,
                        "graph": graph_evaluation.version if graph_evaluation else None,
                    },
                }
            },
        )

        components = [
            ComponentScore(
                component="rule",
                enabled=settings.ENABLE_RULE_ENGINE,
                score=evaluation.score if settings.ENABLE_RULE_ENGINE else None,
                version=rule_engine.version,
            ),
            ComponentScore(
                component="model",
                enabled=settings.ENABLE_MODEL_ENGINE,
                score=model_evaluation.score if model_evaluation else None,
                version=model_evaluation.version if model_evaluation else None,
            ),
            ComponentScore(
                component="graph",
                enabled=settings.ENABLE_GRAPH_ENGINE,
                score=graph_evaluation.score if graph_evaluation else None,
                version=graph_evaluation.version if graph_evaluation else None,
            ),
        ]
        return RiskCheckResponse(
            request_id=request_id,
            event_id=event_id,
            assessment_id=assessment_id,
            scenario=request.scenario,
            stage=self.stage,
            final_score=fusion.score,
            risk_level=fusion.risk_level,
            decision=fusion.decision,
            hit_count=len(evaluation.hits),
            hits=[RuleHitResponse(**payload) for payload in hit_payloads],
            score_breakdown=ScoreBreakdown(
                formula="min(100, highest_rule_score + other_rules_score_sum × additional_weight)",
                highest_rule_score=evaluation.highest_rule_score,
                other_rules_score_sum=evaluation.other_rules_score_sum,
                additional_weight=evaluation.additional_weight,
                weighted_addition=evaluation.weighted_addition,
                raw_score=evaluation.raw_score,
                capped_at_100=evaluation.raw_score > 100,
            ),
            fusion_breakdown=FusionBreakdown(
                formula="min(100, highest_component_score + other_component_scores_sum × additional_weight)",
                component_scores=fusion.component_scores,
                primary_component=fusion.primary_component,
                primary_score=fusion.primary_score,
                other_components_score_sum=fusion.other_components_score_sum,
                additional_weight=fusion.additional_weight,
                weighted_addition=fusion.weighted_addition,
                raw_score=fusion.raw_score,
                capped_at_100=fusion.raw_score > 100,
            ),
            components=components,
            appeal=appeal_option,
            message=decision_reason,
        )

    @staticmethod
    async def _load_rules(scenario: str, session: AsyncSession) -> list[RiskRule]:
        result = await session.scalars(
            select(RiskRule)
            .where(RiskRule.is_enabled.is_(True), RiskRule.deleted_at.is_(None))
            .order_by(RiskRule.priority.desc())
        )
        return [rule for rule in result.all() if scenario in rule.scenarios]


decision_engine = DecisionEngine()
