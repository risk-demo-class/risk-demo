"""
事件处理管道 (process_event 统一入口)

4 步业务流:
  1. 业务实体校验 (号卡存在 + source_id 与事件类型匹配)
  2. 黑名单前置拦截 (号卡/客户/设备/渠道 4 种类型, 撞黑就关停, 不再跑 7 步)
  3. 调用风控决策引擎 run_risk_check (7 步)
  4. 写操作审计日志 (决策结果落审计)

参照 ai_risk/app/service/event.py, 适配电信业务:
  - 核心枢纽是 msisdn (不是 user_id)
  - 黑名单类型: 号卡/客户/设备/渠道 (不是 用户/地址/手机号)
  - 撞黑决策: 关停号码 (不是 拒绝)
"""
import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.models import TelecomCard
from app.models_risk import TelecomRiskActionLog, TelecomRiskBlacklist
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.blacklist import check_blacklist
from app.service.validator import ensure_card_exists, ensure_source_matches_event_type

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    """事件处理主入口: 校验 → 黑名单 → 决策引擎 7 步 → 审计日志."""
    # 1. 业务实体校验 (号卡存在 + source_id 与事件类型匹配)
    await _validate_request(db, request)

    # 2. 黑名单前置检查 (号卡/客户/设备/渠道, 短路返回)
    blocked = await _check_all_blacklists(db, request)
    if blocked is not None:
        logger.warning("撞黑名单: type=%s, value=%s, msisdn=%s",
                       blocked[0], blocked[1], request.msisdn)
        response = _blacklist_reject(request, blocked[0])
        await _write_action_log(db, "system", "ADD_BLACKLIST", "blacklist",
                                blocked[1], None, {"blocked_by": blocked[0], "msisdn": request.msisdn})
        return response

    # 3. 决策引擎 7 步: event → feature → rule → decision → persist
    response = await run_risk_check(db, request)

    # 4. 审计日志: 决策结果
    await _write_action_log(db, "system", "AUTO_HALT_CARD" if response.decision == "关停号码" else "REVIEW_CASE",
                            "assessment", response.assessment_id,
                            None,
                            {"decision": response.decision, "score": response.final_score,
                             "level": response.risk_level, "rule_count": response.rule_count,
                             "msisdn": response.msisdn})

    return response


async def _validate_request(db: AsyncSession, request: RiskCheckRequest) -> None:
    """两步校验: 号卡存在 + source_id 与事件类型匹配."""
    await ensure_card_exists(db, request.msisdn)
    await ensure_source_matches_event_type(db, request)


async def _check_all_blacklists(
    db: AsyncSession, request: RiskCheckRequest,
) -> Optional[tuple[str, str]]:
    """黑名单检查: 号卡 → 客户 → 设备 → 渠道 (优先级短路).

    返回 (blacklist_type, blacklist_value) 或 None.
    一次查 card 拿全 customer_id / current_imei / open_channel_id, 避免多次 SQL.
    """
    # 1. 号卡黑名单 (必查)
    if await check_blacklist(db, "号卡", request.msisdn):
        return ("号卡", request.msisdn)

    # 一次查全 card 关联字段 (customer_id / imei / channel_id)
    card = (await db.execute(
        select(
            TelecomCard.customer_id,
            TelecomCard.current_imei,
            TelecomCard.open_channel_id,
        ).where(TelecomCard.msisdn == request.msisdn)
    )).first()

    if not card:
        return None  # 号卡不存在 (validate 已拦截, 这里兜底)

    # 2. 客户黑名单
    if card.customer_id and await check_blacklist(db, "客户", card.customer_id):
        return ("客户", card.customer_id)

    # 3. 设备黑名单
    if card.current_imei and await check_blacklist(db, "设备", card.current_imei):
        return ("设备", card.current_imei)

    # 4. 渠道黑名单
    if card.open_channel_id and await check_blacklist(db, "渠道", card.open_channel_id):
        return ("渠道", card.open_channel_id)

    return None


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    """撞黑名单: 不写库, 直接返响应 (审计 noise 0).

    决策="关停号码" (电信语义), final_score=100.
    """
    return RiskCheckResponse(
        assessment_id="blacklist_reject",
        event_id="blacklist_reject",
        msisdn=request.msisdn,
        final_score=100,
        risk_level="极高",
        decision="关停号码",
        rule_count=0,
        triggered_rules=[],
        features={},
        create_time=datetime.now(),
        ml_score=None,
        message=f"撞黑名单: {blocked_by}",
        blocked_by=blocked_by,
    )


async def _write_action_log(
    db: AsyncSession,
    operator: str,
    action_type: str,
    target_type: str,
    target_id: str,
    before_value: Optional[dict],
    after_value: Optional[dict],
    remark: Optional[str] = None,
) -> None:
    """写操作审计日志. try/except 包裹: 审计失败不阻塞主流程."""
    try:
        log = TelecomRiskActionLog(
            operator=operator,
            action_type=action_type,
            target_type=target_type,
            target_id=target_id,
            before_value=json.dumps(before_value, ensure_ascii=False) if before_value else None,
            after_value=json.dumps(after_value, ensure_ascii=False) if after_value else None,
            remark=remark,
        )
        db.add(log)
        await db.flush()
    except Exception as e:
        logger.error("审计日志写入失败: %s", e)
