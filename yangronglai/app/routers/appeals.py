"""Client appeal entry points and token-protected internal reconsideration."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import (
    AppealEvidenceRequest,
    AppealResponse,
    AppealReviewRequest,
    AppealStatus,
    AppealSubmissionRequest,
)
from app.service.appeals import (
    AppealServiceError,
    add_client_evidence,
    get_client_appeal,
    list_internal_appeals,
    review_internal_appeal,
    submit_client_appeal,
)


router = APIRouter(prefix="/api", tags=["appeals"])


def _raise_http(exc: AppealServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/client/appeals", response_model=AppealResponse)
async def create_client_appeal(
    data: AppealSubmissionRequest,
    http_request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result, created = await submit_client_appeal(session, data)
    except AppealServiceError as exc:
        _raise_http(exc)
    http_request.state.risk_scenario = result["scenario"]
    http_request.state.outcome_override = "APPEAL_SUBMITTED" if created else "APPEAL_IDEMPOTENT_REPLAY"
    response.status_code = 201 if created else 200
    return result


@router.get("/client/appeals/{appeal_id}", response_model=AppealResponse)
async def query_client_appeal(
    appeal_id: str,
    http_request: Request,
    appeal_token: str = Header(default="", alias="X-Appeal-Token"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await get_client_appeal(session, appeal_id, appeal_token)
    except AppealServiceError as exc:
        _raise_http(exc)
    http_request.state.risk_scenario = result["scenario"]
    http_request.state.outcome_override = "APPEAL_STATUS_QUERIED"
    return result


@router.post("/client/appeals/{appeal_id}/evidence", response_model=AppealResponse)
async def add_appeal_evidence(
    appeal_id: str,
    data: AppealEvidenceRequest,
    http_request: Request,
    appeal_token: str = Header(default="", alias="X-Appeal-Token"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await add_client_evidence(session, appeal_id, appeal_token, data)
    except AppealServiceError as exc:
        _raise_http(exc)
    http_request.state.risk_scenario = result["scenario"]
    http_request.state.outcome_override = "APPEAL_EVIDENCE_RECEIVED"
    return result


@router.get("/internal/appeals")
async def internal_appeal_queue(
    http_request: Request,
    status: AppealStatus | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    internal_token: str = Header(default="", alias="X-Internal-Approval-Token"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await list_internal_appeals(
            session,
            internal_token,
            status.value if status else None,
            page,
            page_size,
        )
    except AppealServiceError as exc:
        _raise_http(exc)
    http_request.state.outcome_override = "INTERNAL_APPEAL_QUEUE_QUERIED"
    return result


@router.post("/internal/appeals/{appeal_id}/review", response_model=AppealResponse)
async def internal_appeal_review(
    appeal_id: str,
    data: AppealReviewRequest,
    http_request: Request,
    internal_token: str = Header(default="", alias="X-Internal-Approval-Token"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await review_internal_appeal(session, appeal_id, internal_token, data)
    except AppealServiceError as exc:
        _raise_http(exc)
    http_request.state.risk_scenario = result["scenario"]
    http_request.state.outcome_override = result["status"]
    return result

