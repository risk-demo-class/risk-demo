"""
银行风控系统 - AI Agent 工具集
=============================
为 AI Agent 提供风控业务工具函数, 让 LLM 能查询和分析风控数据.

【可用工具】
  query_user_info          — 查询用户基本信息
  query_user_transactions  — 查询用户近期交易记录
  query_user_risk_events   — 查询用户风险事件历史
  query_rule_config        — 查询规则配置详情
  query_blacklist          — 查询黑名单命中情况
  analyze_user_risk        — 综合分析用户风险画像
"""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    UserInfo, UserProfile, BankCard, Transaction,
    LoginLog, RiskEvent, RuleConfig, BlacklistExtra,
)

logger = logging.getLogger(__name__)


async def query_user_info(db: AsyncSession, user_id: int) -> dict:
    """
    查询用户基本信息 + 画像 + 绑卡情况.

    Args:
        user_id: 用户 ID

    Returns:
        用户信息字典
    """
    user = (await db.execute(
        select(UserInfo).where(UserInfo.user_id == user_id)
    )).scalar_one_or_none()

    if not user:
        return {"error": f"用户 {user_id} 不存在"}

    profile = (await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )).scalar_one_or_none()

    cards = (await db.execute(
        select(func.count()).select_from(BankCard).where(
            BankCard.user_id == user_id, BankCard.status == 1
        )
    )).scalar() or 0

    status_names = {1: "正常", 2: "冻结", 3: "止付", 4: "销户"}
    kyc_names = {1: "L1要素核验", 2: "L2人脸", 3: "L3证件上传", 4: "L4面签"}

    return {
        "user_id": user.user_id,
        "kyc_level": kyc_names.get(user.kyc_level, "未知"),
        "credit_score": user.credit_score,
        "risk_tag": user.risk_tag,
        "status": status_names.get(user.status, "未知"),
        "register_at": str(user.register_at),
        "profile": {
            "common_city": profile.common_city if profile else None,
            "avg_txn_amount": float(profile.avg_txn_amount) if profile and profile.avg_txn_amount else 0,
            "txn_freq_day": float(profile.txn_freq_day) if profile and profile.txn_freq_day else 0,
            "active_hours": profile.active_hours if profile else None,
        } if profile else None,
        "cards_count": cards,
    }


async def query_user_transactions(
    db: AsyncSession, user_id: int, limit: int = 20,
) -> list[dict]:
    """
    查询用户近期交易记录.

    Args:
        user_id: 用户 ID
        limit: 返回条数

    Returns:
        交易记录列表
    """
    # 通过用户的卡找到交易
    rows = (await db.execute(
        select(Transaction).join(
            BankCard, Transaction.from_card_id == BankCard.card_id
        ).where(
            BankCard.user_id == user_id
        ).order_by(desc(Transaction.created_at)).limit(limit)
    )).scalars().all()

    txn_type_names = {1: "转账", 2: "支付", 3: "取现", 4: "还款", 5: "收款"}
    status_names = {1: "成功", 2: "失败", 3: "挂起", 4: "拒绝"}

    return [
        {
            "txn_id": t.txn_id,
            "from_card_id": t.from_card_id,
            "amount": float(t.amount),
            "txn_type": txn_type_names.get(t.txn_type, "未知"),
            "channel": t.channel,
            "status": status_names.get(t.status, "未知"),
            "risk_score": float(t.risk_score) if t.risk_score else None,
            "created_at": str(t.created_at),
        }
        for t in rows
    ]


async def query_user_risk_events(
    db: AsyncSession, user_id: int, limit: int = 20,
) -> list[dict]:
    """
    查询用户风险事件历史.

    Args:
        user_id: 用户 ID
        limit: 返回条数

    Returns:
        风险事件列表
    """
    rows = (await db.execute(
        select(RiskEvent).where(
            RiskEvent.user_id == user_id
        ).order_by(desc(RiskEvent.created_at)).limit(limit)
    )).scalars().all()

    return [
        {
            "event_id": e.event_id,
            "event_type": e.event_type,
            "risk_score": float(e.risk_score) if e.risk_score else None,
            "decision": e.decision,
            "action": e.action,
            "rule_ids": e.rule_ids,
            "status": {1: "待处理", 2: "已处理", 3: "误报"}.get(e.status, "未知"),
            "created_at": str(e.created_at),
        }
        for e in rows
    ]


