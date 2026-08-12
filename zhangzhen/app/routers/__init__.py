"""FastAPI 路由包。"""

from app.routers.health import router as health_router

__all__ = ["health_router"]

