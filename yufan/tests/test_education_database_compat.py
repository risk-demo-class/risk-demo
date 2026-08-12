"""独立教育数据库与受保护核心枚举兼容测试。"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.education_compat import (
    to_core_category,
    to_core_event,
    to_education_category,
    to_education_event,
)
from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_service


def test_education_event_mapping_is_bidirectional():
    pairs = {
        "课程报名": "下单",
        "退费申请": "售后申请",
        "直播打赏": "支付",
        "学习行为": "物流投诉",
    }
    for education, core in pairs.items():
        assert to_core_event(education) == core
        assert to_education_event(core) == education


def test_education_category_mapping_is_bidirectional():
    pairs = {
        "报名异常": "订单欺诈",
        "退费滥用": "售后滥用",
        "账号风险": "账户风险",
        "学习异常": "物流风险",
        "打赏风险": "支付风险",
        "设备风险": "地址风险",
    }
    for education, core in pairs.items():
        assert to_core_category(education) == core
        assert to_education_category(core) == education


@pytest.mark.asyncio
async def test_process_event_writes_core_enum_but_returns_education_category(monkeypatch):
    request = RiskCheckRequest(
        event_type="课程报名", source_id="ORD_N0001", user_id="U0001"
    )

    async def no_op(db, req):
        return None

    async def enrich(db, req):
        return req

    async def not_blocked(db, req):
        return None

    async def decision(db, req):
        assert req.event_type == "下单"
        assert req.event_data["education_event_type"] == "课程报名"
        return RiskCheckResponse(
            assessment_id="AST001",
            event_id="EVT001",
            user_id=req.user_id,
            final_score=80,
            risk_level="高",
            decision="人工审核",
            rule_count=1,
            triggered_rules=[{
                "rule_id": "EDU001",
                "rule_name": "高额报名",
                "rule_category": "订单欺诈",
                "risk_level": "高",
                "risk_score": 80,
                "action": "人工审核",
            }],
            features={},
            create_time=datetime.now(),
        )

    monkeypatch.setattr(event_service, "validate_risk_check_request", no_op)
    monkeypatch.setattr(event_service, "_enrich_request", enrich)
    monkeypatch.setattr(event_service, "_check_all_blacklists", not_blocked)
    monkeypatch.setattr(event_service, "run_risk_check", decision)

    response = await event_service.process_event(SimpleNamespace(), request)
    assert response.triggered_rules[0].rule_category == "报名异常"
