"""
测试 - 黑名单 4 种类型 (用户/经销商/设备SN/维修工) 拦截
制造业优先级: 用户 > 经销商 > 设备SN > 维修工, 短路返回.
"""
from types import SimpleNamespace
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_module


def _make_request(**overrides) -> RiskCheckRequest:
    """构造一个 RiskCheckRequest, 默认值是"经销商订货/D001/ORD001"."""
    base = dict(
        event_type="经销商订货",
        source_id="ORD001",
        user_id="D001",
        order_id="ORD001",
        event_data={"product_sn": "SN001", "technician_id": "T001"},
    )
    base.update(overrides)
    return RiskCheckRequest(**base)


def _mock_db(dealer_id: str | None = "D001", sn: str | None = "SN001",
             tech: str | None = "T001"):
    """构造一个 mock AsyncSession: _lookup_dealer_id 返回 dealer 行."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(
        first=MagicMock(return_value=SimpleNamespace(dealer_id=dealer_id)),
    ))
    db.commit = AsyncMock()
    return db


def _row(**kwargs):
    return SimpleNamespace(**kwargs)


class TestCheckAllBlacklists:
    """测试 _check_all_blacklists: 4 种类型按顺序查, 短路返回."""

    @pytest.mark.asyncio
    async def test_user_blacklist_hit(self):
        """用户撞黑 → 返回 '用户' (短路, 不查经销商/设备SN/维修工)"""
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
    async def test_dealer_blacklist_hit(self):
        """用户不撞, 经销商撞 → 返回 '经销商' (不查设备SN/维修工)"""
        request = _make_request()
        call_count = {"n": 0}

        async def fake_check(_db, btype, _value):
            call_count["n"] += 1
            return btype == "经销商"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db=_mock_db(), request=request)
        assert result == "经销商"
        assert call_count["n"] == 2, f"用户+经销商应共查 2 次, 实际 {call_count['n']}"

    @pytest.mark.asyncio
    async def test_sn_blacklist_hit(self):
        """用户/经销商不撞, 设备SN撞 → 返回 '设备SN'"""
        request = _make_request()

        async def fake_check(_db, btype, _value):
            return btype == "设备SN"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db=_mock_db(), request=request)
        assert result == "设备SN"

    @pytest.mark.asyncio
    async def test_technician_blacklist_hit(self):
        """用户/经销商/设备SN不撞, 维修工撞 → 返回 '维修工'"""
        request = _make_request()

        async def fake_check(_db, btype, _value):
            return btype == "维修工"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db=_mock_db(), request=request)
        assert result == "维修工"

    @pytest.mark.asyncio
    async def test_no_blacklist_hit(self):
        """都不撞 → 返回 None"""
        request = _make_request()

        async def fake_check(_db, btype, _value):
            return False

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db=_mock_db(), request=request)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_order_skips_dealer_check(self):
        """event_type=经销商订货 + source_id 顶替 order_id → 4 类全查"""
        request = _make_request(order_id=None, source_id="WR001")
        call_log = []

        async def fake_check(_db, btype, _value):
            call_log.append(btype)
            return False

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db=_mock_db(), request=request)
        assert result is None
        assert call_log == ["用户", "经销商", "设备SN", "维修工"], f"实际查了 {call_log}"


class TestBlacklistReject:
    """测试 _blacklist_reject: 撞黑响应."""

    def test_blocked_by_field_set(self):
        req = SimpleNamespace(user_id="D001")
        resp = event_module._blacklist_reject(req, blocked_by="经销商")
        assert isinstance(resp, RiskCheckResponse)
        assert resp.decision == "拒绝"
        assert resp.final_score == 100
        assert resp.rule_count == 0
        assert resp.blocked_by == "经销商"

    def test_blocked_by_4_types(self):
        """4 种类型都能正确回传 blocked_by"""
        for t in ["用户", "经销商", "设备SN", "维修工"]:
            resp = event_module._blacklist_reject(SimpleNamespace(user_id="D001"), blocked_by=t)
            assert resp.blocked_by == t


class TestProcessEventBlacklistIntegration:
    """测试 process_event: 撞黑短路, 不跑决策引擎."""

    @pytest.mark.asyncio
    async def test_blacklist_returns_early_no_decision_engine(self):
        with patch.object(event_module, "validate_risk_check_request", new=AsyncMock()), \
             patch.object(event_module, "_enrich_request", new=AsyncMock(side_effect=lambda db, r: r)), \
             patch.object(event_module, "check_blacklist", new=AsyncMock(return_value=True)), \
             patch.object(event_module, "run_risk_check", new=AsyncMock()) as mock_engine:
            resp = await event_module.process_event(_mock_db(), _make_request())
            assert resp.decision == "拒绝"
            mock_engine.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_blacklist_goes_through_decision(self):
        fake_response = RiskCheckResponse(
            assessment_id="ast_1", event_id="evt_1", user_id="D001",
            final_score=30, risk_level="低", decision="通过",
            rule_count=0, triggered_rules=[], create_time=datetime.now(),
        )
        with patch.object(event_module, "validate_risk_check_request", new=AsyncMock()), \
             patch.object(event_module, "_enrich_request", new=AsyncMock(side_effect=lambda db, r: r)), \
             patch.object(event_module, "check_blacklist", new=AsyncMock(return_value=False)), \
             patch.object(event_module, "run_risk_check", new=AsyncMock(return_value=fake_response)):
            resp = await event_module.process_event(_mock_db(), _make_request())
            assert resp.decision == "通过"
