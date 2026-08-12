"""AI 助手的安全占位接口；真实 Agent 在第四阶段接入。"""

from fastapi import APIRouter

from app.schemas import AgentChatRequest, AgentChatResponse


router = APIRouter(prefix="/api/agent", tags=["AI风控助手"])


@router.post("/chat", response_model=AgentChatResponse)
async def chat(_: AgentChatRequest) -> AgentChatResponse:
    return AgentChatResponse(
        reply=(
            "核心风控与管理页面已经可用；AI Agent 将在第四阶段接入。"
            "当前请使用仪表盘、案件、评估历史和客户画像查看真实数据。"
        ),
        model_available=False,
    )


@router.post("/clear")
async def clear() -> dict[str, str]:
    return {"detail": "当前阶段未保存AI会话"}
