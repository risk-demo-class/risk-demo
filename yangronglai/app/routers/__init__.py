"""API router exports."""

from app.routers.agent import router as agent_router
from app.routers.appeals import router as appeal_router
from app.routers.health import router as health_router
from app.routers.graph import router as graph_router
from app.routers.models import router as model_router
from app.routers.operations import router as operations_router
from app.routers.pages import router as page_router
from app.routers.risk import router as risk_router

__all__ = [
    "agent_router",
    "appeal_router",
    "graph_router",
    "health_router",
    "model_router",
    "operations_router",
    "page_router",
    "risk_router",
]
