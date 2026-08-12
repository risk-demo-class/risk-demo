"""
事件处理管道 (process_event 统一入口)

4 步业务流:
  Step 0:   校验 + 补全 (调 validator.validate_event)
  Step 0.5: 黑名单短路 (调 case.check_blacklists, 撞黑就拒, 不再跑 7 步)
  Step 1-7: 调用风控决策引擎 run_risk_check (7 步流水线)

黑名单检查顺序: 用户 > 银行卡号 > 设备指纹 > IP > 身份证号
撞黑时不写库 (不算一次风控评估, 只算"系统保护动作", 避免审计噪音).
"""
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bank_risk.app.engine.decision import run_risk_check
from bank_risk.app.schemas import RiskCheckRequest, RiskCheckResponse
from bank_risk.app.service.case import check_blacklists
from bank_risk.app.service.validator import validate_event

logger = logging.getLogger(__name__)


async def process_event(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    """4 步编排: 校验 → 黑名单短路 → 7 步引擎决策 → 落库"""

    # Step 0: 校验 + 补全 (用户/交易/贷款存在性, 归属一致性, 状态校验)
    await validate_event(db, request)

    # Step 0.5: 黑名单短路 (用户 > 银行卡号 > 收款卡号 > 设备指纹 > IP > 身份证号)
    # 转账场景: 查 transaction.to_card 一并检查
    to_card = None
    if request.event_type in ("转账", "信用卡") and request.source_id:
        from bank_risk.app.models import Transaction
        from sqlalchemy import select as _sel
        to_card = (await db.execute(
            _sel(Transaction.to_card).where(Transaction.txn_id == request.source_id)
        )).scalar()
    blocked = await check_blacklists(
        db,
        user_id=request.user_id,
        card_id=request.card_id,
        device_id=request.device_id,
        ip=request.ip,
        to_card=to_card,
    )
    if blocked is not None:
        logger.warning(
            "撞黑名单短路: type=%s, user_id=%s, 不走 7 步决策",
            blocked, request.user_id,
        )
        return _blacklist_reject(request, blocked)

    # Step 1-7: 决策引擎 7 步: validate → event → feature → snapshot → rule → decision → persist+respond
    # 合并 device_id / ip 到 event_data, 供 compute_all_features 读取
    merged_event_data = dict(request.event_data or {})
    if request.device_id:
        merged_event_data.setdefault("device_id", request.device_id)
    if request.ip:
        merged_event_data.setdefault("ip", request.ip)
    result = await run_risk_check(
        db,
        event_type=request.event_type,
        source_id=request.source_id,
        user_id=request.user_id,
        event_data=merged_event_data,
    )
    # dict → RiskCheckResponse (blocked_by 默认 None)
    return RiskCheckResponse(**result)


def _blacklist_reject(request: RiskCheckRequest, blocked_by: str) -> RiskCheckResponse:
    """撞黑名单的拒绝响应 (故意不写库).

    黑名单拦截不算一次风控评估, 只算"系统保护动作",
    不写 risk_event/risk_assessment, 避免审计噪音.
    assessment_id / event_id 用特殊值标识撞黑.
    """
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
        create_time=datetime.now(),
        blocked_by=blocked_by,
    )
