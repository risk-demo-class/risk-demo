"""银行五类核心黑名单的前置拦截测试。"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_module


BLACKLIST_TYPES = ("用户", "设备指纹", "IP", "银行卡号", "身份证号")


def _make_request(**overrides) -> RiskCheckRequest:
    values = {
        "event_type": "登录",
        "source_id": "DEMO_LOGIN_001",
        "user_id": "DEMO_USR_001",
    }
    values.update(overrides)
    return RiskCheckRequest(**values)


def _mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


class TestCheckAllBlacklists:
    @pytest.mark.asyncio
    async def test_user_hit_short_circuits_bank_candidates(self):
        with patch.object(event_module, "check_blacklist", AsyncMock(return_value=True)) as check, patch.object(
            event_module, "_bank_blacklist_candidates", AsyncMock()
        ) as candidates:
            result = await event_module._check_all_blacklists(_mock_db(), _make_request())
        assert result == "用户"
        check.assert_awaited_once_with(check.call_args.args[0], "用户", "DEMO_USR_001")
        candidates.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("blacklist_type", BLACKLIST_TYPES[1:])
    async def test_each_bank_dimension_can_block(self, blacklist_type):
        async def fake_check(_db, current_type, _value):
            return current_type == blacklist_type

        candidates = [(blacklist_type, f"DEMO_{blacklist_type}_HASH")]
        with patch.object(event_module, "check_blacklist", side_effect=fake_check), patch.object(
            event_module, "_bank_blacklist_candidates", AsyncMock(return_value=candidates)
        ):
            result = await event_module._check_all_blacklists(_mock_db(), _make_request())
        assert result == blacklist_type

    @pytest.mark.asyncio
    async def test_no_hit_returns_none(self):
        candidates = [
            ("设备指纹", "DEMO_DEVICE_HASH"),
            ("IP", "IP_DEMO_001"),
            ("身份证号", "DEMO_ID_HASH"),
        ]
        with patch.object(event_module, "check_blacklist", AsyncMock(return_value=False)), patch.object(
            event_module, "_bank_blacklist_candidates", AsyncMock(return_value=candidates)
        ):
            assert await event_module._check_all_blacklists(_mock_db(), _make_request()) is None


class TestBlacklistReject:
    @pytest.mark.parametrize("blacklist_type", BLACKLIST_TYPES)
    def test_response_identifies_blocking_dimension(self, blacklist_type):
        response = event_module._blacklist_reject(_make_request(), blacklist_type)
        assert response.assessment_id == "blacklist_reject"
        assert response.event_id == "blacklist_reject"
        assert response.user_id == "DEMO_USR_001"
        assert response.decision == "拒绝"
        assert response.risk_level == "极高"
        assert response.final_score == 100
        assert response.rule_count == 0
        assert response.ml_score is None
        assert response.blocked_by == blacklist_type
        assert response.message == f"撞黑名单: {blacklist_type}"


class TestProcessEventBlacklistIntegration:
    @pytest.mark.asyncio
    async def test_hit_returns_early_without_decision_engine(self):
        run_risk_check = AsyncMock()
        with patch.object(event_module, "validate_risk_check_request", AsyncMock()), patch.object(
            event_module, "_enrich_request", AsyncMock(side_effect=lambda _db, request: request)
        ), patch.object(
            event_module, "_check_all_blacklists", AsyncMock(return_value="设备指纹")
        ), patch.object(event_module, "run_risk_check", run_risk_check):
            response = await event_module.process_event(_mock_db(), _make_request())
        assert response.blocked_by == "设备指纹"
        run_risk_check.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_hit_calls_decision_engine_once(self):
        expected = RiskCheckResponse(
            assessment_id="DEMO_ASSESSMENT_001",
            event_id="DEMO_EVENT_001",
            user_id="DEMO_USR_001",
            final_score=10,
            risk_level="低",
            decision="通过",
            rule_count=0,
            triggered_rules=[],
            create_time=datetime(2026, 8, 11, 12, 0, 0),
        )
        run_risk_check = AsyncMock(return_value=expected)
        with patch.object(event_module, "validate_risk_check_request", AsyncMock()), patch.object(
            event_module, "_enrich_request", AsyncMock(side_effect=lambda _db, request: request)
        ), patch.object(
            event_module, "_check_all_blacklists", AsyncMock(return_value=None)
        ), patch.object(event_module, "run_risk_check", run_risk_check):
            response = await event_module.process_event(_mock_db(), _make_request())
        assert response is expected
        run_risk_check.assert_awaited_once()
