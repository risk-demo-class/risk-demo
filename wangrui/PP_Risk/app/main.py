"""
PP-Risk 应用主入口模块。

本模块负责创建和配置 FastAPI 应用实例，包括：
- 数据库生命周期管理（启动时建表、关闭时释放连接）
- 静态文件挂载
- Web 页面路由和 Agent API 路由注册
- 健康检查接口
- 风险检测核心 API 接口
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import create_schema, engine, get_db
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.event import process_event
from app.web import router as web_router
from app.agent.router import router as agent_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """FastAPI 应用生命周期管理器。

    应用启动时自动创建数据库表结构（create_schema），
    应用关闭时自动释放数据库连接池（engine.dispose）。
    """
    # 启动阶段：确保数据库表结构已创建
    await create_schema()
    try:
        # 应用运行中，交出控制权
        yield
    finally:
        # 关闭阶段：释放数据库引擎的连接池资源
        await engine.dispose()


# 创建 FastAPI 应用实例
app = FastAPI(title=settings.APP_NAME, version="0.2.0", lifespan=lifespan)

# 挂载静态文件目录，用于提供 CSS、JS、图片等静态资源
app.mount("/static", StaticFiles(directory="static"), name="static")

# 注册 Web 页面路由（前端界面相关）
app.include_router(web_router)

# 注册 AI Agent API 路由（智能体对话相关接口）
app.include_router(agent_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """健康检查接口。

    用于监控和负载均衡器探测服务是否正常运行。
    返回服务状态和名称。
    """
    return {"status": "ok", "service": "pp-risk"}


@app.post("/api/risk/check", response_model=RiskCheckResponse)
async def risk_check(
    request: RiskCheckRequest, db: AsyncSession = Depends(get_db)
) -> RiskCheckResponse:
    """风险检测核心接口。

    接收用户的事件描述，通过 AI 分析后返回风险评估结果。

    Args:
        request: 风险检测请求体，包含需要分析的事件信息
        db:        通过依赖注入获取的异步数据库会话

    Returns:
        RiskCheckResponse: 风险评估结果，包含风险等级、分析和建议

    Raises:
        HTTPException 400: 请求参数不合法（如事件内容为空）
        HTTPException 403: 权限不足（如超出调用频率限制）
    """
    try:
        return await process_event(db, request)
    except ValueError as exc:
        # 参数校验失败 → 400 Bad Request
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        # 权限校验失败 → 403 Forbidden
        raise HTTPException(status_code=403, detail=str(exc)) from exc


# 直接运行本模块时启动开发服务器
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
