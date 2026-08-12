"""
银行风控系统 - 请求校验器
========================
校验风控检查请求的合法性:
  1. 用户是否存在且状态正常
  2. 卡是否属于该用户且状态正常
  3. 事件类型是否合法
  4. 金额是否在合理范围

校验失败 → 立即拒绝, 不进入风控决策流水线.
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import UserInfo, BankCard
from app.schemas import RiskCheckRequest

logger = logging.getLogger(__name__)

# 合法事件类型 (PRD 第 5 节)
VALID_EVENT_TYPES = {
    "REGISTER", "BIND_CARD", "CARD_APPLY", "LOAN_APPLY", "LIMIT_ADJUST",
    "LOGIN", "TRANSFER", "PAYMENT", "WITHDRAW", "REPAY",
    "CHANGE_PWD", "CHANGE_PHONE", "UPDATE_PROFILE",
    "DISBURSE", "OVERDUE", "DISPUTE", "FROZEN", "SAR", "REVIEW",
}


async def validate_risk_check_request(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> None:
    """
    校验风控检查请求. 任一校验失败 → raise ValueError.

    校验规则:
      1. event_type 必须是合法值
      2. user_id 对应的用户存在且状态正常
      3. card_id (如有) 存在且属于该用户, 状态正常
      4. amount (如有) >= 0
    """
    errors = []

    # 1. 事件类型
    if request.event_type not in VALID_EVENT_TYPES:
        errors.append(f"非法事件类型: {request.event_type}")

    # 2. 用户
    user = (await db.execute(
        select(UserInfo.status).where(UserInfo.user_id == request.user_id)
    )).scalar_one_or_none()
    if user is None:
        errors.append(f"用户不存在: user_id={request.user_id}")
    elif user != 1:
        status_names = {1: "正常", 2: "冻结", 3: "止付", 4: "销户"}
        errors.append(f"用户状态异常: {status_names.get(user, '未知')}")

    # 3. 卡
    if request.card_id:
        card = (await db.execute(
            select(BankCard.user_id, BankCard.status).where(
                BankCard.card_id == request.card_id
            )
        )).first()
        if card is None:
            errors.append(f"银行卡不存在: card_id={request.card_id}")
        else:
            if card.user_id != request.user_id:
                errors.append(f"银行卡不属于该用户: card_id={request.card_id}, user_id={request.user_id}")
            if card.status != 1:
                status_names = {1: "正常", 2: "冻结", 3: "止付", 4: "挂失", 5: "销户"}
                errors.append(f"银行卡状态异常: {status_names.get(card.status, '未知')}")

    # 4. 金额
    if request.amount is not None and request.amount < 0:
        errors.append(f"金额不能为负数: {request.amount}")

    if errors:
        msg = "; ".join(errors)
        logger.warning("请求校验失败: %s", msg)
        raise ValueError(msg)
