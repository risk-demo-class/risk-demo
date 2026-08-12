"""系统登录与权限相关 ORM。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Enum, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SysUser(Base):
    """后台操作用户，只保留风控管理员和审核员两个角色。"""

    __tablename__ = "sys_user"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, comment="登录账号")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="PBKDF2 密码摘要")
    display_name: Mapped[str] = mapped_column(String(50), nullable=False, comment="显示名称")
    role: Mapped[str] = mapped_column(
        Enum("ADMIN", "REVIEWER", name="sys_user_role_enum"),
        nullable=False,
        comment="ADMIN=风控管理员, REVIEWER=审核员",
    )
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="1=启用, 0=禁用")
    last_login_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now,
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, server_default=func.now(), default=datetime.now, onupdate=datetime.now,
    )

    __table_args__ = (
        Index("idx_sys_user_role", "role"),
        Index("idx_sys_user_active", "is_active"),
    )

    @property
    def role_label(self) -> str:
        return "风控管理员" if self.role == "ADMIN" else "审核员"

