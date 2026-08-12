"""八类银行黑名单的前置检查。"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_risk import BlacklistType, RiskBlacklist
from app.service.context import RiskContext


@dataclass(frozen=True, slots=True)
class BlacklistHit:
    blacklist_id: int
    blacklist_type: BlacklistType
    reason: str | None


def _candidate_pairs(context: RiskContext) -> list[tuple[BlacklistType, str]]:
    """返回已经按硬策略优先级排序的 (类型, 值)。"""

    pairs: list[tuple[BlacklistType, str | None]] = [
        (BlacklistType.USER, context.request.user_id),
        (BlacklistType.ID_CARD, context.customer.id_card_hash),
        (BlacklistType.BANK_ACCOUNT, context.account.account_id if context.account else None),
        (BlacklistType.BANK_ACCOUNT, context.account.account_no_hash if context.account else None),
        (BlacklistType.BANK_CARD, context.card.card_id if context.card else None),
        (BlacklistType.BANK_CARD, context.card.card_no_hash if context.card else None),
        (BlacklistType.BENEFICIARY_ACCOUNT, context.beneficiary_account_hash),
        (BlacklistType.DEVICE_FINGERPRINT, context.device_id),
        (
            BlacklistType.DEVICE_FINGERPRINT,
            context.device.fingerprint_hash if context.device else None,
        ),
        (BlacklistType.IP, context.ip),
        (BlacklistType.MOBILE, context.customer.mobile_hash),
    ]
    return [(item_type, value) for item_type, value in pairs if value]


async def check_all_blacklists(
    db: AsyncSession,
    context: RiskContext,
    *,
    now: datetime | None = None,
) -> BlacklistHit | None:
    """一次查询完成候选对象检查，再按业务优先级选择第一个命中。"""

    candidates = _candidate_pairs(context)
    if not candidates:
        return None

    check_time = now or context.event_time
    pair_conditions = [
        and_(
            RiskBlacklist.blacklist_type == blacklist_type,
            RiskBlacklist.blacklist_value == value,
        )
        for blacklist_type, value in candidates
    ]
    result = await db.execute(
        select(RiskBlacklist).where(
            RiskBlacklist.deleted_at.is_(None),
            or_(RiskBlacklist.expire_time.is_(None), RiskBlacklist.expire_time > check_time),
            or_(*pair_conditions),
        )
    )
    rows = result.scalars().all()
    matched = {(row.blacklist_type, row.blacklist_value): row for row in rows}

    for pair in candidates:
        row = matched.get(pair)
        if row is not None:
            return BlacklistHit(
                blacklist_id=row.blacklist_id,
                blacklist_type=row.blacklist_type,
                reason=row.reason,
            )
    return None

