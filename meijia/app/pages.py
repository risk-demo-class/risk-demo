"""兼容入口：页面路由已迁移至 app.routers.pages。"""

from app.routers.pages import router as page_router

__all__ = ["page_router"]
