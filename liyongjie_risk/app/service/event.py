"""
银行风控系统 - 事件处理管道
==========================
process_event 统一入口, 5 步业务流:

  1. 请求合法性校验 (用户/卡/事件类型)
  2. 黑名单前置拦截 (用户身份证/卡号/设备/IP)
  3. 对手方黑名单检查 (收款卡号)
  4. 调用风控决策引擎 run_risk_check (7 步流水线)
  5. 返回决策结果

【黑名单优先级短路】
  用户身份证 > 收款卡 > 出款卡 > 设备 > IP
  任一命中 → 直接拒绝, 不进入决策引擎 (避免审计噪音)
"""
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import run_risk_check
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.blacklist import check_all_blacklists
from app.service.validator import validate_risk_check_request

logger = logging.getLogger(__name__)


async def process_event(
    db: AsyncSession,
    request: RiskCheckRequest,
) -> RiskCheckResponse:
    """
    风控事件处理 — 统一入口.

    5 步业务流:
      1. 校验 → ValueError
      2. 全维度黑名单 → 命中直接拒
      3. 决策引擎 7 步
      4. 返回响应
    """
    # 1. 校验
    await validate_risk_check_request(db, request)

    # 2. 黑名单前置拦截
    blocked = await check_all_blacklists(
        db,
        user_id=request.user_id,
        card_id=request.card_id,
        device_id=request.device_id,
        ip=request.ip,
        to_card_no_hash=request.to_card_no_hash,
    )
    if blocked:
        logger.warning("黑名单拦截: %s", blocked)
        return _blacklist_reject(request, blocked)

    # 3. 风控决策引擎
    return await run_risk_check(db, request)


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    """黑名单拦截 → 直接拒绝响应 (不写库, 避免审计噪音)"""
    return RiskCheckResponse(
        assessment_id="blacklist_reject",
        event_id="blacklist_reject",
        user_id=request.user_id,
        final_score=100,
        risk_level="极高",
        decision="REJECT",
        rule_count=0,
        triggered_rules=[],
        features={},
        create_time=datetime.now(),
        blocked_by=blocked_by,
        action="STOP_PAYMENT",
    )


# ============================================================
# Demo: 黑名单拦截流程
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("银行风控系统 — 事件处理管道 (process_event)")
    print("=" * 60)
    print("\n5 步业务流:")
    print("  1. validate_risk_check_request  — 用户/卡/事件类型校验")
    print("  2. check_all_blacklists         — 用户身份证 > 卡 > 设备 > IP")
    print("  3. run_risk_check (decision.py) — 7 步流水线")
    print("  4. _blacklist_reject            — 撞黑直接拒 (不写库)")
    print("  5. 返回 RiskCheckResponse")
    print("\n" + "=" * 60)
