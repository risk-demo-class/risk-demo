"""
业务实体校验器: 集中处理银行风控场景的实体存在性、归属一致性、状态校验.
所有校验失败都抛 HTTPException, 由 FastAPI 统一返回 4xx 响应.

6 种校验:
  1. 用户存在性校验 (UserInfo)
  2. 交易存在性校验 (Transaction, for 转账/信用卡)
  3. 贷款申请存在性校验 (LoanApplication, for 贷款)
  4. 归属一致性校验 (txn.user_id == request.user_id)
  5. 用户状态校验 (UserInfo.status == "active")
  6. 卡状态校验 (BankCard.status == "active")
"""
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.models import BankCard, LoanApplication, Transaction, UserInfo
from bank_risk.app.schemas import RiskCheckRequest

logger = logging.getLogger(__name__)


async def validate_event(db: AsyncSession, request: RiskCheckRequest) -> None:
    """6 种校验, 失败抛 HTTPException.

    校验顺序:
      1+5. 用户存在性 + 用户状态 (一次查询拿 user 对象, 两步校验)
      2+4. 交易存在性 + 归属一致性 (转账/信用卡场景)
      3.   贷款申请存在性 (贷款场景)
      6.   卡状态 (有 card_id 时)
    """
    # ---- 1. 用户存在性 + 5. 用户状态 ----
    user = (await db.execute(
        select(UserInfo).where(UserInfo.user_id == request.user_id)
    )).scalar_one_or_none()
    if not user:
        logger.warning("校验失败: 用户不存在 user_id=%s", request.user_id)
        raise HTTPException(status_code=404, detail=f"用户ID不存在: {request.user_id}")
    if getattr(user, "status", None) != "active":
        logger.warning("校验失败: 用户状态异常 user_id=%s, status=%s", request.user_id, getattr(user, "status", None))
        raise HTTPException(
            status_code=403,
            detail=f"用户状态异常: {getattr(user, 'status', None)}, 非 active 不可交易",
        )

    # ---- 2. 交易存在性 + 4. 归属一致性 (转账/信用卡) ----
    if request.event_type in ("转账", "信用卡"):
        txn = (await db.execute(
            select(Transaction).where(Transaction.txn_id == request.source_id)
        )).scalar_one_or_none()
        if not txn:
            logger.warning("校验失败: 交易不存在 source_id=%s", request.source_id)
            raise HTTPException(status_code=404, detail=f"交易ID不存在: {request.source_id}")
        # 归属一致性: 防水平越权 (拿别人交易 + 自己 user_id 绕过风控)
        if txn.user_id != request.user_id:
            logger.warning(
                "安全告警: 交易归属不一致 txn_id=%s, owner=%s, request_user=%s",
                request.source_id, txn.user_id, request.user_id,
            )
            raise HTTPException(
                status_code=403,
                detail=f"交易 {request.source_id} 属于用户 {txn.user_id}, 与请求用户 {request.user_id} 不一致",
            )

    # ---- 3. 贷款申请存在性 (贷款) ----
    elif request.event_type == "贷款":
        loan = (await db.execute(
            select(LoanApplication).where(LoanApplication.loan_id == request.source_id)
        )).scalar_one_or_none()
        if not loan:
            logger.warning("校验失败: 贷款申请不存在 source_id=%s", request.source_id)
            raise HTTPException(status_code=404, detail=f"贷款申请ID不存在: {request.source_id}")

    # 登录场景: source_id 是 login_id, 不做存在性校验 (登录日志可能尚未落库)

    # ---- 6. 卡状态校验 (有 card_id 时) ----
    if request.card_id:
        card = (await db.execute(
            select(BankCard).where(BankCard.card_id == request.card_id)
        )).scalar_one_or_none()
        if not card:
            logger.warning("校验失败: 银行卡不存在 card_id=%s", request.card_id)
            raise HTTPException(status_code=404, detail=f"银行卡ID不存在: {request.card_id}")
        if getattr(card, "status", None) != "active":
            logger.warning("校验失败: 银行卡状态异常 card_id=%s, status=%s", request.card_id, getattr(card, "status", None))
            raise HTTPException(
                status_code=403,
                detail=f"银行卡状态异常: {getattr(card, 'status', None)}, 非 active 不可交易",
            )