async def query_rule_config(
    db: AsyncSession, rule_id: str | None = None, scene: str | None = None,
) -> list[dict]:
    """
    查询规则配置.

    Args:
        rule_id: 指定规则编号 (可选)
        scene: 指定场景过滤 (可选)

    Returns:
        规则列表
    """
    stmt = select(RuleConfig)
    if rule_id:
        stmt = stmt.where(RuleConfig.rule_id == rule_id)
    if scene:
        stmt = stmt.where(RuleConfig.scene == scene)
    stmt = stmt.order_by(RuleConfig.priority.asc())

    rows = (await db.execute(stmt)).scalars().all()
    level_names = {1: "低", 2: "中", 3: "高", 4: "极高"}

    return [
        {
            "rule_id": r.rule_id,
            "rule_name": r.rule_name,
            "scene": r.scene,
            "conditions": r.conditions if isinstance(r.conditions, dict) else json.loads(r.conditions) if r.conditions else {},
            "risk_level": level_names.get(r.risk_level, "未知"),
            "decision": r.decision,
            "action": r.action,
            "priority": r.priority,
            "status": "启用" if r.status == 1 else "停用",
        }
        for r in rows
    ]


async def query_blacklist(db: AsyncSession, bl_type: int | None = None) -> list[dict]:
    """
    查询有效黑名单.

    Args:
        bl_type: 名单类型过滤 (可选)

    Returns:
        黑名单列表
    """
    stmt = select(BlacklistExtra).where(
        BlacklistExtra.status == 1,
    )
    if bl_type:
        stmt = stmt.where(BlacklistExtra.type == bl_type)
    stmt = stmt.order_by(desc(BlacklistExtra.created_at)).limit(50)

    rows = (await db.execute(stmt)).scalars().all()
    type_names = {1: "设备", 2: "IP", 3: "银行卡号", 4: "身份证", 5: "手机号"}

    return [
        {
            "entry_id": b.entry_id,
            "type": type_names.get(b.type, "未知"),
            "value": b.value[:32] + "..." if len(b.value) > 32 else b.value,
            "reason": b.reason,
            "source": b.source,
            "risk_level": {1: "低", 2: "中", 3: "高", 4: "极高"}.get(b.risk_level, "未知"),
            "expire_at": str(b.expire_at) if b.expire_at else "永久",
        }
        for b in rows
    ]


async def analyze_user_risk(db: AsyncSession, user_id: int) -> dict:
    """
    综合分析用户风险画像 — 聚合所有维度.

    Args:
        user_id: 用户 ID

    Returns:
        综合风险分析报告
    """
    user_info = await query_user_info(db, user_id)
    if "error" in user_info:
        return user_info

    txn_history = await query_user_transactions(db, user_id, limit=50)
    risk_events = await query_user_risk_events(db, user_id, limit=30)

    # 统计
    total_txn = len(txn_history)
    blocked_txn = sum(1 for t in txn_history if t["status"] == "拒绝")
    total_amount = sum(t["amount"] for t in txn_history)
    avg_amount = total_amount / total_txn if total_txn > 0 else 0
    reject_rate = blocked_txn / total_txn if total_txn > 0 else 0

    # 最近 7 天
    week_ago = datetime.now() - timedelta(days=7)
    recent_events = [e for e in risk_events if e["created_at"] >= str(week_ago)]
    recent_rejects = sum(1 for e in recent_events if e["decision"] == "REJECT")

    risk_level = "低"
    if reject_rate > 0.3 or recent_rejects >= 3:
        risk_level = "极高"
    elif reject_rate > 0.1 or recent_rejects >= 1:
        risk_level = "高"
    elif blocked_txn > 0:
        risk_level = "中"

    return {
        **user_info,
        "risk_analysis": {
            "total_transactions": total_txn,
            "blocked_transactions": blocked_txn,
            "reject_rate": round(reject_rate, 4),
            "avg_transaction_amount": round(avg_amount, 2),
            "total_amount": round(total_amount, 2),
            "recent_7d_risk_events": len(recent_events),
            "recent_7d_rejects": recent_rejects,
            "overall_risk_level": risk_level,
            "risk_events_summary": [{
                "event_type": e["event_type"],
                "decision": e["decision"],
                "rule_ids": e["rule_ids"],
                "created_at": e["created_at"],
            } for e in risk_events[:10]],
        },
    }
