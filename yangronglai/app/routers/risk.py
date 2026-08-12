"""Rule evaluation, catalog and assessment endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine.decision import decision_engine
from app.engine.rule_catalog import DEMO_EVENTS
from app.models_risk import RiskAssessment, RiskRule
from app.observability import pseudonymize, set_scenario
from app.schemas import (
    AssessmentResponse,
    RiskCheckRequest,
    RiskCheckResponse,
    RuleSummaryResponse,
)
from app.service.event import process_event
from app.service.features import RiskValidationError


router = APIRouter(prefix="/api/risk", tags=["risk"])
validation_logger = logging.getLogger("bankrisk.validation")


@router.get("/capabilities")
async def capabilities() -> dict:
    return decision_engine.capabilities()


@router.get("/demo-events")
async def demo_events() -> dict:
    return {"items": DEMO_EVENTS}


@router.get("/rules", response_model=list[RuleSummaryResponse])
async def list_rules(session: AsyncSession = Depends(get_db)) -> list[RiskRule]:
    result = await session.scalars(select(RiskRule).order_by(RiskRule.rule_id))
    return list(result.all())


@router.get("/assessments/{assessment_id}", response_model=AssessmentResponse)
async def get_assessment(
    assessment_id: str,
    session: AsyncSession = Depends(get_db),
) -> RiskAssessment:
    assessment = await session.get(RiskAssessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    return assessment


@router.post("/check", response_model=RiskCheckResponse)
async def risk_check(
    payload: RiskCheckRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_db),
) -> RiskCheckResponse:
    scenario = payload.scenario.value
    http_request.state.risk_scenario = scenario
    set_scenario(scenario)
    try:
        result = await process_event(payload, session)
    except RiskValidationError as exc:
        validation_logger.info(
            "risk_validation_rejected",
            extra={
                "event_data": {
                    "outcome": "VALIDATION_ERROR",
                    "user_ref": pseudonymize(payload.user_id),
                    "source_ref": pseudonymize(payload.source_id),
                    "reason": str(exc),
                }
            },
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    http_request.state.risk_decision = result.decision.value
    http_request.state.risk_score = result.final_score
    return result
