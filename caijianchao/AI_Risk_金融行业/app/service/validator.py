"""
金融风控系统 - 业务校验服务
负责校验金融业务数据的合法性和一致性
"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccountInfo, TransactionOrder, LoanInfo, CreditCardInfo,
    UserOperationLog, AmlSuspiciousReport
)
from app.schemas import RiskCheckRequest


class ValidationError(Exception):
    """业务校验异常"""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


async def validate_account_exists(db: AsyncSession, account_id: str) -> AccountInfo:
    """校验账户是否存在"""
    result = await db.execute(
        select(AccountInfo).where(AccountInfo.account_id == account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise ValidationError("ACCOUNT_NOT_FOUND", f"账户不存在: {account_id}")
    return account


async def validate_account_active(db: AsyncSession, account_id: str) -> None:
    """校验账户状态是否正常"""
    account = await validate_account_exists(db, account_id)
    if account.account_status != "正常":
        raise ValidationError("ACCOUNT_INACTIVE", f"账户状态异常: {account.account_status}")


async def validate_transaction_exists(db: AsyncSession, txn_id: str) -> TransactionOrder:
    """校验交易记录是否存在"""
    result = await db.execute(
        select(TransactionOrder).where(TransactionOrder.txn_id == txn_id)
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise ValidationError("TRANSACTION_NOT_FOUND", f"交易记录不存在: {txn_id}")
    return txn


async def validate_transaction_amount(txn_amount: float, account_balance: float) -> None:
    """校验交易金额合法性"""
    if txn_amount <= 0:
        raise ValidationError("INVALID_AMOUNT", "交易金额必须大于0")
    if txn_amount > account_balance:
        raise ValidationError("INSUFFICIENT_BALANCE", f"余额不足: 需要{txn_amount}, 可用{account_balance}")


async def validate_daily_transaction_limit(db: AsyncSession, account_id: str, txn_amount: float) -> None:
    """校验日交易限额"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.sum(TransactionOrder.txn_amount)).where(
            TransactionOrder.account_id == account_id,
            TransactionOrder.txn_time >= today,
            TransactionOrder.txn_status == "成功"
        )
    )
    daily_total = result.scalar() or 0
    daily_limit = 500000  # 日限额50万
    if daily_total + txn_amount > daily_limit:
        raise ValidationError(
            "DAILY_LIMIT_EXCEEDED",
            f"超出日交易限额: 已交易{daily_total}, 本次{txn_amount}, 限额{daily_limit}"
        )


