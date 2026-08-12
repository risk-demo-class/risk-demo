"""银行业务实体存在性、事件类型和归属关系校验。"""

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EventType
from app.models_business import (
    AccountStatus,
    BankAccount,
    BankCard,
    BankTransaction,
    CardStatus,
    CustomerInfo,
    CustomerStatus,
    LoanApplication,
    LoginLog,
    TransactionType,
)
from app.schemas import RiskCheckRequest
from app.service.context import RiskContext


def _not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{entity}不存在")


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


async def _load_customer(db: AsyncSession, user_id: str) -> CustomerInfo:
    customer = await db.get(CustomerInfo, user_id)
    if customer is None:
        raise _not_found("客户")
    if customer.status is not CustomerStatus.NORMAL:
        raise _bad_request(f"客户状态为 {customer.status.value}，不允许发起该业务")
    return customer


async def validate_business_entity(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> RiskContext:
    """根据 event_type 定位 source_id，并阻止水平越权。"""

    customer = await _load_customer(db, request.user_id)

    if request.event_type is EventType.LOGIN:
        login = await db.get(LoginLog, request.source_id)
        if login is None:
            raise _not_found("登录日志")
        if login.user_id != request.user_id:
            raise _forbidden("该登录日志不属于当前客户")
        return RiskContext(
            request=request,
            customer=customer,
            login=login,
            event_time=login.login_at,
            device_id=login.device_id,
            ip=login.ip,
            geo=login.geo,
        )

    if request.event_type in {EventType.TRANSFER, EventType.CARD_PAYMENT}:
        transaction = await db.get(BankTransaction, request.source_id)
        if transaction is None:
            raise _not_found("银行交易")
        if transaction.user_id != request.user_id:
            raise _forbidden("该交易不属于当前客户")
        if transaction.amount <= Decimal("0"):
            raise _bad_request("交易金额必须大于0")

        expected_type = (
            TransactionType.TRANSFER
            if request.event_type is EventType.TRANSFER
            else TransactionType.CARD_PAYMENT
        )
        if transaction.txn_type is not expected_type:
            raise _bad_request(
                f"source_id 对应 {transaction.txn_type.value}，与事件 {request.event_type.value} 不匹配"
            )

        account: BankAccount | None = None
        card: BankCard | None = None
        if transaction.from_account_id:
            account = await db.get(BankAccount, transaction.from_account_id)
            if account is None:
                raise _not_found("付款账户")
            if account.user_id != request.user_id:
                raise _forbidden("付款账户不属于当前客户")
            if account.status is not AccountStatus.NORMAL:
                raise _bad_request(f"付款账户状态为 {account.status.value}")

        if transaction.from_card_id:
            card = await db.get(BankCard, transaction.from_card_id)
            if card is None:
                raise _not_found("付款卡")
            if card.user_id != request.user_id:
                raise _forbidden("付款卡不属于当前客户")
            if card.status is not CardStatus.NORMAL:
                raise _bad_request(f"付款卡状态为 {card.status.value}")

        if request.event_type is EventType.TRANSFER and account is None:
            raise _bad_request("转账事件缺少付款账户")
        if request.event_type is EventType.CARD_PAYMENT and card is None:
            raise _bad_request("信用卡交易缺少付款卡")

        return RiskContext(
            request=request,
            customer=customer,
            transaction=transaction,
            account=account,
            card=card,
            event_time=transaction.txn_time,
            device_id=transaction.device_id,
            ip=transaction.ip,
            geo=transaction.geo,
            beneficiary_account_hash=transaction.beneficiary_account_hash,
        )

    if request.event_type is EventType.LOAN_APPLICATION:
        loan = await db.get(LoanApplication, request.source_id)
        if loan is None:
            raise _not_found("贷款申请")
        if loan.user_id != request.user_id:
            raise _forbidden("该贷款申请不属于当前客户")
        if loan.amount <= Decimal("0"):
            raise _bad_request("贷款申请金额必须大于0")
        if not 1 <= loan.term_months <= 360:
            raise _bad_request("贷款期限必须在1至360个月之间")
        if not Decimal("0") <= loan.debt_ratio <= Decimal("1"):
            raise _bad_request("负债率必须在0至1之间")
        return RiskContext(
            request=request,
            customer=customer,
            loan=loan,
            event_time=loan.apply_at,
            device_id=loan.device_id,
            ip=loan.ip,
            geo=customer.home_city,
        )

    # Pydantic 已限制枚举；保留兜底是为了 Service 被内部代码直接调用时仍安全。
    raise _bad_request("不支持的事件类型")

