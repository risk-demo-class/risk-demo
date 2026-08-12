"""
金融风控特征工程模块
特征名与 risk_rule 表中的 rule_condition 字段完全对齐
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_, or_, desc, case as sql_case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccountInfo, TransactionOrder, TransactionType, ProductChannel,
    LoanInfo, RepaymentRecord, CreditCardInfo, CreditInquiryLog,
    UserOperationLog, AddressHistory, AccountBalanceLog
)


# ============================================================
# 事件级特征 (从当前交易/事件直接提取)
# ============================================================

async def compute_event_features(
    db: AsyncSession,
    account_id: str,
    event_data: dict
) -> dict:
    """
    从当前事件提取特征 (与 risk_rule 条件字段对齐)
    
    特征列表:
    - txn_amount: 当前交易金额
    - channel_type: 渠道类型 (线上/线下)
    - is_counter: 是否柜面渠道 (0/1)
    - hour: 交易小时 (0-23)
    - operation_interval_sec: 操作间隔秒数
    - country_code: 国家代码
    - from_account_type: 发起方账户类型
    - to_account_type: 对手方账户类型
    - device_env: 设备环境
    - loan_purpose: 贷款用途
    """
    features = {}
    
    # 交易金额
    features['txn_amount'] = float(event_data.get('txn_amount', 0))
    
    # 渠道信息
    channel_code = event_data.get('channel_code')
    if channel_code:
        stmt = select(ProductChannel).where(ProductChannel.channel_code == channel_code)
        result = await db.execute(stmt)
        channel = result.scalar_one_or_none()
        if channel:
            features['channel_type'] = channel.channel_type
            features['is_counter'] = channel.is_counter
        else:
            features['channel_type'] = '未知'
            features['is_counter'] = 0
    else:
        features['channel_type'] = '未知'
        features['is_counter'] = 0
    
    # 交易时间
    txn_time = event_data.get('txn_time')
    if txn_time:
        if isinstance(txn_time, str):
            txn_time = datetime.fromisoformat(txn_time)
        features['hour'] = txn_time.hour
    else:
        features['hour'] = datetime.now().hour
    
    # 操作间隔秒数
    request_time = event_data.get('request_time')
    if request_time and txn_time:
        if isinstance(request_time, str):
            request_time = datetime.fromisoformat(request_time)
        if isinstance(txn_time, str):
            txn_time = datetime.fromisoformat(txn_time)
        interval = (txn_time - request_time).total_seconds()
        features['operation_interval_sec'] = max(0, interval)
    else:
        features['operation_interval_sec'] = 999
    
    # 国家代码
    features['country_code'] = event_data.get('country_code', 'CN')
    
    # 账户类型
    stmt = select(AccountInfo.account_type).where(AccountInfo.account_id == account_id)
    result = await db.execute(stmt)
    from_type = result.scalar() or '个人'
    features['from_account_type'] = from_type
    
    # 对手方账户类型
    counterparty_account = event_data.get('counterparty_account')
    if counterparty_account:
        stmt = select(AccountInfo.account_type).where(AccountInfo.account_id == counterparty_account)
        result = await db.execute(stmt)
        to_type = result.scalar() or '个人'
        features['to_account_type'] = to_type
    else:
        features['to_account_type'] = '未知'
    
    # 设备环境
    features['device_env'] = event_data.get('device_env', '正常')
    
    # 贷款用途
    features['loan_purpose'] = event_data.get('loan_purpose', '')
    
    return features


# ============================================================
# 账户统计特征 (Account Statistics)
# ============================================================

async def compute_account_statistics(
    db: AsyncSession,
    account_id: str,
    current_txn: Optional[TransactionOrder] = None
) -> dict:
    """
    计算账户统计特征 (与 risk_rule 条件字段对齐)
    
    特征列表:
    - daily_cash_total: 当日现金交易总额
    - daily_transfer_count: 当日转账笔数
    - daily_fail_count: 当日交易失败次数
    - last_txn_days: 距上次交易天数
    - is_first_large: 是否首笔大额交易
    - large_incoming_count: 大额入账笔数 (近30天)
    - per_txn_amount: 平均每笔交易金额
    - total_in_amount: 累计入账总额
    - hold_minutes: 资金停留时间 (分钟)
    - device_account_count: 同一设备关联账户数
    - txn_count_30d_to_new: 30天内向新账户转账笔数
    - counterparty_reg_days: 对手方注册天数
    """
    features = {}
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    time_30d = now - timedelta(days=30)
    
    # 1. 当日现金交易总额
    stmt = select(func.sum(TransactionOrder.txn_amount)).select_from(TransactionOrder).where(
        and_(
            TransactionOrder.account_id == account_id,
            TransactionOrder.txn_time >= today_start,
            TransactionOrder.txn_status == '成功',
            TransactionOrder.txn_type_code.in_(
                select(TransactionType.txn_type_code).where(TransactionType.is_cash == 1)
            )
        )
    )
    result = await db.execute(stmt)
    features['daily_cash_total'] = float(result.scalar() or 0)
    
    # 2. 当日转账笔数
    stmt = select(func.count()).select_from(TransactionOrder).where(
        and_(
            TransactionOrder.account_id == account_id,
            TransactionOrder.txn_time >= today_start,
            TransactionOrder.txn_status == '成功',
            TransactionOrder.txn_type_code.in_(
                select(TransactionType.txn_type_code).where(TransactionType.txn_type_name == '转账汇款')
            )
        )
    )
    result = await db.execute(stmt)
    features['daily_transfer_count'] = result.scalar() or 0
    
    # 3. 当日交易失败次数
    stmt = select(func.count()).select_from(TransactionOrder).where(
        and_(
            TransactionOrder.account_id == account_id,
            TransactionOrder.txn_time >= today_start,
            TransactionOrder.txn_status == '失败'
        )
    )
    result = await db.execute(stmt)
    features['daily_fail_count'] = result.scalar() or 0
    
    # 4. 距上次交易天数
    stmt = select(func.max(TransactionOrder.txn_time)).select_from(TransactionOrder).where(
        and_(
            TransactionOrder.account_id == account_id,
            TransactionOrder.txn_status == '成功',
            TransactionOrder.txn_time < (current_txn.txn_time if current_txn else now)
        )
    )
    result = await db.execute(stmt)
    last_txn_time = result.scalar()
    if last_txn_time:
        features['last_txn_days'] = (now - last_txn_time).days
    else:
        features['last_txn_days'] = 9999
    
    # 5. 是否首笔大额交易 (当日首笔 >= 1万)
    if current_txn and current_txn.txn_amount >= 10000:
        stmt = select(func.count()).select_from(TransactionOrder).where(
            and_(
                TransactionOrder.account_id == account_id,
                TransactionOrder.txn_time >= today_start,
                TransactionOrder.txn_time < current_txn.txn_time,
                TransactionOrder.txn_amount >= 10000,
                TransactionOrder.txn_status == '成功'
            )
        )
        result = await db.execute(stmt)
        prev_large_count = result.scalar() or 0
        features['is_first_large'] = prev_large_count == 0
    else:
        features['is_first_large'] = False
    
    # 6. 大额入账笔数 (近30天 >= 1万)
    stmt = select(func.count()).select_from(TransactionOrder).where(
        and_(
            TransactionOrder.account_id == account_id,
            TransactionOrder.txn_time >= time_30d,
            TransactionOrder.txn_status == '成功',
            TransactionOrder.txn_type_code.in_(
                select(TransactionType.txn_type_code).where(TransactionType.is_credit == 1)
            ),
            TransactionOrder.txn_amount >= 10000
        )
    )
    result = await db.execute(stmt)
    features['large_incoming_count'] = result.scalar() or 0
    
    # 7. 平均每笔交易金额 (近30天)
    stmt = select(func.avg(TransactionOrder.txn_amount)).select_from(TransactionOrder).where(
        and_(
            TransactionOrder.account_id == account_id,
            TransactionOrder.txn_time >= time_30d,
            TransactionOrder.txn_status == '成功'
        )
    )
    result = await db.execute(stmt)
    features['per_txn_amount'] = float(result.scalar() or 0)
    
    # 8. 累计入账总额
    stmt = select(AccountInfo.total_in_amount).where(AccountInfo.account_id == account_id)
    result = await db.execute(stmt)
    features['total_in_amount'] = float(result.scalar() or 0)
    
    # 9. 资金停留时间 (分钟) - 简化计算：最近一笔入账到当前交易的时间
    if current_txn:
        stmt = select(AccountBalanceLog.change_time).where(
            and_(
                AccountBalanceLog.account_id == account_id,
                AccountBalanceLog.change_amount > 0,
                AccountBalanceLog.change_time < current_txn.txn_time
            )
        ).order_by(desc(AccountBalanceLog.change_time)).limit(1)
        result = await db.execute(stmt)
        last_in_time = result.scalar()
        if last_in_time:
            features['hold_minutes'] = int((current_txn.txn_time - last_in_time).total_seconds() / 60)
        else:
            features['hold_minutes'] = 9999
    else:
        features['hold_minutes'] = 9999
    
    # 10. 同一设备关联账户数
    if current_txn and current_txn.device_id:
        stmt = select(func.count(func.distinct(TransactionOrder.account_id))).select_from(TransactionOrder).where(
            and_(
                TransactionOrder.device_id == current_txn.device_id,
                TransactionOrder.txn_time >= time_30d
            )
        )
        result = await db.execute(stmt)
        features['device_account_count'] = result.scalar() or 1
    else:
        features['device_account_count'] = 1
    
    # 11. 30天内向新账户转账笔数
    if current_txn and current_txn.counterparty_account:
        # 查询对手方注册时间
        stmt = select(AccountInfo.register_time).where(AccountInfo.account_id == current_txn.counterparty_account)
        result = await db.execute(stmt)
        counterparty_reg_time = result.scalar()
        if counterparty_reg_time:
            features['counterparty_reg_days'] = (now - counterparty_reg_time).days
        else:
            features['counterparty_reg_days'] = 999
        
        # 统计向该对手方转账笔数
        stmt = select(func.count()).select_from(TransactionOrder).where(
            and_(
                TransactionOrder.account_id == account_id,
                TransactionOrder.counterparty_account == current_txn.counterparty_account,
                TransactionOrder.txn_time >= time_30d,
                TransactionOrder.txn_status == '成功'
            )
        )
        result = await db.execute(stmt)
        features['txn_count_30d_to_new'] = result.scalar() or 0
    else:
        features['counterparty_reg_days'] = 999
        features['txn_count_30d_to_new'] = 0
    
    return features


# ============================================================
# 信贷特征 (Credit Features)
# ============================================================

async def compute_credit_features(
    db: AsyncSession,
    account_id: str
) -> dict:
    """
    计算信贷特征 (与 risk_rule 条件字段对齐)
    
    特征列表:
    - credit_inquiry_3m: 近3个月征信查询次数
    - credit_usage_rate: 信用卡使用率 (%)
    - duration_months: 持续时间 (月)
    - loan_to_income_ratio: 贷款收入比
    - overdue_days: 逾期天数
    - overdue_amount: 逾期金额
    - unsettled_lender_count: 未结清贷款机构数
    - is_approved: 是否已批准
    """
    features = {}
    now = datetime.now()
    time_3m = now - timedelta(days=90)
    
    # 1. 近3个月征信查询次数
    stmt = select(func.count()).select_from(CreditInquiryLog).where(
        and_(
            CreditInquiryLog.account_id == account_id,
            CreditInquiryLog.inquiry_time >= time_3m
        )
    )
    result = await db.execute(stmt)
    features['credit_inquiry_3m'] = result.scalar() or 0
    
    # 2. 信用卡使用率 (%)
    stmt = select(
        func.sum(CreditCardInfo.used_limit),
        func.sum(CreditCardInfo.total_limit)
    ).select_from(CreditCardInfo).where(
        CreditCardInfo.account_id == account_id
    )
    result = await db.execute(stmt)
    row = result.first()
    used_limit = float(row[0] or 0)
    total_limit = float(row[1] or 0)
    features['credit_usage_rate'] = (
        (used_limit / total_limit * 100) if total_limit > 0 else 0
    )
    
    # 3. 持续时间 (月) - 信用卡使用率 >= 90% 的持续时间
    stmt = select(func.min(CreditCardInfo.update_time)).select_from(CreditCardInfo).where(
        and_(
            CreditCardInfo.account_id == account_id,
            CreditCardInfo.used_limit / CreditCardInfo.total_limit >= 0.9
        )
    )
    result = await db.execute(stmt)
    high_usage_start = result.scalar()
    if high_usage_start:
        features['duration_months'] = (now - high_usage_start).days // 30
    else:
        features['duration_months'] = 0
    
    # 4. 贷款收入比
    stmt = select(
        func.sum(LoanInfo.remaining_principal),
        AccountInfo.monthly_income
    ).select_from(LoanInfo).outerjoin(
        AccountInfo, LoanInfo.account_id == AccountInfo.account_id
    ).where(
        and_(
            LoanInfo.account_id == account_id,
            LoanInfo.repay_status.in_(['正常', '逾期'])
        )
    ).group_by(AccountInfo.monthly_income)
    result = await db.execute(stmt)
    row = result.first()
    if row:
        remaining_principal = float(row[0] or 0)
        monthly_income = float(row[1] or 0)
        features['loan_to_income_ratio'] = (
            remaining_principal / monthly_income if monthly_income > 0 else 999
        )
    else:
        features['loan_to_income_ratio'] = 0
    
    # 5. 逾期天数 (最大)
    # 【2026-08-12 修复】优先从 loan_info.overdue_days 读取 (生成脚本写此表),
    # repayment_record.is_late 作为回退来源.
    stmt = select(func.max(LoanInfo.overdue_days)).select_from(LoanInfo).where(
        and_(
            LoanInfo.account_id == account_id,
            LoanInfo.repay_status == '逾期',
            LoanInfo.overdue_days.isnot(None),
        )
    )
    result = await db.execute(stmt)
    overdue_days_loan = result.scalar() or 0

    stmt = select(func.max(RepaymentRecord.late_days)).select_from(RepaymentRecord).join(
        LoanInfo, LoanInfo.loan_id == RepaymentRecord.loan_id
    ).where(
        and_(
            LoanInfo.account_id == account_id,
            RepaymentRecord.is_late == 1
        )
    )
    result = await db.execute(stmt)
    overdue_days_repay = result.scalar() or 0
    features['overdue_days'] = max(overdue_days_loan, overdue_days_repay)

    # 6. 逾期金额 (最近一次逾期)
    # 【2026-08-12 修复】优先取 loan_info.remaining_principal (逾期贷款的剩余本金),
    # repayment_record.repay_amount 作为回退来源.
    stmt = select(LoanInfo.remaining_principal).select_from(LoanInfo).where(
        and_(
            LoanInfo.account_id == account_id,
            LoanInfo.repay_status == '逾期',
            LoanInfo.remaining_principal.isnot(None),
        )
    ).order_by(desc(LoanInfo.due_time)).limit(1)
    result = await db.execute(stmt)
    overdue_amount_loan = float(result.scalar() or 0)

    stmt = select(RepaymentRecord.repay_amount).select_from(RepaymentRecord).join(
        LoanInfo, LoanInfo.loan_id == RepaymentRecord.loan_id
    ).where(
        and_(
            LoanInfo.account_id == account_id,
            RepaymentRecord.is_late == 1
        )
    ).order_by(desc(RepaymentRecord.repay_time)).limit(1)
    result = await db.execute(stmt)
    overdue_amount_repay = float(result.scalar() or 0)
    features['overdue_amount'] = max(overdue_amount_loan, overdue_amount_repay)

# 7. 未结清贷款机构数
    stmt = select(func.count(func.distinct(LoanInfo.lender_org))).select_from(LoanInfo).where(
        and_(
            LoanInfo.account_id == account_id,
            LoanInfo.repay_status.in_(['正常', '逾期'])
        )
    )
    result = await db.execute(stmt)
    features['unsettled_lender_count'] = result.scalar() or 0
    
    # 8. 是否已批准 (征信查询后是否放款)
    stmt = select(func.count()).select_from(CreditInquiryLog).where(
        and_(
            CreditInquiryLog.account_id == account_id,
            CreditInquiryLog.inquiry_time >= time_3m,
            CreditInquiryLog.is_approved == 1
        )
    )
    result = await db.execute(stmt)
    approved_count = result.scalar() or 0
    features['is_approved'] = approved_count > 0
    
    return features


# ============================================================
# 行为特征 (Behavior Features)
# ============================================================

async def compute_behavior_features(
    db: AsyncSession,
    account_id: str,
    current_operation: Optional[UserOperationLog] = None
) -> dict:
    """
    计算行为维度特征 (10个)
    
    特征列表:
    - beh_dormant_days: 沉睡账户天数(最后一次交易距今)
    - beh_info_change_count_30d: 近30天信息修改次数
    - beh_password_change_count_30d: 近30天密码修改次数
    - beh_device_env_risk_score: 设备环境风险评分
    - beh_sensitive_op_interval_min: 敏感操作间隔(分钟)
    - beh_login_failure_count_7d: 近7天登录失败次数
    - beh_ip_change_count_30d: 近30天IP变更次数
    - beh_address_change_count_30d: 近30天地址变更次数
    - beh_night_operation_count_30d: 近30天凌晨操作次数
    - beh_high_risk_operation_count_30d: 近30天高风险操作次数
    """
    features = {}
    now = datetime.now()
    
    # 时间窗口
    time_7d = now - timedelta(days=7)
    time_30d = now - timedelta(days=30)
    
    # 1. 沉睡账户天数
    stmt = select(func.max(TransactionOrder.txn_time)).select_from(TransactionOrder).where(
        and_(
            TransactionOrder.account_id == account_id,
            TransactionOrder.txn_status == '成功'
        )
    )
    result = await db.execute(stmt)
    last_txn_time = result.scalar()
    
    if last_txn_time:
        features['beh_dormant_days'] = (now - last_txn_time).days
    else:
        # 从未交易过，使用账户注册时间
        stmt = select(AccountInfo.register_time).where(AccountInfo.account_id == account_id)
        result = await db.execute(stmt)
        create_time = result.scalar()
        if create_time:
            features['beh_dormant_days'] = (now - create_time).days
        else:
            features['beh_dormant_days'] = 999  # 异常值
    
    # 2. 近30天信息修改次数
    stmt = select(func.count()).select_from(UserOperationLog).where(
        and_(
            UserOperationLog.account_id == account_id,
            UserOperationLog.op_time >= time_30d,
            UserOperationLog.op_type.in_(['修改手机号', '修改邮箱', '修改地址'])
        )
    )
    result = await db.execute(stmt)
    features['beh_info_change_count_30d'] = result.scalar() or 0
    
    # 3. 近30天密码修改次数
    stmt = select(func.count()).select_from(UserOperationLog).where(
        and_(
            UserOperationLog.account_id == account_id,
            UserOperationLog.op_time >= time_30d,
            UserOperationLog.op_type.in_(['修改密码', '修改支付密码', '找回密码'])
        )
    )
    result = await db.execute(stmt)
    features['beh_password_change_count_30d'] = result.scalar() or 0
    
    # 4. 设备环境风险评分
    # 简化：基于设备变更频率、模拟器检测等
    stmt = select(func.count(func.distinct(UserOperationLog.device_id))).select_from(UserOperationLog).where(
        and_(
            UserOperationLog.account_id == account_id,
            UserOperationLog.op_time >= time_30d,
            UserOperationLog.device_id.isnot(None)
        )
    )
    result = await db.execute(stmt)
    device_count = result.scalar() or 0
    
    # 设备风险评分：设备数越多风险越高
    features['beh_device_env_risk_score'] = min(device_count / 5, 1.0)  # 5个以上设备满分
    
    # 5. 敏感操作间隔(分钟)
    # 敏感操作：转账、修改密码、修改手机号等
    sensitive_ops = ['转账', '修改密码', '修改支付密码', '修改手机号']
    stmt = select(UserOperationLog.op_time).select_from(UserOperationLog).where(
        and_(
            UserOperationLog.account_id == account_id,
            UserOperationLog.op_time >= time_30d,
            UserOperationLog.op_type.in_(sensitive_ops)
        )
    ).order_by(desc(UserOperationLog.op_time)).limit(2)
    result = await db.execute(stmt)
    rows = result.fetchall()
    
    if len(rows) >= 2:
        interval = (rows[0][0] - rows[1][0]).total_seconds() / 60
        features['beh_sensitive_op_interval_min'] = interval
    else:
        features['beh_sensitive_op_interval_min'] = 999  # 无足够数据
    
    # 6. 近7天登录失败次数
    stmt = select(func.count()).select_from(UserOperationLog).where(
        and_(
            UserOperationLog.account_id == account_id,
            UserOperationLog.op_time >= time_7d,
            UserOperationLog.op_type == '登录',
            UserOperationLog.op_result == '失败'
        )
    )
    result = await db.execute(stmt)
    features['beh_login_failure_count_7d'] = result.scalar() or 0
    
    # 7. 近30天IP变更次数
    stmt = select(func.count(func.distinct(UserOperationLog.ip_address))).select_from(UserOperationLog).where(
        and_(
            UserOperationLog.account_id == account_id,
            UserOperationLog.op_time >= time_30d,
            UserOperationLog.ip_address.isnot(None)
        )
    )
    result = await db.execute(stmt)
    features['beh_ip_change_count_30d'] = result.scalar() or 0
    
    # 8. 近30天地址变更次数
    stmt = select(func.count()).select_from(AddressHistory).where(
        and_(
            AddressHistory.account_id == account_id,
            AddressHistory.first_seen_time >= time_30d,
            AddressHistory.address_type == '常用地址'
        )
    )
    result = await db.execute(stmt)
    features['beh_address_change_count_30d'] = result.scalar() or 0
    
    # 9. 近30天凌晨操作次数(0-6点)
    stmt = select(func.count()).select_from(UserOperationLog).where(
        and_(
            UserOperationLog.account_id == account_id,
            UserOperationLog.op_time >= time_30d,
            func.hour(UserOperationLog.op_time) < 6
        )
    )
    result = await db.execute(stmt)
    features['beh_night_operation_count_30d'] = result.scalar() or 0
    
    # 10. 近30天高风险操作次数
    # 高风险操作：大额转账、境外交易、修改关键信息等
    high_risk_ops = ['大额转账', '境外转账', '修改支付密码', '绑定新设备']
    stmt = select(func.count()).select_from(UserOperationLog).where(
        and_(
            UserOperationLog.account_id == account_id,
            UserOperationLog.op_time >= time_30d,
            UserOperationLog.op_type.in_(high_risk_ops)
        )
    )
    result = await db.execute(stmt)
    features['beh_high_risk_operation_count_30d'] = result.scalar() or 0
    
    return features


# ============================================================
# 统一特征计算入口
# ============================================================

async def compute_all_features(
    db: AsyncSession,
    account_id: str,
    event_data: Optional[dict] = None,
    current_txn: Optional[TransactionOrder] = None,
    current_operation: Optional[UserOperationLog] = None
) -> dict:
    """
    计算全部金融风控特征 (与 risk_rule 条件字段完全对齐)
    返回合并后的特征字典

    参数:
    - event_data: 当前事件数据 (用于提取事件级特征)
    - current_txn: 当前交易记录 (用于计算账户统计特征)
    - current_operation: 当前操作记录 (用于计算行为特征)
    """
    # 1. 事件级特征 (从当前事件直接提取)
    if event_data:
        event_features = await compute_event_features(db, account_id, event_data)
    else:
        event_features = {}

    # 2. 账户统计特征 (从数据库聚合计算)
    account_stats = await compute_account_statistics(db, account_id, current_txn)

    # 3. 信贷特征
    credit_features = await compute_credit_features(db, account_id)

    # 4. 行为特征
    behavior_features = await compute_behavior_features(db, account_id, current_operation)

    # 合并所有特征 (事件特征优先级最高, 可覆盖统计值)
    all_features = {}
    all_features.update(account_stats)
    all_features.update(credit_features)
    all_features.update(behavior_features)
    all_features.update(event_features)

    return all_features


# ============================================================
# 特征重要性排序 (用于模型训练)
# ============================================================

FEATURE_IMPORTANCE = {
    # 账户特征
    'acct_txn_amount_7d': 0.95,
    'acct_max_txn_amount_30d': 0.92,
    'acct_night_txn_count_30d': 0.88,
    'acct_failed_txn_count_7d': 0.85,
    'acct_device_count_30d': 0.82,
    'acct_quick_in_out_ratio_30d': 0.80,
    'acct_overseas_txn_count_30d': 0.78,
    'acct_high_risk_country_count_30d': 0.75,
    
    # 信贷特征
    'credit_inquiry_count_30d': 0.90,
    'credit_card_utilization': 0.88,
    'credit_multi_lending_count': 0.85,
    'credit_overdue_count_30d': 0.93,
    'credit_overdue_days_max': 0.91,
    'credit_loan_income_ratio': 0.89,
    
    # 行为特征
    'beh_dormant_days': 0.86,
    'beh_info_change_count_30d': 0.83,
    'beh_password_change_count_30d': 0.81,
    'beh_device_env_risk_score': 0.79,
    'beh_sensitive_op_interval_min': 0.77,
    'beh_login_failure_count_7d': 0.84,
}


def get_feature_names() -> list:
    """获取所有特征名称列表"""
    return list(FEATURE_IMPORTANCE.keys())