async def validate_loan_exists(db: AsyncSession, loan_id: str) -> LoanInfo:
    """校验贷款是否存在"""
    result = await db.execute(
        select(LoanInfo).where(LoanInfo.loan_id == loan_id)
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise ValidationError("LOAN_NOT_FOUND", f"贷款不存在: {loan_id}")
    return loan


async def validate_loan_status(loan: LoanInfo) -> None:
    """校验贷款状态"""
    if loan.repay_status not in ["正常", "逾期"]:
        raise ValidationError("LOAN_INACTIVE", f"贷款状态异常: {loan.repay_status}")


async def validate_credit_card_exists(db: AsyncSession, card_id: str) -> CreditCardInfo:
    """校验信用卡是否存在"""
    result = await db.execute(
        select(CreditCardInfo).where(CreditCardInfo.card_id == card_id)
    )
    card = result.scalar_one_or_none()
    if not card:
        raise ValidationError("CREDIT_CARD_NOT_FOUND", f"信用卡不存在: {card_id}")
    return card


async def validate_credit_limit(card: CreditCardInfo, txn_amount: float) -> None:
    """校验信用卡额度"""
    available_limit = card.total_limit - card.used_limit
    if txn_amount > available_limit:
        raise ValidationError(
            "CREDIT_LIMIT_EXCEEDED",
            f"超出信用卡额度: 需要{txn_amount}, 可用{available_limit}"
        )


async def validate_operation_log_exists(db: AsyncSession, op_id: int) -> UserOperationLog:
    """校验操作日志是否存在"""
    result = await db.execute(
        select(UserOperationLog).where(UserOperationLog.op_id == op_id)
    )
    op = result.scalar_one_or_none()
    if not op:
        raise ValidationError("OPERATION_NOT_FOUND", f"操作日志不存在: {op_id}")
    return op


async def validate_aml_report_exists(db: AsyncSession, report_id: int) -> AmlSuspiciousReport:
    """校验反洗钱报告是否存在"""
    result = await db.execute(
        select(AmlSuspiciousReport).where(AmlSuspiciousReport.report_id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise ValidationError("AML_REPORT_NOT_FOUND", f"反洗钱报告不存在: {report_id}")
    return report


async def validate_risk_check_request(db: AsyncSession, request: RiskCheckRequest) -> dict:
    """
    校验风控检查请求的完整性
    返回: 校验通过的业务实体字典
    """
    validated = {}
    
    # 1. 校验账户
    if request.account_id:
        account = await validate_account_exists(db, request.account_id)
        validated["account"] = account
        await validate_account_active(db, request.account_id)
    
    # 2. 根据事件类型校验关联业务
    if request.event_type in ["交易", "转账", "取现"]:
        if not request.source_id:
            raise ValidationError("MISSING_SOURCE_ID", "交易类事件必须提供source_id(txn_id)")
        txn = await validate_transaction_exists(db, request.source_id)
        validated["transaction"] = txn
        
        # 校验交易归属
        if request.account_id and txn.account_id != request.account_id:
            raise ValidationError(
                "TRANSACTION_OWNER_MISMATCH",
                f"交易{request.source_id}不属于账户{request.account_id}"
            )
    
    elif request.event_type == "贷款申请":
        if not request.source_id:
            raise ValidationError("MISSING_SOURCE_ID", "贷款申请事件必须提供source_id(loan_id)")
        loan = await validate_loan_exists(db, request.source_id)
        validated["loan"] = loan
        await validate_loan_status(loan)
        
        # 校验贷款归属
        if request.account_id and loan.account_id != request.account_id:
            raise ValidationError(
                "LOAN_OWNER_MISMATCH",
                f"贷款{request.source_id}不属于账户{request.account_id}"
            )
    
    elif request.event_type == "账户变更":
        if not request.source_id:
            raise ValidationError("MISSING_SOURCE_ID", "账户变更事件必须提供source_id(op_id)")
        try:
            op_id = int(request.source_id)
            op = await validate_operation_log_exists(db, op_id)
            validated["operation"] = op
            
            # 校验操作归属
            if request.account_id and op.account_id != request.account_id:
                raise ValidationError(
                    "OPERATION_OWNER_MISMATCH",
                    f"操作{request.source_id}不属于账户{request.account_id}"
                )
        except ValueError:
            raise ValidationError("INVALID_OP_ID", f"操作ID格式错误: {request.source_id}")
    
    elif request.event_type == "反洗钱预警":
        if not request.source_id:
            raise ValidationError("MISSING_SOURCE_ID", "反洗钱预警事件必须提供source_id(report_id)")
        try:
            report_id = int(request.source_id)
            report = await validate_aml_report_exists(db, report_id)
            validated["aml_report"] = report
            
            # 校验报告归属
            if request.account_id and report.account_id != request.account_id:
                raise ValidationError(
                    "AML_REPORT_OWNER_MISMATCH",
                    f"报告{request.source_id}不属于账户{request.account_id}"
                )
        except ValueError:
            raise ValidationError("INVALID_REPORT_ID", f"报告ID格式错误: {request.source_id}")
    
    elif request.event_type == "登录":
        # 登录事件只需校验账户存在
        if not request.account_id:
            raise ValidationError("MISSING_ACCOUNT_ID", "登录事件必须提供account_id")
    
    return validated


async def validate_blacklist_target(target_type: str, target_value: str) -> None:
    """校验黑名单目标类型和值的合法性"""
    valid_types = ["身份证", "手机号", "账户", "IP", "设备ID", "国家地区"]
    if target_type not in valid_types:
        raise ValidationError("INVALID_BLACKLIST_TYPE", f"无效的黑名单类型: {target_type}")
    
    if not target_value or not target_value.strip():
        raise ValidationError("EMPTY_BLACKLIST_VALUE", "黑名单值不能为空")
    
    # 根据类型做格式校验
    if target_type == "手机号" and not target_value.isdigit():
        raise ValidationError("INVALID_PHONE_FORMAT", "手机号格式错误")
    
    if target_type == "身份证" and len(target_value) != 18:
        raise ValidationError("INVALID_ID_CARD_FORMAT", "身份证号长度必须为18位")


async def validate_rule_condition(condition: dict) -> None:
    """校验规则条件表达式的合法性"""
    if not condition:
        raise ValidationError("EMPTY_CONDITION", "规则条件不能为空")
    
    # 递归校验条件
    def _validate_node(node: dict):
        if "and" in node or "or" in node:
            # 逻辑组合
            items = node.get("and") or node.get("or")
            if not isinstance(items, list) or len(items) < 2:
                raise ValidationError("INVALID_LOGIC_OP", "逻辑操作符必须包含至少2个子条件")
            for item in items:
                _validate_node(item)
        else:
            # 单条件
            required_fields = ["field", "op", "value"]
            for field in required_fields:
                if field not in node:
                    raise ValidationError("MISSING_FIELD", f"条件缺少必需字段: {field}")
            
            valid_ops = [">", ">=", "<", "<=", "==", "!=", "in", "not_in", "between"]
            if node["op"] not in valid_ops:
                raise ValidationError("INVALID_OPERATOR", f"无效的操作符: {node['op']}")
    
    _validate_node(condition)
