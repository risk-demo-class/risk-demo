"""教育风控 AI Agent 工具集（8 个 LangChain @tool，同步 DB 访问）。

架构: 业务实现写在 loader 函数里, 统一经 _safe_call 包装异常 → 返回带 error_id 的字符串,
不让单次工具失败拖垮整轮 Agent 对话。

工具 (education 领域):
  风控决策 (4): risk_check / query_cases / query_user_profile / manage_blacklist
  数据分析 (4): query_dashboard_stats / analyze_risk_trend / analyze_rule_effectiveness / query_business_data
"""

from __future__ import annotations

import json
import logging
import ulid
from datetime import date, datetime
from decimal import Decimal

from langchain_core.tools import tool
from sqlalchemy import desc, func, select

from app.database import SessionLocal
from app.engine.feature import compute_account_features
from app.models_business import (
    BlacklistExtra, EducationCredential, LiveReward, OrderInfo, RefundRequest, UserInfo,
)
from app.models_risk import RiskAssessment, RiskCase, RiskRule
from app.schemas import RiskCheckRequest
from app.service.risk import run_risk_check

logger = logging.getLogger(__name__)


def _dumps(obj) -> str:
    """JSON 序列化, 处理 Decimal / datetime 等不可默认序列化类型。"""
    def _conv(v):
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        if isinstance(v, dict):
            return {k: _conv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [_conv(x) for x in v]
        return v
    return json.dumps(_conv(obj), ensure_ascii=False, default=str)


def _safe_call(label: str, loader, **kwargs) -> str:
    """共享执行模板: 开 session → 调 loader(db, **kwargs) → 异常转字符串。"""
    try:
        with SessionLocal() as db:
            result = loader(db=db, **kwargs)
            return _dumps(result)
    except Exception as exc:
        error_id = ulid.new().str.lower()[:12]
        logger.exception("%s 执行失败 [error_id=%s]", label, error_id)
        return json.dumps({"ok": False, "error": f"{label}失败: {exc}", "error_id": error_id}, ensure_ascii=False)


# ============================================================
# 风控决策工具 (4)
# ============================================================


def _risk_check_loader(db, user_id: str, event_type: str, source_id: str,
                       order_id: str | None = None, refund_id: str | None = None,
                       live_session_id: str | None = None) -> dict:
    req = RiskCheckRequest(
        event_type=event_type, source_id=source_id, user_id=user_id,
        order_id=order_id, refund_id=refund_id, live_session_id=live_session_id,
    )
    return run_risk_check(db, req)


@tool
def risk_check(user_id: str, event_type: str, source_id: str,
               order_id: str | None = None, refund_id: str | None = None,
               live_session_id: str | None = None) -> str:
    """对指定用户与事件执行一次实时风控检查。

    Args:
        user_id: 用户ID (如 RISK-STU-001)
        event_type: 事件类型 (报名支付成功/退费申请提交/退款成功/直播打赏变更/学历核验完成/设备关联更新)
        source_id: 关联业务ID
        order_id: 报名支付成功 事件必填 (订单号)
        refund_id: 退费申请提交/退款成功 事件必填 (退费单号)
        live_session_id: 直播打赏变更 事件必填 (直播场次ID)
    """
    return _safe_call(
        "风险检查", _risk_check_loader,
        user_id=user_id, event_type=event_type, source_id=str(source_id),
        order_id=order_id, refund_id=refund_id, live_session_id=live_session_id,
    )


def _case_to_dict(row: RiskCase, db) -> dict:
    assessment = db.get(RiskAssessment, row.assessment_id)
    return {
        "case_id": row.case_id, "user_id": row.user_id, "case_status": row.case_status,
        "case_category": row.case_category,
        "final_score": assessment.final_score if assessment else None,
        "risk_level": assessment.risk_level if assessment else None,
        "reviewer": row.reviewer, "created_at": row.created_at,
    }


def _query_cases_loader(db, status: str | None = None, page: int = 1, page_size: int = 20) -> dict:
    stmt = select(RiskCase).order_by(desc(RiskCase.created_at))
    if status:
        stmt = stmt.where(RiskCase.case_status == status)
    rows = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)))
    return {"page": page, "page_size": page_size, "items": [_case_to_dict(r, db) for r in rows]}


@tool
def query_cases(status: str | None = None, page: int = 1, page_size: int = 20) -> str:
    """查询风控案件列表 (可按状态过滤: 待审核/审核中/已通过/已拒绝/已关闭)。"""
    return _safe_call("案件查询", _query_cases_loader, status=status, page=page, page_size=page_size)


