"""Router 层：只负责接收请求、注入数据库会话并转交 Service。"""

from collections.abc import Generator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.event import process_event


risk_router = APIRouter(prefix="/api/risk", tags=["教育风控"])


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@risk_router.post("/check", response_model=RiskCheckResponse)
def check_risk(request: RiskCheckRequest, session: Session = Depends(get_session)) -> RiskCheckResponse:
    return process_event(session, request)
