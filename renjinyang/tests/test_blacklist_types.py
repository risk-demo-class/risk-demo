"""旅游事件入口的黑名单语义回归测试。"""
from datetime import datetime
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_module


def _make_request(**overrides) -> RiskCheckRequest:
    base = dict(
        event_type="机票预订",
        source_id="TRV000001",
        user_id="RISK001",
        order_id="TRV000001",
        receive_id="日本",
    )
    base.update(overrides)
    return RiskCheckRequest(**base)


def _mock_db(phone="13800000000"):
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = phone
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


class TestCheckAllBlacklists:
    @pytest.mark.asyncio
    async def test_user_blacklist_hit(self):
        request = _make_request()
        check = AsyncMock(return_value=True)
        with patch.object(event_module, "check_blacklist", check), \
             patch.object(event_module, "_extra_blacklisted", AsyncMock(return_value=False)):
            result = await event_module._check_all_blacklists(_mock_db(), request)
        assert result == "用户"
        check.assert_awaited_once_with(ANY, "用户", "RISK001")

    @pytest.mark.asyncio
    async def test_addr_blacklist_hit(self):
        """目的地不再当旧地址黑名单检查，证件风险统一由 R030 审计。"""
        request = _make_request()
        check = AsyncMock(return_value=False)
        extra = AsyncMock(return_value=False)
        with patch.object(event_module, "check_blacklist", check), \
             patch.object(event_module, "_extra_blacklisted", extra):
            result = await event_module._check_all_blacklists(_mock_db(), request)
        assert result is None
        assert all(call.args[1] != "地址" for call in check.await_args_list)

    @pytest.mark.asyncio
    async def test_phone_blacklist_hit(self):
        async def core_check(_db, kind, _value):
            return kind == "手机号"
        with patch.object(event_module, "check_blacklist", side_effect=core_check), \
             patch.object(event_module, "_extra_blacklisted", AsyncMock(return_value=False)):
            result = await event_module._check_all_blacklists(_mock_db("13900009999"), _make_request())
        assert result == "手机号"

    @pytest.mark.asyncio
    async def test_no_blacklist_hit(self):
        with patch.object(event_module, "check_blacklist", AsyncMock(return_value=False)), \
             patch.object(event_module, "_extra_blacklisted", AsyncMock(return_value=False)):
            result = await event_module._check_all_blacklists(_mock_db(), _make_request())
        assert result is None

    @pytest.mark.asyncio
    async def test_no_receive_id_skips_addr_and_phone(self):
        """手机号来自用户表，与是否已有目的地上下文无关。"""
        check = AsyncMock(return_value=False)
        with patch.object(event_module, "check_blacklist", check), \
             patch.object(event_module, "_extra_blacklisted", AsyncMock(return_value=False)):
            result = await event_module._check_all_blacklists(
                _mock_db(), _make_request(receive_id=None)
            )
        assert result is None
        assert [call.args[1] for call in check.await_args_list] == ["用户", "手机号"]

    @pytest.mark.asyncio
    async def test_receive_id_no_phone_skips_phone(self):
        check = AsyncMock(return_value=False)
        with patch.object(event_module, "check_blacklist", check), \
             patch.object(event_module, "_extra_blacklisted", AsyncMock(return_value=False)):
            result = await event_module._check_all_blacklists(_mock_db(None), _make_request())
        assert result is None
        assert [call.args[1] for call in check.await_args_list] == ["用户"]


class TestBlacklistReject:
    def test_blocked_by_field_set(self):
        response = event_module._blacklist_reject(_make_request(), "设备指纹")
        assert response.decision == "拒绝"
        assert response.risk_level == "极高"
        assert response.final_score == 100
        assert response.rule_count == 0
        assert response.blocked_by == "设备指纹"
        assert response.assessment_id == "blacklist_reject"
        assert response.user_id == "RISK001"

    def test_blocked_by_3_types(self):
        for kind in ("用户", "手机号", "签证号", "设备指纹"):
            assert event_module._blacklist_reject(_make_request(), kind).blocked_by == kind


class TestProcessEventBlacklistIntegration:
    @pytest.mark.asyncio
    async def test_blacklist_returns_early_no_decision_engine(self):
        run = AsyncMock()
        with patch.object(event_module, "validate_risk_check_request", AsyncMock()), \
             patch.object(event_module, "_enrich_request", AsyncMock(side_effect=lambda _db, req: req)), \
             patch.object(event_module, "_check_all_blacklists", AsyncMock(return_value="用户")), \
             patch.object(event_module, "run_risk_check", run):
            response = await event_module.process_event(_mock_db(), _make_request())
        assert response.decision == "拒绝"
        assert response.blocked_by == "用户"
        run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_blacklist_goes_through_decision(self):
        expected = RiskCheckResponse(
            assessment_id="ast_test",
            event_id="evt_test",
            user_id="RISK001",
            final_score=10,
            risk_level="低",
            decision="通过",
            rule_count=0,
            triggered_rules=[],
            features={},
            create_time=datetime.now(),
        )
        run = AsyncMock(return_value=expected)
        with patch.object(event_module, "validate_risk_check_request", AsyncMock()), \
             patch.object(event_module, "_enrich_request", AsyncMock(side_effect=lambda _db, req: req)), \
             patch.object(event_module, "_check_all_blacklists", AsyncMock(return_value=None)), \
             patch.object(event_module, "run_risk_check", run):
            response = await event_module.process_event(_mock_db(), _make_request())
        assert response.decision == "通过"
        core_request = run.await_args.args[1]
        assert core_request.event_type == "下单"
        assert core_request.event_data["tourism_event_type"] == "机票预订"
