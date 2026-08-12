"""规则、案件和黑名单写操作的统一审计入口。"""

from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_risk import ActionTargetType, ActionType, RiskActionLog


async def record_action(
    db: AsyncSession,
    *,
    operator: str,
    action_type: ActionType,
    target_type: ActionTargetType,
    target_id: str,
    before_value: dict[str, Any] | None = None,
    after_value: dict[str, Any] | None = None,
    ip: str | None = None,
    remark: str | None = None,
) -> None:
    """只写入当前事务，不自行提交，保证业务变更和审计原子提交。"""

    db.add(
        RiskActionLog(
            operator=operator,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            before_value=jsonable_encoder(before_value) if before_value else None,
            after_value=jsonable_encoder(after_value) if after_value else None,
            ip=ip,
            remark=remark,
        )
    )


def selected_fields(instance: object, *fields: str) -> dict[str, Any]:
    return jsonable_encoder({field: getattr(instance, field, None) for field in fields})
