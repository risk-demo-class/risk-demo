"""Liveness and stage-readiness endpoints."""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.config import settings
from app.database import database_ping
from app.engine.model_manager import model_manager
from app.schemas import HealthResponse


router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        stage="complete-three-layer",
        timestamp=datetime.now(UTC),
        components=settings.enabled_components(),
    )


@router.get("/readiness")
async def readiness() -> dict:
    database_ready = await database_ping()
    model_ready = all(item["ready"] for item in model_manager.status().values())
    graph_ready = not settings.ENABLE_GRAPH_ENGINE or settings.GRAPH_BACKEND == "local" or bool(settings.NEO4J_PASSWORD)
    agent_ready = not settings.ENABLE_AGENT or settings.AGENT_MODE == "local" or bool(settings.LLM_API_KEY)
    return {
        "ready": database_ready and (not settings.ENABLE_MODEL_ENGINE or model_ready) and graph_ready and agent_ready,
        "stage": "complete-three-layer",
        "observability": {
            "format": "json-lines",
            "retention_days": settings.LOG_RETENTION_DAYS,
            "sensitive_identifiers": "hmac-pseudonymized",
            "alert_channel": "file+webhook" if settings.ALERT_WEBHOOK_URL else "file",
        },
        "appeals": {
            "client_submission": "ready",
            "window_days": settings.APPEAL_WINDOW_DAYS,
            "review_sla_days": settings.APPEAL_REVIEW_SLA_DAYS,
            "internal_review": "configured" if settings.APPEAL_REVIEW_TOKEN else "token-required",
        },
        "external_dependencies": {
            "database": "ready" if database_ready else "unavailable",
            "database_driver": settings.DB_DRIVER,
            "models": "ready" if model_ready else "unavailable",
            "graph": settings.GRAPH_BACKEND if graph_ready else "unavailable",
            "agent": settings.AGENT_MODE if agent_ready else "unavailable",
            "llm": "configured" if settings.LLM_API_KEY else "not-required-in-local-mode",
        },
    }
