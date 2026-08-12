"""阶段 7：教育行业黑名单类型和短路逻辑。"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas import BlacklistCreate, RiskCheckRequest
from app.service import event as event_module


EDUCATION_BLACKLIST_TYPES = ("用户", "学号", "身份证哈希", "设备指纹", "直播账号")


def test_schema_accepts_education_blacklist_types_only():
    for blacklist_type in EDUCATION_BLACKLIST_TYPES:
        item = BlacklistCreate(blacklist_type=blacklist_type, blacklist_value="VALUE001")
        assert item.blacklist_type == blacklist_type
    with pytest.raises(ValidationError):
        BlacklistCreate(blacklist_type="地址", blacklist_value="旧电商字段")


@pytest.mark.asyncio
async def test_blacklist_checks_fixed_priority_and_short_circuits(monkeypatch):
    calls = []

    async def fake_check(db, blacklist_type, value):
        calls.append((blacklist_type, value))
        return blacklist_type == "设备指纹"

    class FakeResult:
        def first(self):
            return SimpleNamespace(
                student_id="STU001", id_card_hash="HASH001", device_id="DEV001"
            )

    class FakeDB:
        async def execute(self, statement):
            return FakeResult()

    request = RiskCheckRequest(
        event_type="学习行为",
        source_id="PROG001",
        user_id="U001",
        device_id="DEV001",
        event_data={"live_session_id": "LIVE001"},
    )
    monkeypatch.setattr(event_module, "check_blacklist", fake_check)
    result = await event_module._check_all_blacklists(FakeDB(), request)

    assert result == "设备指纹"
    assert calls == [
        ("用户", "U001"),
        ("学号", "STU001"),
        ("身份证哈希", "HASH001"),
        ("设备指纹", "DEV001"),
    ]


def test_blacklist_reject_response_is_immediate_rejection():
    request = RiskCheckRequest(
        event_type="课程报名", source_id="ORD001", user_id="U001"
    )
    response = event_module._blacklist_reject(request, "学号")
    assert response.assessment_id == "blacklist_reject"
    assert response.decision == "拒绝"
    assert response.final_score == 100
    assert response.blocked_by == "学号"
    assert isinstance(response.create_time, datetime)
