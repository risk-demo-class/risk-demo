"""
银行信贷风控 - 特征工程模块 (Task 3 重写)

通过 ORM 查询银行业务表, 计算 25 个风控特征 (替换电商版 25 维).

【特征命名规范】前缀用于 engine/decision.py 决定 risk_feature 表的 entity_type
  user_*  = 借款人维度 (13 个): 申请频次 / 负债 / 逾期 / 征信 / 收入偏差 / 关联关系
  order_* = 事件维度   (9 个): 按 event_type 映射到 申请/合同/还款/转账/登录 源实体
  addr_*  = 设备/IP 维度 (3 个): 设备共用 / 设备新度 / 代理IP

【特征名 ↔ 规则 / XGBoost】
  FEATURE_COLUMNS (app/engine/ml_model.py) 顺序必须跟本文件 key 一一对应,
  规则引擎 (rule.py) 用这些 key 写条件表达式.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BUSINESS_EVENT_TYPES
from app.models import (
    CreditReport,
    DeviceFingerprint,
    IncomeVerify,
    IpGeoLocation,
    LoanApplication,
    LoanContract,
    LoginLog,
    RepaymentPlan,
    RepaymentRecord,
    Transaction,
    UserInfo,
    UserRelation,
)


# ============================================================
# 通用 SQL 工具
# ============================================================

async def _count(db: AsyncSession, model, **filters) -> float:
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _avg(db: AsyncSession, model, col_name: str, **filters) -> float:
    col = getattr(model, col_name)
    stmt = select(func.avg(col)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


async def _max(db: AsyncSession, model, col_name: str, **filters) -> float:
    col = getattr(model, col_name)
    stmt = select(func.max(col)).select_from(model)
    for f_col, val in filters.items():
        stmt = stmt.where(getattr(model, f_col) == val)
    return float((await db.execute(stmt)).scalar() or 0)


def _is_night(dt: datetime | None) -> float:
    """是否凌晨 0-5 点. 兼容 DATE 类型 (无 hour 属性, 按非夜间处理)."""
    if dt is None:
        return 0.0
    try:
        return 1.0 if 0 <= dt.hour < 6 else 0.0
    except AttributeError:
        return 0.0


def _gap_ratio(declared, verified) -> float:
    """收入申报偏差比 = (申报 - 核验) / 核验. 核验为 0 时返回 0."""
    try:
        declared = float(declared)
        verified = float(verified)
    except (TypeError, ValueError):
        return 0.0
    if verified <= 0:
        return 0.0
    return round(max(declared - verified, 0) / verified, 4)


# ============================================================
# 用户维度特征 (13 个)
# ============================================================

async def _feat_user_total_applications(db: AsyncSession, user_id: str) -> float:
    """历史贷款申请总笔数"""
    return await _count(db, LoanApplication, user_id=user_id)


async def _feat_user_applications_30d(db: AsyncSession, user_id: str) -> float:
    """近 30 天贷款申请笔数 (多头借贷信号)"""
    since = datetime.now() - timedelta(days=30)
    stmt = select(func.count()).select_from(LoanApplication).where(
        LoanApplication.user_id == user_id,
        LoanApplication.apply_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_applications_60d(db: AsyncSession, user_id: str) -> float:
    """近 60 天贷款申请笔数 (多头借贷信号)"""
    since = datetime.now() - timedelta(days=60)
    stmt = select(func.count()).select_from(LoanApplication).where(
        LoanApplication.user_id == user_id,
        LoanApplication.apply_time >= since,
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_avg_apply_amount(db: AsyncSession, user_id: str) -> float:
    """平均申请金额"""
    return await _avg(db, LoanApplication, "apply_amount", user_id=user_id)


async def _feat_user_max_apply_amount(db: AsyncSession, user_id: str) -> float:
    """最大申请金额"""
    return await _max(db, LoanApplication, "apply_amount", user_id=user_id)


async def _feat_user_avg_debt_ratio(db: AsyncSession, user_id: str) -> float:
    """平均债务收入比 DTI (月负债/月收入)"""
    return await _avg(db, LoanApplication, "debt_ratio", user_id=user_id)


async def _feat_user_overdue_plan_count(db: AsyncSession, user_id: str) -> float:
    """当前逾期还款计划期数 (M1/M2/M3 信号)"""
    return await _count(db, RepaymentPlan, user_id=user_id, status="逾期")


async def _feat_user_overdue_24m_count(db: AsyncSession, user_id: str) -> float:
    """征信近 24 月累计逾期次数 (取最近一份征信)"""
    stmt = select(CreditReport.overdue_24m_count).where(
        CreditReport.user_id == user_id,
    ).order_by(CreditReport.report_date.desc()).limit(1)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_hard_query_6m(db: AsyncSession, user_id: str) -> float:
    """征信近 6 月硬查询次数 (取最近一份征信)"""
    stmt = select(CreditReport.recent_6m_hard_query_count).where(
        CreditReport.user_id == user_id,
    ).order_by(CreditReport.report_date.desc()).limit(1)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_credit_score(db: AsyncSession, user_id: str) -> float:
    """行内信用分 (0-1000)"""
    stmt = select(UserInfo.credit_score).where(UserInfo.user_id == user_id).limit(1)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_income_gap_ratio(db: AsyncSession, user_id: str) -> float:
    """申报 vs 核验月收入偏差比 (材料造假信号)"""
    row = (await db.execute(
        select(UserInfo.monthly_income, UserInfo.verified_income)
        .where(UserInfo.user_id == user_id).limit(1)
    )).first()
    if not row:
        return 0.0
    return _gap_ratio(row.monthly_income, row.verified_income)


async def _feat_user_account_age_days(db: AsyncSession, user_id: str) -> float:
    """开户天数 (新开户 = 高风险信号)"""
    stmt = select(UserInfo.account_age_days).where(UserInfo.user_id == user_id).limit(1)
    return float((await db.execute(stmt)).scalar() or 0)


async def _feat_user_relation_count(db: AsyncSession, user_id: str) -> float:
    """关联关系数 (知识图谱: 同设备/同地址/互保/资金往来)"""
    stmt = select(func.count()).select_from(UserRelation).where(
        (UserRelation.user_id == user_id) | (UserRelation.related_user_id == user_id)
    )
    return float((await db.execute(stmt)).scalar() or 0)


async def compute_user_features(db: AsyncSession, user_id: str) -> dict[str, float]:
    """计算 13 个借款人维度特征."""
    feat_funcs = {
        "user_total_applications": _feat_user_total_applications,
        "user_applications_30d": _feat_user_applications_30d,
        "user_applications_60d": _feat_user_applications_60d,
        "user_avg_apply_amount": _feat_user_avg_apply_amount,
        "user_max_apply_amount": _feat_user_max_apply_amount,
        "user_avg_debt_ratio": _feat_user_avg_debt_ratio,
        "user_overdue_plan_count": _feat_user_overdue_plan_count,
        "user_overdue_24m_count": _feat_user_overdue_24m_count,
        "user_hard_query_6m": _feat_user_hard_query_6m,
        "user_credit_score": _feat_user_credit_score,
        "user_income_gap_ratio": _feat_user_income_gap_ratio,
        "user_account_age_days": _feat_user_account_age_days,
        "user_relation_count": _feat_user_relation_count,
    }
    return {name: await fn(db, user_id) for name, fn in feat_funcs.items()}


# ============================================================
# 事件维度特征 (9 个) — 按 event_type 映射源实体
# ============================================================

async def _load_application_features(db: AsyncSession, entity_id: str) -> dict[str, float]:
    """贷款申请事件: 申请 + 征信 + 收入核验"""
    app = (await db.execute(
        select(LoanApplication).where(LoanApplication.application_id == entity_id).limit(1)
    )).scalar_one_or_none()
    if not app:
        return {}

    credit = (await db.execute(
        select(CreditReport).where(CreditReport.application_id == entity_id).limit(1)
    )).scalar_one_or_none()
    income = (await db.execute(
        select(IncomeVerify).where(IncomeVerify.application_id == entity_id).limit(1)
    )).scalar_one_or_none()

    credit_score = float(credit.credit_score) if credit else 0.0
    hard_query = float(credit.recent_6m_hard_query_count) if credit else 0.0
    five_level_risk = 1.0 if (credit and credit.five_level_class != "正常") else 0.0
    income_gap = 0.0
    if income:
        income_gap = _gap_ratio(income.declared_monthly_income, income.verified_monthly_income)

    return {
        "order_amount": float(app.apply_amount),
        "order_term_months": float(app.term_months),
        "order_dti": float(app.debt_ratio),
        "order_is_night": _is_night(app.apply_time),
        "order_purpose_risk": 1.0 if app.purpose in ("经营", "购房") else 0.0,
        "order_credit_score": credit_score,
        "order_hard_query_6m": hard_query,
        "order_five_level_risk": five_level_risk,
        "order_income_verify_gap": income_gap,
    }


async def _load_contract_features(db: AsyncSession, entity_id: str) -> dict[str, float]:
    """放款事件: 合同"""
    contract = (await db.execute(
        select(LoanContract).where(LoanContract.contract_id == entity_id).limit(1)
    )).scalar_one_or_none()
    if not contract:
        return {}
    return {
        "order_amount": float(contract.loan_amount),
        "order_term_months": float(contract.term_months),
        "order_dti": 0.0,
        "order_is_night": _is_night(contract.disbursement_date),
        "order_purpose_risk": 0.0,
        "order_credit_score": 0.0,
        "order_hard_query_6m": 0.0,
        "order_five_level_risk": 0.0,
        "order_income_verify_gap": 0.0,
    }


async def _load_repayment_features(db: AsyncSession, entity_id: str) -> dict[str, float]:
    """还款事件: 还款流水"""
    record = (await db.execute(
        select(RepaymentRecord).where(RepaymentRecord.record_id == entity_id).limit(1)
    )).scalar_one_or_none()
    if not record:
        return {}
    return {
        "order_amount": float(record.repay_amount),
        "order_term_months": 0.0,
        "order_dti": 0.0,
        "order_is_night": _is_night(record.repay_time),
        "order_purpose_risk": 0.0,
        "order_credit_score": 0.0,
        "order_hard_query_6m": 0.0,
        "order_five_level_risk": 0.0,
        "order_income_verify_gap": 0.0,
    }


async def _load_transaction_features(db: AsyncSession, entity_id: str) -> dict[str, float]:
    """转账/交易事件: 交易流水"""
    txn = (await db.execute(
        select(Transaction).where(Transaction.txn_id == entity_id).limit(1)
    )).scalar_one_or_none()
    if not txn:
        return {}
    return {
        "order_amount": float(txn.amount),
        "order_term_months": 0.0,
        "order_dti": 0.0,
        "order_is_night": _is_night(txn.txn_time),
        "order_purpose_risk": 0.0,
        "order_credit_score": 0.0,
        "order_hard_query_6m": 0.0,
        "order_five_level_risk": 0.0,
        "order_income_verify_gap": 0.0,
    }


async def _load_login_features(db: AsyncSession, entity_id: str) -> dict[str, float]:
    """登录事件: 登录日志"""
    login = (await db.execute(
        select(LoginLog).where(LoginLog.login_id == entity_id).limit(1)
    )).scalar_one_or_none()
    if not login:
        return {}
    return {
        "order_amount": 0.0,
        "order_term_months": 0.0,
        "order_dti": 0.0,
        "order_is_night": _is_night(login.login_time),
        "order_purpose_risk": 0.0,
        "order_credit_score": 0.0,
        "order_hard_query_6m": 0.0,
        "order_five_level_risk": 0.0,
        "order_income_verify_gap": 0.0,
    }


_ORDER_LOADERS = {
    "贷款申请": _load_application_features,
    "放款": _load_contract_features,
    "还款": _load_repayment_features,
    "转账": _load_transaction_features,
    "登录": _load_login_features,
}

# 一致性约束: 事件特征加载器必须覆盖 config.BUSINESS_EVENT_TYPES 全量
assert set(_ORDER_LOADERS) == set(BUSINESS_EVENT_TYPES), (
    "feature._ORDER_LOADERS 与 config.BUSINESS_EVENT_TYPES 不一致"
)


async def compute_order_features(
    db: AsyncSession,
    entity_id: str | None,
    event_type: str,
) -> dict[str, float]:
    """计算 9 个事件维度特征 (按 event_type 映射到源实体表)."""
    if not entity_id:
        return {}
    loader = _ORDER_LOADERS.get(event_type)
    if not loader:
        return {}
    return await loader(db, entity_id)


# ============================================================
# 设备/IP 维度特征 (3 个)
# ============================================================

async def _resolve_device(db: AsyncSession, user_id: str, device_id: str | None) -> str | None:
    """事件没带 device_id 时, 兜底用该用户最近使用的设备"""
    if device_id:
        return device_id
    row = (await db.execute(
        select(DeviceFingerprint.device_id).where(
            DeviceFingerprint.user_id == user_id,
        ).order_by(DeviceFingerprint.last_seen.desc()).limit(1)
    )).first()
    return row.device_id if row else None


async def _feat_addr_device_share_count(
    db: AsyncSession, user_id: str, device_id: str | None,
) -> float:
    """设备关联的不同用户数 (设备多人共用 = 团伙信号)"""
    device_id = await _resolve_device(db, user_id, device_id)
    if not device_id:
        return 0.0
    stmt = select(func.count(func.distinct(UserInfo.user_id))).select_from(UserInfo).where(
        UserInfo.user_id.in_(
            select(DeviceFingerprint.user_id).where(DeviceFingerprint.device_id == device_id)
        )
    )
    # 申请记录里同设备的不同用户也计入
    stmt_app = select(func.count(func.distinct(LoanApplication.user_id))).select_from(
        LoanApplication
    ).where(LoanApplication.device_id == device_id)
    return float((await db.execute(stmt)).scalar() or 0) + float((await db.execute(stmt_app)).scalar() or 0)


async def _feat_addr_device_age_days(
    db: AsyncSession, user_id: str, device_id: str | None,
) -> float:
    """设备首次出现到今天的天数 (新设备 = 高风险信号)"""
    device_id = await _resolve_device(db, user_id, device_id)
    if not device_id:
        return 0.0
    stmt = select(func.min(DeviceFingerprint.first_seen)).where(
        DeviceFingerprint.device_id == device_id,
    )
    first_seen = (await db.execute(stmt)).scalar()
    if not first_seen:
        return 0.0
    return max(float((datetime.now() - first_seen).total_seconds() / 86400), 0.0)


async def _feat_addr_ip_risk(db: AsyncSession, ip: str | None) -> float:
    """IP 是否代理/Tor/境外 (秒拨代理 = 欺诈信号)"""
    if not ip:
        return 0.0
    row = (await db.execute(
        select(IpGeoLocation.is_proxy, IpGeoLocation.is_tor, IpGeoLocation.is_abroad)
        .where(IpGeoLocation.ip == ip).limit(1)
    )).first()
    if not row:
        return 0.0
    return 1.0 if (row.is_proxy or row.is_tor or row.is_abroad) else 0.0


async def compute_address_features(
    db: AsyncSession,
    user_id: str,
    device_id: str | None = None,
    ip: str | None = None,
) -> dict[str, float]:
    """计算 3 个设备/IP 维度特征."""
    return {
        "addr_device_share_count": await _feat_addr_device_share_count(db, user_id, device_id),
        "addr_device_age_days": await _feat_addr_device_age_days(db, user_id, device_id),
        "addr_ip_risk": await _feat_addr_ip_risk(db, ip),
    }


# ============================================================
# 聚合入口
# ============================================================

async def compute_all_features(
    db: AsyncSession,
    user_id: str,
    entity_id: str | None = None,
    device_id: str | None = None,
    ip: str | None = None,
    event_type: str = "",
) -> dict[str, float]:
    """一次性计算全部 25 维特征并合并返回."""
    features = await compute_user_features(db, user_id)
    features.update(await compute_order_features(db, entity_id, event_type))
    features.update(await compute_address_features(db, user_id, device_id, ip))
    return features


# ============================================================
# Demo: 展示 25 维特征名 + 分类 + 字典派发表 — 无需 DB (只读常量)
# 跑法: python app/engine/feature.py
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("银行特征工程 — 25 维特征名 + 分类 + 字典派发表")
    print("=" * 60)

    user_feats = [
        ("user_total_applications", "历史贷款申请笔数"),
        ("user_applications_30d", "近30天申请笔数"),
        ("user_applications_60d", "近60天申请笔数(多头借贷)"),
        ("user_avg_apply_amount", "平均申请金额"),
        ("user_max_apply_amount", "最大申请金额"),
        ("user_avg_debt_ratio", "平均债务收入比DTI"),
        ("user_overdue_plan_count", "当前逾期期数"),
        ("user_overdue_24m_count", "征信近24月逾期次数"),
        ("user_hard_query_6m", "征信近6月硬查询次数"),
        ("user_credit_score", "行内信用分"),
        ("user_income_gap_ratio", "申报/核验收入偏差比"),
        ("user_account_age_days", "开户天数"),
        ("user_relation_count", "关联关系数(图谱)"),
    ]
    order_feats = [
        ("order_amount", "事件金额(申请/合同/还款/转账)"),
        ("order_term_months", "期限(月)"),
        ("order_dti", "申请DTI"),
        ("order_is_night", "是否凌晨0-5点(0/1)"),
        ("order_purpose_risk", "用途是否高敏(经营/购房)"),
        ("order_credit_score", "本次申请征信分"),
        ("order_hard_query_6m", "本次申请近6月硬查询"),
        ("order_five_level_risk", "五级分类是否非正常(0/1)"),
        ("order_income_verify_gap", "本次收入申报偏差比"),
    ]
    addr_feats = [
        ("addr_device_share_count", "设备关联用户数(共用)"),
        ("addr_device_age_days", "设备年龄(天)"),
        ("addr_ip_risk", "IP是否代理/Tor/境外(0/1)"),
    ]
    all_groups = [("用户 (13)", user_feats), ("事件 (9)", order_feats), ("设备/IP (3)", addr_feats)]
    total = 0
    for sec, feats in all_groups:
        print(f"\n【{sec}】")
        for i, (k, desc) in enumerate(feats, 1):
            print(f"  {i:>2}. {k:<28} - {desc}")
            total += 1
    print(f"\n总计: {total} 维特征 (跟 ml_model.FEATURE_COLUMNS 顺序一一对应)")
    print("\n事件维度按 event_type 字典派发: 贷款申请→申请+征信+收入核验 / 放款→合同 / 还款→还款流水 / 转账→交易 / 登录→登录日志")
