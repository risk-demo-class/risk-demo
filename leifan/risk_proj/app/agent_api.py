from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from openai import APIError
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.agent_service import run_agent
from app.auth import AuthenticatedStaff, require_administrator
from app.database import get_db


router = APIRouter(prefix="/api/agent", tags=["admin-agent"])


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=200)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请输入需要 Agent 执行的任务")
        return value


@router.get("/capabilities")
def capabilities(
    staff: AuthenticatedStaff = Depends(require_administrator),
) -> dict:
    return {
        "history_enabled": False,
        "capabilities": [
            "查询风险概览、订单、用户及评分详情",
            "查询并处置人工审核案件",
            "管理规则启停、档位分数并重算全部评分",
            "查询、新增和更新黑护照名单",
            "查询审计日志和员工账号状态",
        ],
    }


@router.post("/run")
def run_admin_agent(
    payload: AgentRequest,
    staff: AuthenticatedStaff = Depends(require_administrator),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return run_agent(payload.message, db, staff)
    except APIError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="模型服务暂时不可用，请稍后重试") from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
