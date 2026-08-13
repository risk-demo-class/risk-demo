"""八个银行风控 Agent 工具及其固定权限边界。"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

import ulid
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models import Decision, EventType
from app.models_business import (
    BankAccount,
    BankTransaction,
    CustomerInfo,
    LoanApplication,
    LoginLog,
)
from app.models_risk import (
    BlacklistType,
    CaseStatus,
    RiskAssessment,
    RiskBlacklist,
    RiskRule,
)
from app.schemas import RiskCheckRequest
from app.service.admin import (
    case_statistics,
    dashboard_overview,
    list_blacklist,
    list_cases,
    mask_sensitive_value,
    user_profile,
)
from app.service.event import process_event


logger = logging.getLogger(__name__)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"无法序列化类型: {type(value).__name__}")


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=_json_default)


async def _safe_db_call(label: str, operation, **kwargs: Any) -> str:
    try:
        async with AsyncSessionLocal() as db:
            return await operation(db=db, **kwargs)
    except Exception:
        error_id = f"agt_{ulid.new().str.lower()[:12]}"
        # 不记录工具实参，避免查询值或业务标识进入异常日志。
        logger.exception("Agent 工具失败 tool=%s error_id=%s", label, error_id)
        return _dumps({"ok": False, "error": f"{label}暂不可用", "error_id": error_id})


class RiskCheckArgs(BaseModel):
    user_id: str = Field(min_length=1, max_length=50)
    event_type: EventType
    source_id: str = Field(min_length=1, max_length=50)


class QueryCasesArgs(BaseModel):
    status: CaseStatus | None = None
    page: int = Field(default=1, ge=1)


class UserProfileArgs(BaseModel):
    user_id: str = Field(min_length=1, max_length=50)


class BlacklistArgs(BaseModel):
    action: Literal["list", "check", "add", "remove"] = "list"
    blacklist_type: BlacklistType | None = None
    value: str = Field(default="", max_length=200)


class EmptyArgs(BaseModel):
    pass


class TrendArgs(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


class BankingDataArgs(BaseModel):
    query_type: Literal["customer", "accounts", "transactions", "logins", "loans"]
    user_id: str = Field(default="", max_length=50)
    limit: int = Field(default=10, ge=1, le=50)


async def _risk_check_impl(
    *, db: AsyncSession, user_id: str, event_type: EventType, source_id: str
) -> str:
    result = await process_event(
        db,
        RiskCheckRequest(event_type=event_type, source_id=source_id, user_id=user_id),
    )
    payload = result.model_dump(mode="json")
    payload["write_notice"] = "本工具已写入 risk_event/risk_feature/risk_assessment，并可能创建案件"
    return _dumps(payload)


async def risk_check(user_id: str, event_type: EventType, source_id: str) -> str:
    return await _safe_db_call(
        "risk_check", _risk_check_impl,
        user_id=user_id, event_type=event_type, source_id=source_id,
    )


async def _query_cases_impl(
    *, db: AsyncSession, status: CaseStatus | None, page: int
) -> str:
    result = await list_cases(
        db, status=status, user_id=None, active_only=status is None,
        page=page, page_size=20,
    )
    stats = await case_statistics(db)
    return _dumps(
        {
            "items": [item.model_dump(mode="json") for item in result.items],
            "total": result.total, "page": result.page,
            "statistics": stats.model_dump(mode="json"),
        }
    )


async def query_cases(status: CaseStatus | None = None, page: int = 1) -> str:
    return await _safe_db_call("query_cases", _query_cases_impl, status=status, page=page)


async def _query_user_profile_impl(*, db: AsyncSession, user_id: str) -> str:
    result = await user_profile(db, user_id)
    if result is None:
        return _dumps({"found": False, "user_id": user_id, "message": "尚无画像，请先执行风控检查"})
    return _dumps({"found": True, **result.model_dump(mode="json")})


async def query_user_profile(user_id: str) -> str:
    return await _safe_db_call("query_user_profile", _query_user_profile_impl, user_id=user_id)


async def _manage_blacklist_impl(
    *, db: AsyncSession, action: str, blacklist_type: BlacklistType | None, value: str
) -> str:
    # 写权限在函数内部硬编码拒绝，系统提示词或用户提示词都无法绕过。
    if action in {"add", "remove"}:
        return _dumps(
            {
                "ok": False,
                "restricted": True,
                "message": "AI 助手无黑名单写权限，请到黑名单页面由人工确认并留下审计日志",
            }
        )
    if action == "list":
        result = await list_blacklist(
            db, blacklist_type=blacklist_type, page=1, page_size=50
        )
        return _dumps(result.model_dump(mode="json"))
    if blacklist_type is None or not value:
        return _dumps({"ok": False, "message": "check 需要 blacklist_type 和 value"})
    now = datetime.now(UTC).replace(tzinfo=None)
    row = (
        await db.execute(
            select(RiskBlacklist).where(
                RiskBlacklist.blacklist_type == blacklist_type,
                RiskBlacklist.blacklist_value == value,
                RiskBlacklist.deleted_at.is_(None),
                or_(RiskBlacklist.expire_time.is_(None), RiskBlacklist.expire_time > now),
            ).limit(1)
        )
    ).scalar_one_or_none()
    return _dumps(
        {
            "matched": row is not None,
            "blacklist_type": blacklist_type.value,
            "value_masked": mask_sensitive_value(value),
        }
    )


async def manage_blacklist(
    action: str = "list",
    blacklist_type: BlacklistType | None = None,
    value: str = "",
) -> str:
    return await _safe_db_call(
        "manage_blacklist", _manage_blacklist_impl,
        action=action, blacklist_type=blacklist_type, value=value,
    )


async def _query_dashboard_stats_impl(*, db: AsyncSession) -> str:
    return _dumps((await dashboard_overview(db)).model_dump(mode="json"))


async def query_dashboard_stats() -> str:
    return await _safe_db_call("query_dashboard_stats", _query_dashboard_stats_impl)


async def _analyze_risk_trend_impl(*, db: AsyncSession, days: int) -> str:
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    rows = (
        await db.execute(
            select(
                func.date(RiskAssessment.create_time).label("day"),
                func.count(RiskAssessment.assessment_id).label("total"),
                func.sum(
                    case(
                        (RiskAssessment.decision.in_((Decision.MANUAL_REVIEW, Decision.REJECT)), 1),
                        else_=0,
                    )
                ).label("positive"),
            )
            .where(RiskAssessment.create_time >= since)
            .group_by(func.date(RiskAssessment.create_time))
            .order_by(func.date(RiskAssessment.create_time))
        )
    ).all()
    return _dumps(
        {
            "days": days,
            "daily": [
                {"date": str(row.day), "assessments": int(row.total or 0),
                 "manual_or_reject": int(row.positive or 0)}
                for row in rows
            ],
        }
    )


async def analyze_risk_trend(days: int = 30) -> str:
    return await _safe_db_call("analyze_risk_trend", _analyze_risk_trend_impl, days=days)


async def _analyze_rule_effectiveness_impl(*, db: AsyncSession) -> str:
    assessments = (
        await db.execute(
            select(RiskAssessment.rule_results)
            .order_by(RiskAssessment.create_time.desc())
            .limit(1000)
        )
    ).scalars().all()
    hits: Counter[str] = Counter()
    for value in assessments:
        if not value:
            continue
        items = json.loads(value) if isinstance(value, str) else value
        hits.update(item.get("rule_id") for item in items if item.get("rule_id"))
    rules = (
        await db.execute(
            select(RiskRule).where(
                RiskRule.is_enabled.is_(True), RiskRule.deleted_at.is_(None)
            ).order_by(RiskRule.priority.desc())
        )
    ).scalars().all()
    denominator = max(len(assessments), 1)
    return _dumps(
        {
            "sampled_assessments": len(assessments),
            "rules": [
                {
                    "rule_id": rule.rule_id, "rule_name": rule.rule_name,
                    "hit_count": hits[rule.rule_id],
                    "hit_rate": round(hits[rule.rule_id] / denominator, 4),
                }
                for rule in rules
            ],
        }
    )


async def analyze_rule_effectiveness() -> str:
    return await _safe_db_call(
        "analyze_rule_effectiveness", _analyze_rule_effectiveness_impl
    )


async def _query_banking_data_impl(
    *, db: AsyncSession, query_type: str, user_id: str, limit: int
) -> str:
    allowed = {"customer", "accounts", "transactions", "logins", "loans"}
    if query_type not in allowed:
        return _dumps({"ok": False, "message": f"不支持的 query_type: {query_type}"})
    if not user_id:
        return _dumps({"ok": False, "message": "银行业务查询必须提供 user_id"})
    if query_type == "customer":
        customer = await db.get(CustomerInfo, user_id)
        if customer is None:
            return _dumps({"found": False, "user_id": user_id})
        # 姓名、证件、手机哈希也不交给 LLM；哈希并不等于可随意外发。
        return _dumps(
            {
                "found": True, "user_id": customer.user_id,
                "credit_score": customer.credit_score, "kyc_level": customer.kyc_level,
                "monthly_income": customer.monthly_income, "home_city": customer.home_city,
                "register_at": customer.register_at, "status": customer.status,
            }
        )
    if query_type == "accounts":
        rows = (
            await db.execute(
                select(BankAccount).where(BankAccount.user_id == user_id).limit(limit)
            )
        ).scalars().all()
        return _dumps([
            {"account_id": row.account_id, "account_type": row.account_type,
             "balance": row.balance, "available_balance": row.available_balance,
             "home_branch": row.home_branch, "status": row.status}
            for row in rows
        ])
    if query_type == "transactions":
        rows = (
            await db.execute(
                select(BankTransaction).where(BankTransaction.user_id == user_id)
                .order_by(BankTransaction.txn_time.desc()).limit(limit)
            )
        ).scalars().all()
        return _dumps([
            {"txn_id": row.txn_id, "amount": row.amount, "txn_type": row.txn_type,
             "channel": row.channel, "geo": row.geo, "txn_time": row.txn_time,
             "status": row.status,
             "beneficiary_masked": mask_sensitive_value(row.beneficiary_account_hash or "")}
            for row in rows
        ])
    if query_type == "logins":
        rows = (
            await db.execute(
                select(LoginLog).where(LoginLog.user_id == user_id)
                .order_by(LoginLog.login_at.desc()).limit(limit)
            )
        ).scalars().all()
        return _dumps([
            {"login_id": row.login_id, "device_id": row.device_id,
             "ip_masked": mask_sensitive_value(row.ip), "geo": row.geo,
             "success": row.success, "login_at": row.login_at}
            for row in rows
        ])
    rows = (
        await db.execute(
            select(LoanApplication).where(LoanApplication.user_id == user_id)
            .order_by(LoanApplication.apply_at.desc()).limit(limit)
        )
    ).scalars().all()
    return _dumps([
        {"loan_id": row.loan_id, "institution_code": row.institution_code,
         "amount": row.amount, "term_months": row.term_months,
         "debt_ratio": row.debt_ratio, "apply_at": row.apply_at, "status": row.status}
        for row in rows
    ])


async def query_banking_data(
    query_type: str, user_id: str = "", limit: int = 10
) -> str:
    return await _safe_db_call(
        "query_banking_data", _query_banking_data_impl,
        query_type=query_type, user_id=user_id, limit=limit,
    )


def build_langchain_tools() -> list[Any]:
    """惰性导入 LangChain，使未安装 agent extra 时主应用仍可启动。"""

    from langchain_core.tools import StructuredTool

    definitions = [
        (risk_check, RiskCheckArgs, "risk_check", "执行真实银行风险检查；会写评估记录，调用前必须向用户说明。"),
        (query_cases, QueryCasesArgs, "query_cases", "只读查询案件列表和统计。"),
        (query_user_profile, UserProfileArgs, "query_user_profile", "只读查询客户风险画像。"),
        (manage_blacklist, BlacklistArgs, "manage_blacklist", "只允许 list/check；add/remove 后端固定拒绝并要求人工确认。"),
        (query_dashboard_stats, EmptyArgs, "query_dashboard_stats", "只读查询仪表盘聚合统计。"),
        (analyze_risk_trend, TrendArgs, "analyze_risk_trend", "只读分析 1 至 365 天风险趋势。"),
        (analyze_rule_effectiveness, EmptyArgs, "analyze_rule_effectiveness", "只读分析规则命中效果。"),
        (query_banking_data, BankingDataArgs, "query_banking_data", "只读查询模拟银行数据；结果已脱敏且不含身份哈希。"),
    ]
    return [
        StructuredTool.from_function(
            coroutine=func, name=name, description=description, args_schema=args_schema
        )
        for func, args_schema, name, description in definitions
    ]


ALL_TOOL_NAMES = (
    "risk_check", "query_cases", "query_user_profile", "manage_blacklist",
    "query_dashboard_stats", "analyze_risk_trend",
    "analyze_rule_effectiveness", "query_banking_data",
)
