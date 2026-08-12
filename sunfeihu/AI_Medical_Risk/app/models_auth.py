"""后台登录与用户管理模型。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AppUser(Base):
    __tablename__ = "app_user"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, comment="登录名")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="Argon2 密码摘要")
    display_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="显示名称")
    role: Mapped[str] = mapped_column(
        Enum("admin", "reviewer", "analyst", "viewer", name="app_user_role_enum"),
        nullable=False, server_default="viewer", comment="角色",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    create_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=datetime.now)
    update_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, onupdate=datetime.now,
    )

    __table_args__ = (
        Index("idx_app_user_role_active", "role", "is_active"),
    )
