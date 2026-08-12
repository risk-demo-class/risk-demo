from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.agent.service import chat, clear, confirm, enabled
from app.config import settings

router = APIRouter(prefix="/api/agent", tags=["agent"])

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    user_id: str = Field(min_length=1, max_length=50)
    session_id: str | None = None

class ConfirmRequest(BaseModel):
    token: str
    user_id: str
    session_id: str

class ClearRequest(BaseModel):
    user_id: str
    session_id: str

@router.get("/status")
async def status() -> dict[str, object]:
    return {"enabled": enabled(), "provider": settings.LLM_PROVIDER, "model": settings.LLM_MODEL_NAME}

@router.post("/chat")
async def agent_chat(payload: ChatRequest) -> dict[str, str | None]:
    try:
        reply, session_id, confirmation_token = await chat(payload.message, payload.user_id, payload.session_id)
        return {"reply": reply, "session_id": session_id, "confirmation_token": confirmation_token}
    except RuntimeError as exc: raise HTTPException(503, str(exc)) from exc
    except PermissionError as exc: raise HTTPException(403, str(exc)) from exc

@router.post("/confirm")
async def agent_confirm(payload: ConfirmRequest) -> dict[str, object]:
    try: return await confirm(payload.token, payload.user_id, payload.session_id)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    except PermissionError as exc: raise HTTPException(403, str(exc)) from exc

@router.post("/clear")
async def agent_clear(payload: ClearRequest) -> dict[str, bool]:
    return {"cleared": await clear(payload.session_id, payload.user_id)}