def _profile_loader(db, user_id: str) -> dict:
    user = db.get(UserInfo, user_id)
    if not user:
        raise ValueError(f"用户 {user_id} 不存在")
    feats = compute_account_features(db, user_id)
    orders = db.scalar(select(func.count()).select_from(OrderInfo).where(OrderInfo.user_id == user_id)) or 0
    refunds = db.scalar(
        select(func.count()).select_from(RefundRequest)
        .join(OrderInfo, OrderInfo.order_id == RefundRequest.order_id)
        .where(OrderInfo.user_id == user_id, RefundRequest.refund_status == "退款成功")
    ) or 0
    latest = db.scalar(select(RiskAssessment).where(RiskAssessment.user_id == user_id).order_by(desc(RiskAssessment.created_at)).limit(1))
    return {
        "user": {"user_id": user.user_id, "name": user.name, "role": user.role,
                 "student_id": user.student_id, "real_name_status": user.real_name_status,
                 "register_at": user.register_at},
        "metrics": {"orders": orders, "successful_refunds": refunds, **feats},
        "latest_assessment": {
            "final_score": latest.final_score, "risk_level": latest.risk_level,
            "decision": latest.decision, "rule_count": latest.rule_count,
            "ml_score": latest.ml_score, "ml_decision": latest.ml_decision, "created_at": latest.created_at,
        } if latest else None,
    }


@tool
def query_user_profile(user_id: str) -> str:
    """查询用户风险画像: 基本信息 + 账号特征 + 业务统计 + 最近一次风控评估。"""
    return _safe_call("用户画像", _profile_loader, user_id=user_id)


def _blacklist_add(db, btype: str, value: str, reason: str) -> dict:
    row = db.scalar(select(BlacklistExtra).where(BlacklistExtra.type == btype, BlacklistExtra.value == value))
    if row:
        row.status, row.deleted_at = "启用", None
        row.reason = reason
    else:
        db.add(BlacklistExtra(type=btype, value=value, value_masked=value, reason=reason, status="启用", created_by="agent"))
    db.commit()
    return {"ok": True, "action": "add", "type": btype, "value": value}


def _blacklist_check(db, btype: str, value: str) -> dict:
    row = db.scalar(select(BlacklistExtra).where(
        BlacklistExtra.type == btype, BlacklistExtra.value == value,
        BlacklistExtra.status == "启用", BlacklistExtra.deleted_at.is_(None),
    ))
    return {"hit": row is not None, "type": btype, "value": value}


def _blacklist_list(db, btype: str | None = None, limit: int = 20) -> dict:
    stmt = select(BlacklistExtra).where(BlacklistExtra.deleted_at.is_(None)).order_by(desc(BlacklistExtra.created_at)).limit(limit)
    if btype:
        stmt = stmt.where(BlacklistExtra.type == btype)
    rows = list(db.scalars(stmt))
    return {"items": [{"entry_id": r.entry_id, "type": r.type, "value": r.value_masked or r.value,
                       "reason": r.reason, "status": r.status} for r in rows]}


def _blacklist_loader(db, action: str, btype: str, value: str | None = None, reason: str | None = None, limit: int = 20) -> dict:
    if action == "add":
        if not value or not reason:
            raise ValueError("add 需要 value 和 reason")
        return _blacklist_add(db, btype, value, reason)
    if action == "check":
        if not value:
            raise ValueError("check 需要 value")
        return _blacklist_check(db, btype, value)
    if action == "list":
        return _blacklist_list(db, btype, limit)
    raise ValueError(f"未知 blacklist action: {action}")


@tool
def manage_blacklist(action: str, btype: str, value: str | None = None, reason: str | None = None, limit: int = 20) -> str:
    """黑名单管理。action: add(加)/check(查是否命中)/list(列表)。btype: 用户ID/学号/身份证/设备指纹/直播账号。"""
    return _safe_call("黑名单管理", _blacklist_loader, action=action, btype=btype, value=value, reason=reason, limit=limit)



# ============================================================
# 数据分析工具 (4)
# ============================================================


def _stats_loader(db) -> dict:
    total = db.scalar(select(func.count()).select_from(RiskAssessment)) or 0
    positive = db.scalar(select(func.count()).select_from(RiskAssessment).where(RiskAssessment.decision != "通过")) or 0
    pending = db.scalar(select(func.count()).select_from(RiskCase).where(RiskCase.case_status == "待审核")) or 0
    decision_rows = db.execute(select(RiskAssessment.decision, func.count()).group_by(RiskAssessment.decision)).all()
    return {
        "assessment_count": total, "risk_count": positive,
        "risk_rate": round(positive / total, 4) if total else 0,
        "pending_cases": pending, "decision_distribution": dict(decision_rows),
    }


