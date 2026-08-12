"""ORM 公共基类和跨表枚举。

业务表定义位于 :mod:`app.models_business`，风控核心表定义位于
:mod:`app.models_risk`。拆分文件是为了明确“银行业务层”和“风控平台层”的边界。
"""

from enum import StrEnum
from typing import TypeVar

from sqlalchemy import Enum, MetaData
from sqlalchemy.orm import DeclarativeBase


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class EventType(StrEnum):
    LOGIN = "登录"
    TRANSFER = "转账"
    CARD_PAYMENT = "信用卡交易"
    LOAN_APPLICATION = "贷款申请"


class RuleEventType(StrEnum):
    LOGIN = "登录"
    TRANSFER = "转账"
    CARD_PAYMENT = "信用卡交易"
    LOAN_APPLICATION = "贷款申请"
    COMMON = "通用"


class RiskLevel(StrEnum):
    LOW = "低"
    MEDIUM = "中"
    HIGH = "高"
    EXTREME = "极高"


class Decision(StrEnum):
    PASS = "通过"
    FLAG = "标记"
    MANUAL_REVIEW = "人工审核"
    REJECT = "拒绝"


EnumT = TypeVar("EnumT", bound=StrEnum)


def enum_type(enum_class: type[EnumT], name: str) -> Enum:
    """让数据库保存枚举的中文/业务值，而不是 Python 成员名。"""

    return Enum(
        enum_class,
        values_callable=lambda members: [member.value for member in members],
        name=name,
        validate_strings=True,
    )


# 导入后，Base.metadata 才能一次性包含全部 17 张表。
# 放在文件尾部可以避免模型模块导入 Base 时产生循环导入。
from app import models_business as models_business  # noqa: E402,F401
from app import models_risk as models_risk  # noqa: E402,F401

