"""
测试 - 旅游黑名单前置拦截 (用户/签证号/设备指纹)
优先级: 用户 > 签证号 > 设备指纹 (短路)
护照号不走前置, 由规则 R030 拦截留审计 (Q3 决策)
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_module


def _make_request(**overrides) -> RiskCheckRequest:
    base = dict(
        event_type="预订下单",
        source_id="order_001",
        user_id="1001",
        order_id="order_001",
        event_data=None,
    )
    base.update(overrides)
    return RiskCheckRequest(**base)


def _mock_db(passengers: list[str] | None = None):
    """mock AsyncSession: execute 返回乘客证件查询结果 (scalars().all())."""
    db = MagicMock()
    if passengers is not None:
        result = MagicMock()
        result.scalars.return_value.all.return_value = passengers
        db.execute = AsyncMock(return_value=result)
    else:
        db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


class TestCheckAllBlacklists:
    """测试 _check_all_blacklists: 4 种类型按优先级短路."""

    @pytest.mark.asyncio
    async def test_user_blacklist_hit(self):
        """用户撞黑 → 返回 '用户' (短路, 不查护照/签证/设备)"""
        request = _make_request()
        call_count = {"n": 0}

        async def fake_check(_db, btype, _value):
            call_count["n"] += 1
            return btype == "用户"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db=_mock_db(), request=request)
        assert result == "用户"
        assert call_count["n"] == 1, f"短路应只查 1 次, 实际 {call_count['n']}"

    @pytest.mark.asyncio
    async def test_visa_blacklist_hit(self):
        """签证申请事件, 签证号撞黑 → 返回 '签证号'"""
        request = _make_request(event_type="签证申请", source_id="VISA_BLACK_001",
                                order_id=None)

        async def fake_check(_db, btype, value):
            return btype == "签证号" and value == "VISA_BLACK_001"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db=_mock_db(), request=request)
        assert result == "签证号"

    @pytest.mark.asyncio
    async def test_device_fingerprint_hit(self):
        """event_data.device_id 撞黑 → 返回 '设备指纹'"""
        request = _make_request(event_data={"device_id": "DEVICE_BLACK_001"})

        async def fake_check(_db, btype, value):
            return btype == "设备指纹" and value == "DEVICE_BLACK_001"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db=_mock_db(), request=request)
        assert result == "设备指纹"

    @pytest.mark.asyncio
    async def test_no_blacklist_hit(self):
        """都不撞 → 返回 None"""
        request = _make_request(event_data={"device_id": "DEVICE_OK"})

        async def fake_check(_db, btype, _value):
            return False

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(
                db=_mock_db(passengers=["E12345678"]), request=request)
        assert result is None

class TestBlacklistReject:
    """测试 _blacklist_reject 响应构造."""

    def test_blocked_by_field_set(self):
        request = _make_request()
        resp = event_module._blacklist_reject(request, "护照号")
        assert resp.decision == "拒绝"
        assert resp.risk_level == "极高"
        assert resp.final_score == 100
        assert resp.rule_count == 0
        assert resp.blocked_by == "护照号"
        assert resp.assessment_id == "blacklist_reject"

    def test_blocked_by_types(self):
        for btype in ("用户", "签证号", "设备指纹"):
            resp = event_module._blacklist_reject(_make_request(), btype)
            assert resp.blocked_by == btype


class TestProcessEventBlacklistIntegration:
    """process_event 端到端: 撞黑后返回 _blacklist_reject, 不走 7 步."""

    @pytest.mark.asyncio
    async def test_blacklist_returns_early_no_decision_engine(self):
        request = _make_request()
        db = _mock_db()
        run_called = {"n": 0}

        async def fake_run(_db, _req):
            run_called["n"] += 1
            return None

        async def fake_validate(_db, _req):
            return None

        async def fake_enrich(_db, req):
            return req

        with patch.object(event_module, "validate_risk_check_request", side_effect=fake_validate), \
             patch.object(event_module, "_enrich_request", side_effect=fake_enrich), \
             patch.object(event_module, "_check_all_blacklists", return_value="设备指纹"), \
             patch.object(event_module, "run_risk_check", side_effect=fake_run):
            resp = await event_module.process_event(db, request)

        assert resp.decision == "拒绝"
        assert resp.blocked_by == "设备指纹"
        assert run_called["n"] == 0, "撞黑后不应调决策引擎"

    @pytest.mark.asyncio
    async def test_no_blacklist_goes_through_decision(self):
        request = _make_request()
        db = _mock_db()
        run_called = {"n": 0}

        async def fake_run(_db, _req):
            run_called["n"] += 1
            from datetime import datetime
            return RiskCheckResponse(
                assessment_id="ast_test", event_id="evt_test",
                user_id="1001", final_score=10, risk_level="低",
                decision="通过", rule_count=0, triggered_rules=[],
                features={}, create_time=datetime.now(), blocked_by=None,
            )

        async def fake_validate(_db, _req):
            return None

        async def fake_enrich(_db, req):
            return req

        with patch.object(event_module, "validate_risk_check_request", side_effect=fake_validate), \
             patch.object(event_module, "_enrich_request", side_effect=fake_enrich), \
             patch.object(event_module, "_check_all_blacklists", return_value=None), \
             patch.object(event_module, "run_risk_check", side_effect=fake_run):
            resp = await event_module.process_event(db, request)

        assert run_called["n"] == 1
        assert resp.decision == "通过"