@tool
def query_dashboard_stats() -> str:
    """查询风控仪表盘统计: 评估总数 / 风险数 / 待审核案件 / 决策分布。"""
    return _safe_call("仪表盘统计", _stats_loader)


def _trend_loader(db, days: int = 7) -> dict:
    from datetime import timedelta
    since = datetime.now() - timedelta(days=days)
    rows = db.execute(
        select(func.date(RiskAssessment.created_at), RiskAssessment.decision, func.count())
        .where(RiskAssessment.created_at >= since)
        .group_by(func.date(RiskAssessment.created_at), RiskAssessment.decision)
    ).all()
    daily: dict = {}
    for d, decision, cnt in rows:
        daily.setdefault(str(d), {}).setdefault(decision, 0)
        daily[str(d)][decision] += cnt
    return {"days": days, "daily": daily}


@tool
def analyze_risk_trend(days: int = 7) -> str:
    """分析最近 N 天每日风险的决策分布趋势。"""
    return _safe_call("风险趋势", _trend_loader, days=days)


def _rule_effectiveness_loader(db, top_n: int = 5) -> dict:
    from collections import Counter
    cnt = Counter()
    rows = list(db.scalars(select(RiskAssessment).where(RiskAssessment.rule_count > 0).limit(3000)))
    for r in rows:
        for hit in (r.rule_results or []):
            rid = hit.get("rule_id")
            if rid:
                cnt[rid] += 1
    enabled = {r.rule_id: r.rule_name for r in db.scalars(select(RiskRule).where(RiskRule.enabled.is_(True)))}
    top = [{"rule_id": rid, "rule_name": enabled.get(rid, ""), "hits": c} for rid, c in cnt.most_common(top_n)]
    return {"top_n": top_n, "items": top}


@tool
def analyze_rule_effectiveness(top_n: int = 5) -> str:
    """分析各规则的历史命中次数 (规则效果), 返回命中 TOP N。"""
    return _safe_call("规则效果", _rule_effectiveness_loader, top_n=top_n)


def _biz_loader(db, query_type: str, user_id: str, limit: int = 20) -> dict:
    if query_type == "orders":
        rows = list(db.scalars(select(OrderInfo).where(OrderInfo.user_id == user_id).order_by(desc(OrderInfo.created_at)).limit(limit)))
        return {"items": [{"order_id": o.order_id, "course_id": o.course_id, "total_amount": o.total_amount,
                           "order_status": o.order_status, "created_at": o.created_at, "paid_at": o.paid_at} for o in rows]}
    if query_type == "refunds":
        rows = list(db.scalars(
            select(RefundRequest).join(OrderInfo, OrderInfo.order_id == RefundRequest.order_id)
            .where(OrderInfo.user_id == user_id).order_by(desc(RefundRequest.requested_at)).limit(limit)
        ))
        return {"items": [{"refund_id": r.refund_id, "reason": r.reason, "amount": r.requested_amount,
                           "status": r.refund_status, "study_minutes_before_refund": r.study_minutes_before_refund,
                           "requested_at": r.requested_at} for r in rows]}
    if query_type == "credentials":
        rows = list(db.scalars(select(EducationCredential).where(EducationCredential.user_id == user_id).limit(limit)))
        return {"items": [{"credential_id": c.credential_id, "verify_status": c.verify_status,
                           "submitted_level": c.submitted_education_level, "submitted_at": c.submitted_at} for c in rows]}
    if query_type == "live_rewards":
        rows = list(db.scalars(select(LiveReward).where(LiveReward.user_id == user_id).order_by(desc(LiveReward.rewarded_at)).limit(limit)))
        return {"items": [{"reward_id": r.reward_id, "session_id": r.live_session_id, "type": r.transaction_type,
                           "amount": r.amount, "status": r.reward_status, "rewarded_at": r.rewarded_at} for r in rows]}
    raise ValueError(f"未知业务查询类型: {query_type} (可用 orders/refunds/credentials/live_rewards)")


@tool
def query_business_data(query_type: str, user_id: str, limit: int = 20) -> str:
    """查询用户业务数据。query_type: orders(订单)/refunds(退费)/credentials(学历认证)/live_rewards(直播打赏)。"""
    return _safe_call("业务数据", _biz_loader, query_type=query_type, user_id=user_id, limit=limit)


RISK_TOOLS = [risk_check, query_cases, query_user_profile, manage_blacklist]
DATA_TOOLS = [query_dashboard_stats, analyze_risk_trend, analyze_rule_effectiveness, query_business_data]
ALL_TOOLS = RISK_TOOLS + DATA_TOOLS

