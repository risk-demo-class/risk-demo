"""
AI Agent 工具集 — 8 个 @tool (教育风控场景)
内部 _impl 函数做实际工作,@tool 函数做薄包装 + 类型注解(让 LLM 知道怎么调)。
每个 @tool 内部自行创建独立 DB 会话,LLM 无需感知 db。
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.models import (
    CourseInfo, Enrollment, ExamRecord, PaymentRecord, RefundRecord, RiskAssessment,
    RiskBlacklist, RiskCase, RiskEvent, RiskUserProfile,
)

# langchain 可选: 未安装时 AI 层降级,核心风控不受影响
try:
    from langchain_core.tools import tool
except ImportError:
    def tool(func=None, *args, **kwargs):
        """未安装 langchain 时的空装饰器(等价 @tool 原样返回)。"""
        if func is None:
            return lambda f: f
        return func

logger = logging.getLogger(__name__)


def _session():
    """每个工具调用独立会话(显式 close)。"""
    from app.database import AsyncSessionLocal
    return AsyncSessionLocal()


# ============================================================
# 工具 1: 触发一次风控检查
# ============================================================

async def _impl_risk_check(db, event_type: str, source_id: str, user_id: str) -> dict:
    from app.service.event import process_event
    return await process_event(db, {
        "event_type": event_type, "source_id": source_id, "user_id": user_id,
    })


@tool
async def risk_check(event_type: str, source_id: str, user_id: str) -> dict:
    """对一笔教育业务(报名/缴费/退费/考试/作业)执行风控检查,返回评分与决策。"""
    db = _session()
    try:
        return await _impl_risk_check(db, event_type, source_id, user_id)
    finally:
        await db.close()


# ============================================================
# 工具 2: 查询案件
# ============================================================

async def _impl_query_cases(db, status: str | None = None, user_id: str | None = None,
                            limit: int = 20) -> list:
    stmt = select(RiskCase).order_by(RiskCase.create_time.desc()).limit(limit)
    if status:
        stmt = stmt.where(RiskCase.case_status == status)
    if user_id:
        stmt = stmt.where(RiskCase.user_id == user_id)
    rows = (await db.execute(stmt)).scalars().all()
    return [{
        "case_id": c.case_id, "user_id": c.user_id, "source_id": c.source_id,
        "event_type": c.event_type, "case_status": c.case_status,
        "create_time": c.create_time.isoformat() if c.create_time else None,
    } for c in rows]


@tool
async def query_cases(status: str | None = None, user_id: str | None = None,
                      limit: int = 20) -> list:
    """查询风险案件列表,可按状态(待审核/审核中/已通过/已拒绝/已关闭)和学员过滤。"""
    db = _session()
    try:
        return await _impl_query_cases(db, status, user_id, limit)
    finally:
        await db.close()


# ============================================================
# 工具 3: 查询用户风险画像
# ============================================================

async def _impl_query_user_profile(db, user_id: str) -> dict:
    profile = (await db.execute(
        select(RiskUserProfile).where(RiskUserProfile.user_id == user_id))).scalar_one_or_none()
    black = (await db.execute(
        select(RiskBlacklist).where(RiskBlacklist.user_id == user_id,
                                    RiskBlacklist.status == "生效",
                                    RiskBlacklist.is_deleted.is_(False)))).scalar_one_or_none()
    return {
        "user_id": user_id,
        "total_checks": profile.total_checks if profile else 0,
        "total_cases": profile.total_cases if profile else 0,
        "max_score": float(profile.max_score) if profile else 0,
        "avg_score": float(profile.avg_score) if profile else 0,
        "risk_tag": profile.risk_tag if profile else "正常",
        "in_blacklist": black is not None,
        "blacklist_reason": black.reason if black else None,
    }


@tool
async def query_user_profile(user_id: str) -> dict:
    """查询学员风险画像(累计检查次数/案件数/最高分/风险标签/黑名单状态)。"""
    db = _session()
    try:
        return await _impl_query_user_profile(db, user_id)
    finally:
        await db.close()


# ============================================================
# 工具 4: 黑名单管理
# ============================================================

async def _impl_manage_blacklist(db, action: str, user_id: str,
                                 reason: str = "", blacklist_id: str = "") -> dict:
    from app.models import gen_id
    if action == "add":
        row = RiskBlacklist(blacklist_id=gen_id("BL"),
                            user_id=user_id, reason=reason or "AI 拉黑", source="AI")
        db.add(row)
        await db.commit()
        return {"ok": True, "message": f"已拉黑 {user_id}"}
    if action == "release":
        if blacklist_id:
            row = (await db.execute(select(RiskBlacklist).where(
                RiskBlacklist.blacklist_id == blacklist_id))).scalar_one_or_none()
        else:
            row = (await db.execute(select(RiskBlacklist).where(
                RiskBlacklist.user_id == user_id, RiskBlacklist.status == "生效"))).scalar_one_or_none()
        if row:
            row.status = "解除"
            await db.commit()
            return {"ok": True, "message": f"已解除 {row.user_id}"}
        return {"ok": False, "message": "未找到黑名单记录"}
    if action == "query":
        rows = (await db.execute(select(RiskBlacklist).where(
            RiskBlacklist.status == "生效").limit(50))).scalars().all()
        return {"ok": True, "items": [{"user_id": b.user_id, "reason": b.reason} for b in rows]}
    return {"ok": False, "message": f"未知动作: {action}"}


@tool
async def manage_blacklist(action: str, user_id: str = "", reason: str = "",
                           blacklist_id: str = "") -> dict:
    """黑名单增删查: action=add(拉黑)/release(解除)/query(列表)。"""
    db = _session()
    try:
        return await _impl_manage_blacklist(db, action, user_id, reason, blacklist_id)
    finally:
        await db.close()


# ============================================================
# 工具 5: 仪表盘统计
# ============================================================

async def _impl_query_dashboard_stats(db, days: int = 7) -> dict:
    since = datetime.now() - timedelta(days=days)
    checks = (await db.execute(select(func.count(RiskEvent.event_id)).where(
        RiskEvent.create_time >= since))).scalar() or 0
    pending = (await db.execute(select(func.count(RiskCase.case_id)).where(
        RiskCase.case_status == "待审核"))).scalar() or 0
    decision_rows = (await db.execute(
        select(RiskAssessment.decision, func.count())
        .join(RiskEvent, RiskEvent.event_id == RiskAssessment.event_id)
        .where(RiskEvent.create_time >= since).group_by(RiskAssessment.decision))).all()
    return {
        "window_days": days,
        "total_checks": checks,
        "pending_cases": pending,
        "decision_distribution": {d: c for d, c in decision_rows},
    }


@tool
async def query_dashboard_stats(days: int = 7) -> dict:
    """查询风控运营大盘统计(检查量/待审核案件/决策分布)。"""
    db = _session()
    try:
        return await _impl_query_dashboard_stats(db, days)
    finally:
        await db.close()


# ============================================================
# 工具 6: 风险趋势分析
# ============================================================

async def _impl_analyze_risk_trend(db, days: int = 7) -> list:
    since = datetime.now() - timedelta(days=days)
    rows = (await db.execute(
        select(func.date(RiskEvent.create_time), func.count())
        .where(RiskEvent.create_time >= since)
        .group_by(func.date(RiskEvent.create_time))
        .order_by(func.date(RiskEvent.create_time)))).all()
    return [{"date": str(d), "count": c} for d, c in rows]


@tool
async def analyze_risk_trend(days: int = 7) -> list:
    """分析近 N 天风控检查量趋势(按天)。"""
    db = _session()
    try:
        return await _impl_analyze_risk_trend(db, days)
    finally:
        await db.close()


# ============================================================
# 工具 7: 规则命中率分析
# ============================================================

async def _impl_analyze_rule_effectiveness(db, top_n: int = 10) -> dict:
    assessments = (await db.execute(
        select(RiskAssessment).where(RiskAssessment.hit_rules.is_not(None))
        .limit(2000))).scalars().all()
    from collections import Counter
    counter = Counter()
    for a in assessments:
        for hit in (a.hit_rules or []):
            counter[hit.get("rule_id", "?")] += 1
    total = sum(counter.values())
    return {
        "total_assessments": len(assessments),
        "top_rules": [{"rule_id": rid, "count": c, "rate": round(c / total, 4) if total else 0}
                      for rid, c in counter.most_common(top_n)],
    }


@tool
async def analyze_rule_effectiveness(top_n: int = 10) -> dict:
    """分析规则命中率,找出最活跃的风险规则。"""
    db = _session()
    try:
        return await _impl_analyze_rule_effectiveness(db, top_n)
    finally:
        await db.close()


# ============================================================
# 工具 8: 教育业务数据查询
# ============================================================

async def _impl_query_business_data(db, biz_type: str, user_id: str | None = None,
                                    limit: int = 20) -> list:
    if biz_type == "enrollments":
        stmt = select(Enrollment).order_by(Enrollment.create_time.desc()).limit(limit)
        if user_id:
            stmt = stmt.where(Enrollment.user_id == user_id)
        rows = (await db.execute(stmt)).scalars().all()
        return [{"enrollment_id": e.enrollment_id, "user_id": e.user_id,
                 "status": e.status, "total_amount": float(e.total_amount)} for e in rows]
    if biz_type == "payments":
        stmt = select(PaymentRecord).order_by(PaymentRecord.pay_time.desc()).limit(limit)
        if user_id:
            stmt = stmt.where(PaymentRecord.user_id == user_id)
        rows = (await db.execute(stmt)).scalars().all()
        return [{"payment_id": p.payment_id, "user_id": p.user_id,
                 "amount": float(p.amount), "status": p.status} for p in rows]
    if biz_type == "refunds":
        stmt = select(RefundRecord).order_by(RefundRecord.apply_time.desc()).limit(limit)
        if user_id:
            stmt = stmt.where(RefundRecord.user_id == user_id)
        rows = (await db.execute(stmt)).scalars().all()
        return [{"refund_id": r.refund_id, "user_id": r.user_id,
                 "amount": float(r.amount), "reason": r.reason, "status": r.status} for r in rows]
    if biz_type == "exams":
        stmt = select(ExamRecord).order_by(ExamRecord.exam_time.desc()).limit(limit)
        if user_id:
            stmt = stmt.where(ExamRecord.user_id == user_id)
        rows = (await db.execute(stmt)).scalars().all()
        return [{"exam_id": e.exam_id, "user_id": e.user_id, "score": float(e.score),
                 "cheat_flag": e.cheat_flag} for e in rows]
    if biz_type == "courses":
        rows = (await db.execute(select(CourseInfo).limit(limit))).scalars().all()
        return [{"course_id": c.course_id, "course_name": c.course_name,
                 "price": float(c.price)} for c in rows]
    return [{"error": f"未知业务类型: {biz_type}(可选 enrollments/payments/refunds/exams/courses)"}]


@tool
async def query_business_data(biz_type: str, user_id: str | None = None,
                              limit: int = 20) -> list:
    """查询教育业务数据: biz_type=报名(enrollments)/缴费(payments)/退费(refunds)/考试(exams)/课程(courses)。"""
    db = _session()
    try:
        return await _impl_query_business_data(db, biz_type, user_id, limit)
    finally:
        await db.close()


ALL_TOOLS = [
    risk_check, query_cases, query_user_profile, manage_blacklist,
    query_dashboard_stats, analyze_risk_trend, analyze_rule_effectiveness,
    query_business_data,
]
