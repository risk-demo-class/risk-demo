"""FastAPI 路由包。"""

from app.routers.health import router as health_router
from app.routers.risk import router as risk_router

__all__ = ["health_router", "risk_router"]
