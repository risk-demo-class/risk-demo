"""Router 层：沿用源码的教育黑名单运营管理 API。"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.routers.risk import get_session
from app.schemas import BlacklistCreate, BlacklistItem, BlacklistListResponse
from app.service.case import add_blacklist, list_blacklists, remove_blacklist


blacklist_router = APIRouter(prefix="/api/blacklist", tags=["教育风控黑名单"])


@blacklist_router.get("", response_model=BlacklistListResponse)
def get_blacklist(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    blacklist_type: Literal["用户", "证件哈希", "设备哈希"] | None = None,
    session: Session = Depends(get_session),
) -> BlacklistListResponse:
    total, items = list_blacklists(session, page, page_size, blacklist_type)
    return BlacklistListResponse(
        items=[BlacklistItem.model_validate(item, from_attributes=True) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@blacklist_router.post("", response_model=BlacklistItem, status_code=status.HTTP_201_CREATED)
def create_blacklist(data: BlacklistCreate, session: Session = Depends(get_session)) -> BlacklistItem:
    item = add_blacklist(session, data)
    return BlacklistItem.model_validate(item, from_attributes=True)


@blacklist_router.delete("/{blacklist_id}")
def delete_blacklist(blacklist_id: int, session: Session = Depends(get_session)) -> dict[str, str]:
    if not remove_blacklist(session, blacklist_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="黑名单记录不存在")
    return {"detail": "已移除"}
