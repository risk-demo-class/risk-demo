"""Service 层：复刻旧项目的四步事件处理编排。"""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.engine.decision import run_risk_check
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service.case import check_blacklists
from app.service.validator import validate_source_ownership


def process_event(session: Session, request: RiskCheckRequest) -> RiskCheckResponse:
    """四步：校验事件 → 补全上下文 → 黑名单 → 调用七步引擎。"""
    # 1. 校验来源数据和用户归属。
    validate_source_ownership(session, request)

    # 2. 当前请求已经具备引擎所需上下文；后续可在此补齐 IP、渠道等字段。
    enriched_request = request

    # 3. 黑名单命中时直接拒绝，避免无效特征和规则计算。
    blocked_by = check_blacklists(session, enriched_request)
    if blocked_by:
        return RiskCheckResponse(
            event_id=f"BLK-{uuid4().hex[:16].upper()}",
            assessment_id=f"BLK-{uuid4().hex[:16].upper()}",
            user_id=request.user_id,
            final_score=100,
            risk_level="高风险",
            decision="拒绝",
            rule_count=0,
            triggered_rules=[],
            blocked_by=blocked_by,
        )

    # 4. 交给 Engine 完成七步风险计算、审计和案件落库。
    return run_risk_check(session, enriched_request)
