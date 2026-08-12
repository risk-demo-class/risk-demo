"""
AI Agent 工具集 (8 个 LangChain @tool) - 银行风控场景.

风控决策类 (4): check_risk / query_rules / query_cases / query_blacklist
数据分析类 (4): query_user_info / query_transactions / query_loan_applications / execute_sql

架构: 业务实现是 _impl 函数, @tool 包装层只负责转 LLM 入参 → 调 _safe_call → _impl.
"""
import json
import logging
import ulid
from datetime import datetime

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.database import AsyncSessionLocal
from bank_risk.app.models import (
    BankCard,
    LoanApplication,
    RiskBlacklist,
    RiskCase,
    RiskRule,
    Transaction,
    UserInfo,
)
from bank_risk.app.schemas import RiskCheckRequest
from bank_risk.app.service.event import process_event

logger = logging.getLogger(__name__)


# ============================================================
# 公共 helper
# ============================================================

async def _safe_call(error_label: str, impl, **kwargs) -> str:
    """8 个 @tool 共享的执行模板: 开 session → 调 impl → 异常转字符串."""
    try:
        async with AsyncSessionLocal() as db:
            return await impl(db=db, **kwargs)
    except Exception as e:
        error_id = f"err_{ulid.new().str.lower()[:12]}"
        logger.exception(
            "%s 执行失败 [error_id=%s] args=%s",
            error_label, error_id, {k: v for k, v in kwargs.items() if k != "db"},
        )
        return f"{error_label}失败: {e} (error_id={error_id})"


def _row_to_dict(row) -> dict:
    """SQLAlchemy Row → dict. datetime → ISO 字符串, Decimal/numpy → float."""
    item = {}
    for key, val in row._mapping.items():
        if isinstance(val, datetime):
            val = val.isoformat()
        elif hasattr(val, "__float__"):  # Decimal / numpy 数值
            val = float(val)
        item[key] = val
    return item


def _orm_to_dict(obj) -> dict:
    """ORM 对象 → dict (按表列名取值)."""
    if obj is None:
        return None
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


# ============================================================
# 风控决策类 (4 个)
# ============================================================

async def _check_risk_impl(
    *, db: AsyncSession, user_id: str, event_type: str, source_id: str,
) -> str:
    """对用户和事件执行实时风控检查 (走 process_event)."""
    request = RiskCheckRequest(event_type=event_type, source_id=source_id, user_id=user_id)
    result = await process_event(db, request)
    return json.dumps({
        "assessment_id": result.assessment_id,
        "user_id": result.user_id,
        "final_score": result.final_score,
        "risk_level": result.risk_level,
        "decision": result.decision,
        "rule_count": result.rule_count,
        "triggered_rules": [r.model_dump() for r in result.triggered_rules],
    }, ensure_ascii=False, indent=2)


async def _query_rules_impl(
    *, db: AsyncSession, category: str, enabled_only: bool,
) -> str:
    """查询风控规则列表."""
    stmt = select(RiskRule).order_by(RiskRule.priority.desc())
    if category:
        stmt = stmt.where(RiskRule.rule_category == category)
    if enabled_only:
        stmt = stmt.where(RiskRule.is_enabled == 1)
    rules = (await db.execute(stmt)).scalars().all()
    return json.dumps([_orm_to_dict(r) for r in rules], ensure_ascii=False, indent=2, default=str)


async def _query_cases_impl(*, db: AsyncSession, status: str, page: int) -> str:
    """查询风控案件列表."""
    stmt = select(RiskCase).order_by(RiskCase.create_time.desc())
    if status:
        stmt = stmt.where(RiskCase.case_status == status)
    stmt = stmt.offset((page - 1) * 20).limit(20)
    cases = (await db.execute(stmt)).scalars().all()
    return json.dumps([_orm_to_dict(c) for c in cases], ensure_ascii=False, indent=2, default=str)


async def _query_blacklist_impl(*, db: AsyncSession, blacklist_type: str) -> str:
    """查询黑名单列表."""
    stmt = select(RiskBlacklist).order_by(RiskBlacklist.create_time.desc())
    if blacklist_type:
        stmt = stmt.where(RiskBlacklist.blacklist_type == blacklist_type)
    items = (await db.execute(stmt)).scalars().all()
    return json.dumps([_orm_to_dict(b) for b in items], ensure_ascii=False, indent=2, default=str)


# ============================================================
# 数据分析类 (4 个)
# ============================================================

