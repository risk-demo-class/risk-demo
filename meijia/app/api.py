"""兼容入口：新代码请从 app.routers 导入模块化路由。"""

from fastapi import APIRouter

from app.routers import ALL_ROUTERS

api_router = APIRouter()
for _router in ALL_ROUTERS[1:]:  # 排除 HTML 页面路由
    api_router.include_router(_router)

__all__ = ["api_router"]
