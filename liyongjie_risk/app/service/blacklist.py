"""
银行风控系统 - 黑名单服务
========================
黑名单检查: 判断一个值是否命中有效黑名单.

【检查维度 (PRD 第 7.8 节)】
  type=1 设备, type=2 IP, type=3 银行卡号, type=4 身份证, type=5 手机号

【命中条件】
  status=1 (有效) 且 (expire_at IS NULL 或 expire_at > NOW())

【名单来源】
  内部/公安涉诈/法院/同业/外部
"""
import logging
from datetime import datetime

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BlacklistExtra

logger = logging.getLogger(__name__)


async def check_blacklist(
    db: AsyncSession,
    bl_type: int,
    value: str,
) -> bool:
    """
    检查 value 是否在指定类型的有效黑名单中.

    Args:
        db: 数据库 Session
        bl_type: 名单类型 (1=设备, 2=IP, 3=银行卡号, 4=身份证, 5=手机号)
        value: 待检查的值 (哈希或原文)

    Returns:
        True = 命中黑名单, False = 未命中
    """
    now = datetime.now()
    stmt = select(BlacklistExtra.entry_id).where(
        BlacklistExtra.type == bl_type,
        BlacklistExtra.value == value,
        BlacklistExtra.status == 1,
        or_(
            BlacklistExtra.expire_at.is_(None),
            BlacklistExtra.expire_at > now,
        ),
    ).limit(1)
    result = (await db.execute(stmt)).scalar_one_or_none()
    hit = result is not None
    if hit:
        logger.info("黑名单命中: type=%d, value=%s...", bl_type, value[:16] if len(value) > 16 else value)
    return hit


async def check_all_blacklists(
    db: AsyncSession,
    user_id: int,
    card_id: int | None = None,
    device_id: int | None = None,
    ip: str | None = None,
    to_card_no_hash: str | None = None,
) -> str | None:
    """
    全维度黑名单检查, 短路返回第一个命中的维度.

    检查顺序 (按优先级):
      1. 用户身份证 (type=4)
      2. 收款卡号 (type=3)
      3. 设备 (type=1)
      4. IP (type=2)

    Returns:
        None = 全部通过; str = 命中的维度描述
    """
    from app.models import UserInfo, BankCard

    # 1. 用户身份证
    if user_id:
        user = (await db.execute(
            select(UserInfo.id_card_hash).where(UserInfo.user_id == user_id)
        )).scalar_one_or_none()
        if user and await check_blacklist(db, 4, user):
            return f"用户身份证在黑名单 (user_id={user_id})"

    # 2. 收款卡
    if to_card_no_hash:
        if await check_blacklist(db, 3, to_card_no_hash):
            return f"收款卡在黑名单"

    # 3. 出款卡
    if card_id:
        card = (await db.execute(
            select(BankCard.card_no_hash).where(BankCard.card_id == card_id)
        )).scalar_one_or_none()
        if card and await check_blacklist(db, 3, card):
            return f"出款卡在黑名单 (card_id={card_id})"

    # 4. 设备
    if device_id:
        from app.models import DeviceFingerprint
        device = (await db.execute(
            select(DeviceFingerprint.fingerprint_hash).where(
                DeviceFingerprint.device_id == device_id
            )
        )).scalar_one_or_none()
        if device and await check_blacklist(db, 1, device):
            return f"设备在黑名单 (device_id={device_id})"

    # 5. IP
    if ip:
        if await check_blacklist(db, 2, ip):
            return f"IP在黑名单 (ip={ip})"

    return None