async def _query_user_info_impl(*, db: AsyncSession, user_id: str) -> str:
    """查询用户信息 + 银行卡."""
    user = (await db.execute(
        select(UserInfo).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()
    if not user:
        return f"未找到用户: {user_id}"
    cards = (await db.execute(
        select(BankCard).where(BankCard.user_id == user_id)
    )).scalars().all()
    return json.dumps({
        "user_info": _orm_to_dict(user),
        "bank_cards": [_orm_to_dict(c) for c in cards],
    }, ensure_ascii=False, indent=2, default=str)


async def _query_transactions_impl(*, db: AsyncSession, user_id: str, limit: int) -> str:
    """查询交易记录."""
    stmt = select(Transaction).order_by(Transaction.create_time.desc()).limit(limit)
    if user_id:
        stmt = stmt.where(Transaction.user_id == user_id)
    items = (await db.execute(stmt)).scalars().all()
    return json.dumps([_orm_to_dict(t) for t in items], ensure_ascii=False, indent=2, default=str)


async def _query_loan_applications_impl(*, db: AsyncSession, user_id: str, limit: int) -> str:
    """查询贷款申请记录."""
    stmt = select(LoanApplication).order_by(LoanApplication.create_time.desc()).limit(limit)
    if user_id:
        stmt = stmt.where(LoanApplication.user_id == user_id)
    items = (await db.execute(stmt)).scalars().all()
    return json.dumps([_orm_to_dict(l) for l in items], ensure_ascii=False, indent=2, default=str)


async def _execute_sql_impl(*, db: AsyncSession, sql: str) -> str:
    """执行只读 SQL 查询做数据分析 (仅允许 SELECT)."""
    sql_lower = sql.strip().lower()
    # 安全限制: 只允许 SELECT, 防写操作
    if not sql_lower.startswith("select"):
        return "仅支持 SELECT 查询"
    rows = (await db.execute(sql)).all()
    return json.dumps([_row_to_dict(r) for r in rows], ensure_ascii=False, indent=2, default=str)


# ============================================================
# @tool 包装层 (8 个 LangChain 工具)
# ============================================================

@tool(
    description=(
        "对指定用户和事件执行实时风控检查。"
        "参数: user_id (用户ID)、event_type (事件类型, 可选值: 信用卡/贷款/转账/登录)、source_id (关联业务ID, 如交易号/订单号)。"
        "返回: 风控评估结果 JSON, 含评分、风险等级、决策和命中规则。"
        "内部: 走 process_event 流水线 (校验→黑名单→补全→决策)。"
    )
)
async def check_risk(user_id: str, event_type: str, source_id: str) -> str:
    return await _safe_call("风控检查", _check_risk_impl,
                            user_id=user_id, event_type=event_type, source_id=source_id)


@tool(
    description=(
        "查询风控规则列表。"
        "参数: category (规则分类筛选, 可选)、enabled_only (只查启用的规则, 默认 False)。"
        "返回: 规则列表 JSON。"
    )
)
async def query_rules(category: str = "", enabled_only: bool = False) -> str:
    return await _safe_call("规则查询", _query_rules_impl,
                            category=category, enabled_only=enabled_only)


@tool(
    description=(
        "查询风控案件列表。"
        "参数: status (案件状态筛选, 可选值: 待审核/审核中/已通过/已拒绝/已关闭, 为空查全部)、page (页码, 默认1)。"
        "返回: 案件列表 JSON。"
    )
)
async def query_cases(status: str = "", page: int = 1) -> str:
    return await _safe_call("案件查询", _query_cases_impl, status=status, page=page)


@tool(
    description=(
        "查询黑名单列表。"
        "参数: blacklist_type (黑名单类型筛选, 可选, 如 用户/银行卡/手机号)。"
        "返回: 黑名单列表 JSON。"
    )
)
async def query_blacklist(blacklist_type: str = "") -> str:
    return await _safe_call("黑名单查询", _query_blacklist_impl, blacklist_type=blacklist_type)


@tool(
    description=(
        "查询用户信息及其银行卡。"
        "参数: user_id (用户ID)。"
        "返回: 用户信息 + 银行卡列表 JSON。"
    )
)
async def query_user_info(user_id: str) -> str:
    return await _safe_call("用户信息查询", _query_user_info_impl, user_id=user_id)


@tool(
    description=(
        "查询交易记录。"
        "参数: user_id (用户ID, 可选, 为空查全部)、limit (返回条数, 默认10)。"
        "返回: 交易记录列表 JSON。"
    )
)
async def query_transactions(user_id: str = "", limit: int = 10) -> str:
    return await _safe_call("交易查询", _query_transactions_impl, user_id=user_id, limit=limit)


@tool(
    description=(
        "查询贷款申请记录。"
        "参数: user_id (用户ID, 可选, 为空查全部)、limit (返回条数, 默认10)。"
        "返回: 贷款申请列表 JSON。"
    )
)
async def query_loan_applications(user_id: str = "", limit: int = 10) -> str:
    return await _safe_call("贷款申请查询", _query_loan_applications_impl, user_id=user_id, limit=limit)


@tool(
    description=(
        "执行只读 SQL 查询做数据分析。仅支持 SELECT 语句, 禁止写操作。"
        "参数: sql (SQL 查询语句)。"
        "返回: 查询结果 JSON。"
    )
)
async def execute_sql(sql: str) -> str:
    return await _safe_call("SQL查询", _execute_sql_impl, sql=sql)


# ============================================================
# 工具列表导出
# ============================================================
def get_all_tools() -> list:
    """返回全部 8 个 @tool (风控决策 4 + 数据分析 4)."""
    return [
        check_risk, query_rules, query_cases, query_blacklist,
        query_user_info, query_transactions, query_loan_applications, execute_sql,
    ]
