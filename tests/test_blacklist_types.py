"""
测试 - 制造业黑名单 4 种类型 (用户/经销商/设备SN/维修工) 拦截
用户走核心表 risk_blacklist, 经销商/设备SN/维修工走行业扩展表 blacklist_extra.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import RiskCheckRequest
from app.service import event as event_module


def _make_request(**overrides) -> RiskCheckRequest:
    """默认: 经销商订货 / ORD001 / D001."""
    base = dict(
        event_type="经销商订货",
        source_id="ORD001",
        user_id="D001",
        order_id="ORD001",
    )
    base.update(overrides)
    return RiskCheckRequest(**base)


def _mock_db(*execute_results):
    """mock AsyncSession; execute 按调用顺序返回结果 (None = 返回空)."""
    db = MagicMock()
    results = list(execute_results)

    async def fake_execute(*_args, **_kwargs):
        if results:
            r = results.pop(0)
            return r
        return MagicMock(
            scalar_one_or_none=AsyncMock(return_value=None),
            first=AsyncMock(return_value=None),
        )

    db.execute = AsyncMock(side_effect=fake_execute)
    db.commit = AsyncMock()
    return db


def _scalar_row(value):
    return MagicMock(scalar_one_or_none=MagicMock(return_value=value))


def _first_row(product_sn=None, technician_id=None):
    return MagicMock(first=MagicMock(return_value=SimpleNamespace(
        product_sn=product_sn, technician_id=technician_id,
    )))


class TestCheckAllBlacklists:
    """测试 _check_all_blacklists: 4 种类型按顺序查, 短路返回."""

    @pytest.mark.asyncio
    async def test_user_blacklist_hit(self):
        """用户撞黑 → 返回 '用户' (短路, 不再查经销商)"""
        request = _make_request()
        call_count = {"n": 0}

        async def fake_check(_db, btype, _value):
            call_count["n"] += 1
            return btype == "用户"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db=_mock_db(), request=request)
        assert result == "用户"
        assert call_count["n"] == 1

    @pytest.mark.asyncio
    async def test_order_dealer_blacklist_hit(self):
        """订货事件: 用户不撞, 经销商撞 → 返回 '经销商'"""
        request = _make_request()

        async def fake_extra(_db, btype, _value):
            return btype == "经销商"

        db = _mock_db(_scalar_row("D008"))  # 订单的 dealer_id
        with (
            patch.object(event_module, "check_blacklist", AsyncMock(return_value=False)),
            patch.object(event_module, "check_blacklist_extra", side_effect=fake_extra),
        ):
            result = await event_module._check_all_blacklists(db, request)
        assert result == "经销商"

    @pytest.mark.asyncio
    async def test_warranty_sn_blacklist_hit(self):
        """保修事件: 设备SN撞 → 返回 '设备SN' (不查维修工)"""
        request = _make_request(event_type="售后维修", source_id="W001")
        db = _mock_db(_first_row(product_sn="SN-BLK-0002", technician_id="TEC001"))

        async def fake_extra(_db, btype, _value):
            return btype == "设备SN"

        with (
            patch.object(event_module, "check_blacklist", AsyncMock(return_value=False)),
            patch.object(event_module, "check_blacklist_extra", side_effect=fake_extra),
        ):
            result = await event_module._check_all_blacklists(db, request)
        assert result == "设备SN"

    @pytest.mark.asyncio
    async def test_warranty_technician_blacklist_hit(self):
        """保修事件: SN不撞, 维修工撞 → 返回 '维修工'"""
        request = _make_request(event_type="保修申请", source_id="W001")
        db = _mock_db(_first_row(product_sn="SN-OK-0001", technician_id="TEC099"))

        async def fake_extra(_db, btype, _value):
            return btype == "维修工"

        with (
            patch.object(event_module, "check_blacklist", AsyncMock(return_value=False)),
            patch.object(event_module, "check_blacklist_extra", side_effect=fake_extra),
        ):
            result = await event_module._check_all_blacklists(db, request)
        assert result == "维修工"

    @pytest.mark.asyncio
    async def test_report_dealer_blacklist_hit(self):
        """串货举报: 被举报经销商撞 → 返回 '经销商'"""
        request = _make_request(event_type="串货举报", source_id="1", order_id=None)
        db = _mock_db(_scalar_row("D004"))

        async def fake_extra(_db, btype, _value):
            return btype == "经销商"

        with (
            patch.object(event_module, "check_blacklist", AsyncMock(return_value=False)),
            patch.object(event_module, "check_blacklist_extra", side_effect=fake_extra),
        ):
            result = await event_module._check_all_blacklists(db, request)
        assert result == "经销商"

    @pytest.mark.asyncio
    async def test_no_blacklist_hit(self):
        """都不撞 → 返回 None"""
        request = _make_request()
        db = _mock_db(_scalar_row("D001"))
        with (
            patch.object(event_module, "check_blacklist", AsyncMock(return_value=False)),
            patch.object(event_module, "check_blacklist_extra", AsyncMock(return_value=False)),
        ):
            result = await event_module._check_all_blacklists(db, request)
        assert result is None


class TestBlacklistReject:
    """测试 _blacklist_reject 响应构造."""

    def test_blocked_by_field_set(self):
        request = _make_request()
        resp = event_module._blacklist_reject(request, "经销商")
        assert resp.decision == "拒绝"
        assert resp.risk_level == "极高"
        assert resp.final_score == 100
        assert resp.rule_count == 0
        assert resp.blocked_by == "经销商"
        assert resp.assessment_id == "blacklist_reject"
        assert resp.event_id == "blacklist_reject"
        assert resp.user_id == "D001"

    def test_blocked_by_4_types(self):
        for btype in ("用户", "经销商", "设备SN", "维修工"):
            resp = event_module._blacklist_reject(_make_request(), btype)
            assert resp.blocked_by == btype


class TestProcessEventBlacklistIntegration:
    """测试 process_event 端到端: 撞黑后返回 _blacklist_reject, 不走 7 步."""

    @pytest.mark.asyncio
    async def test_blacklist_returns_early_no_decision_engine(self):
        request = _make_request()
        db = _mock_db()
        run_called = {"n": 0}

        async def fake_run(_db, _req):
            run_called["n"] += 1
            return "should_not_happen"

        with (
            patch.object(event_module, "validate_risk_check_request", AsyncMock()),
            patch.object(event_module, "run_risk_check", side_effect=fake_run),
            patch.object(event_module, "check_blacklist", AsyncMock(return_value=True)),
        ):
            result = await event_module.process_event(db, request)
        assert result.decision == "拒绝"
        assert result.blocked_by == "用户"
        assert run_called["n"] == 0

    @pytest.mark.asyncio
    async def test_no_blacklist_goes_through_decision(self):
        request = _make_request()
        db = _mock_db()

        async def fake_run(_db, _req):
            return "ran"

        with (
            patch.object(event_module, "validate_risk_check_request", AsyncMock()),
            patch.object(event_module, "run_risk_check", side_effect=fake_run),
            patch.object(event_module, "check_blacklist", AsyncMock(return_value=False)),
            patch.object(event_module, "check_blacklist_extra", AsyncMock(return_value=False)),
        ):
            result = await event_module.process_event(db, request)
        assert result == "ran"
