"""
事件处理管道 (process_event 统一入口)

4 步业务流:
  1. 业务实体校验（银行 source 是否存在、归属是否一致）
  2. 保留内部兼容参数（order_id, receive_id 均不对银行调用方必填）
  3. 黑名单前置拦截（用户/设备指纹/IP/银行卡号/身份证号）
  4. 调用风控决策引擎 run_risk_check (7 步)

扩展名单 BlacklistExtra 不在这里直接执行；只有规范化/同步到核心
risk_blacklist 的值才由现有 check_blacklist 服务实时拦截。
"""

import logging
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.engine.decision import run_risk_check
from app.engine.feature import load_event_context
from app.models import (
    BankCard,
    DeviceFingerprint,
    LoanApplication,
    LoginLog,
    Transaction,
    UserInfo,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklist
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(
    db: AsyncSession, request: RiskCheckRequest
) -> RiskCheckResponse:
    # 1. 业务实体校验
    await validate_risk_check_request(db, request)

    # 2. 补全 order_id / receive_id (黑名单检查需要 receive_id)
    request = await _enrich_request(db, request)

    # 3. 黑名单前置检查
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning(
            "撞黑名单: type=%s, user_id=%s",
            blocked,
            request.user_id,
        )
        return _blacklist_reject(request, blocked)

    # 4. 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    return await run_risk_check(db, request)


# 优先级: 用户 > 设备指纹 > IP > 银行卡号 > 身份证号；命中即短路。
async def _check_all_blacklists(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> str | None:
    if await check_blacklist(db, "用户", request.user_id):
        return "用户"

    for blacklist_type, value in await _bank_blacklist_candidates(db, request):
        if value and await check_blacklist(db, blacklist_type, value):
            return blacklist_type
    return None


async def _bank_blacklist_candidates(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> list[tuple[str, str | None]]:
    """从已校验的银行 source 提取核心黑名单候选值。"""
    internal = (request.event_data or {}).get("_internal", {})
    candidates: list[tuple[str, str | None]] = [
        ("设备指纹", internal.get("device_fingerprint")),
        ("IP", internal.get("ip")),
    ]
    if request.event_type == "登录":
        row = (
            await db.execute(
                select(UserInfo.id_card_hash)
                .select_from(LoginLog)
                .join(UserInfo, LoginLog.user_id == UserInfo.user_id)
                .where(LoginLog.login_id == request.source_id)
            )
        ).first()
        if row:
            candidates.append(("身份证号", row.id_card_hash))

    elif request.event_type == "转账":
        payer_card = aliased(BankCard)
        payee_card = aliased(BankCard)
        device = aliased(DeviceFingerprint)
        row = (
            await db.execute(
                select(
                    payer_card.card_no_hash.label("payer_card_hash"),
                    payee_card.card_no_hash.label("payee_card_hash"),
                    UserInfo.id_card_hash,
                )
                .select_from(Transaction)
                .join(payer_card, Transaction.from_card == payer_card.card_id)
                .join(payee_card, Transaction.to_card == payee_card.card_id)
                .join(UserInfo, payer_card.user_id == UserInfo.user_id)
                .where(Transaction.txn_id == request.source_id)
            )
        ).first()
        if row:
            candidates.extend([
                ("银行卡号", row.payer_card_hash),
                ("银行卡号", row.payee_card_hash),
                ("身份证号", row.id_card_hash),
            ])

    elif request.event_type == "贷款申请":
        row = (
            await db.execute(
                select(UserInfo.id_card_hash)
                .select_from(LoanApplication)
                .join(UserInfo, LoanApplication.user_id == UserInfo.user_id)
                .where(LoanApplication.loan_id == request.source_id)
            )
        ).first()
        if row:
            candidates.append(("身份证号", row.id_card_hash))

    elif request.event_type == "绑卡":
        row = (
            await db.execute(
                select(BankCard.card_no_hash, UserInfo.id_card_hash)
                .select_from(BankCard)
                .join(UserInfo, BankCard.user_id == UserInfo.user_id)
                .where(BankCard.card_id == request.source_id)
            )
        ).first()
        if row:
            candidates.extend(
                [("银行卡号", row.card_no_hash), ("身份证号", row.id_card_hash)]
            )

    return candidates


async def _enrich_request(
    db: AsyncSession, request: RiskCheckRequest
) -> RiskCheckRequest:
    """按已校验 source 补全内部兼容字段和可信设备/IP 环境。"""
    context = await load_event_context(
        db, request.event_type, request.source_id, request.user_id
    )
    fingerprint = None
    if context.device_id:
        fingerprint = (
            await db.execute(
                select(DeviceFingerprint.fingerprint_hash).where(
                    DeviceFingerprint.device_id == context.device_id,
                    DeviceFingerprint.user_id == request.user_id,
                )
            )
        ).scalar_one_or_none()

    event_data = dict(request.event_data or {})
    event_data["_internal"] = {
        "source_type": request.event_type,
        "device_id": context.device_id,
        "device_fingerprint": fingerprint,
        "ip": context.ip,
        "geo": context.geo,
        "event_time": context.event_time.isoformat(),
    }
    return request.model_copy(
        update={
            "order_id": request.source_id,
            "receive_id": context.device_id or context.ip or request.user_id,
            "event_data": event_data,
        }
    )


# 故意不写库: 黑名单拦截不算一次风控评估, 只算"系统保护动作",
# 不写 risk_event/risk_assessment, 避免审计噪音
def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    return RiskCheckResponse(
        assessment_id="blacklist_reject",
        event_id="blacklist_reject",
        user_id=request.user_id,
        final_score=100,
        risk_level="极高",
        decision="拒绝",
        rule_count=0,
        triggered_rules=[],
        features={},
        create_time=request.create_time or datetime.now(),
        # 【P4-L5 2026-08-10】ml_score 保持 None, 前端不渲染 ML 评分块
        # message 直接告诉用户"为什么拒绝", 不需要他懂 blocked_by 字段语义
        message=f"撞黑名单: {blocked_by}",
        blocked_by=blocked_by,
    )
