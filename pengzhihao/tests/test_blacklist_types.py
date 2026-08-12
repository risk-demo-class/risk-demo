"""物流核心/扩展黑名单适配测试。"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.service import event as event_module


def _internal_request():
    return event_module._InternalRiskRequest(
        event_type="下单",
        source_id="SHP0001",
        user_id="U001",
        event_data={"business_event_type": "寄件受理"},
        order_id="SHP0001",
        receive_id="ADDR001",
    )


class TestBlacklistReject:
    def test_response_uses_logistics_blocked_by(self):
        response = event_module._blacklist_reject(_internal_request(), "收件地址")
        assert response.decision == "拒绝"
        assert response.final_score == 100
        assert response.blocked_by == "收件地址"
        assert response.user_id == "U001"

    def test_all_public_core_labels_are_supported(self):
        for label in ("寄件人", "收件地址", "联系电话"):
            assert event_module._blacklist_reject(_internal_request(), label).blocked_by == label


class TestExtraBlacklist:
    @pytest.mark.asyncio
    async def test_extra_blacklist_hit(self):
        result = MagicMock()
        result.scalar_one_or_none.return_value = 1
        db = MagicMock()
        db.execute = AsyncMock(return_value=result)
        assert await event_module._extra_blacklist_hit(db, "设备指纹", "DEV-RISK") is True

    @pytest.mark.asyncio
    async def test_empty_extra_value_skips_database(self):
        db = MagicMock()
        db.execute = AsyncMock()
        assert await event_module._extra_blacklist_hit(db, "IP地址", None) is False
        db.execute.assert_not_awaited()


class TestProcessEventBlacklistIntegration:
    @pytest.mark.asyncio
    async def test_blacklist_short_circuits_seven_step_engine(self):
        from app.schemas import RiskCheckRequest

        request = RiskCheckRequest(
            event_type="寄件受理", source_id="SHP0001", user_id="U001", event_data={}
        )
        internal = _internal_request()
        engine = AsyncMock()
        with patch.object(event_module, "validate_risk_check_request", AsyncMock()), \
             patch.object(event_module, "_enrich_request", AsyncMock(return_value=internal)), \
             patch.object(event_module, "_check_all_blacklists", AsyncMock(return_value="寄件人")), \
             patch.object(event_module, "run_risk_check", engine):
            response = await event_module.process_event(MagicMock(), request)
        assert response.decision == "拒绝"
        assert response.blocked_by == "寄件人"
        engine.assert_not_awaited()
