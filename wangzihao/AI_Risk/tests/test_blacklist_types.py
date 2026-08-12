"""
测试 - 制造业兼容黑名单 3 种类型 (经销商/区域/手机号) 拦截
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_module


def _make_request(**overrides) -> RiskCheckRequest:
    """构造制造业兼容 RiskCheckRequest。"""
    base = dict(
        event_type="下单",
        source_id="PO001",
        user_id="DLR001",
        order_id="PO001",
        receive_id="华东-上海中心仓",
    )
    base.update(overrides)
    return RiskCheckRequest(**base)


def _mock_db():
    """构造一个 mock AsyncSession, 不会真连 DB."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


def _row(**kwargs):
    """构造一个 SQLAlchemy Row-like 对象 (支持属性访问)."""
    return SimpleNamespace(**kwargs)


class TestCheckAllBlacklists:
    """测试 _check_all_blacklists: 3 种类型按顺序查, 短路返回."""

    @pytest.mark.asyncio
    async def test_user_blacklist_hit(self):
        """用户撞黑 → 返回 '用户' (短路, 不查地址/手机号)"""
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
    async def test_addr_blacklist_hit(self):
        """用户不撞, 地址撞 → 返回 '地址' (不查手机号)"""
        request = _make_request()
        call_count = {"n": 0}

        async def fake_check(_db, btype, _value):
            call_count["n"] += 1
            return btype == "地址"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db=_mock_db(), request=request)
        assert result == "地址"
        # 用户查了 + 地址查了 + 手机号没查 (因为地址已经撞了短路)
        assert call_count["n"] == 2, f"用户+地址应共查 2 次, 实际 {call_count['n']}"

    @pytest.mark.asyncio
    async def test_phone_blacklist_hit(self):
        """经销商/区域不撞，event_data 联系手机号撞黑。"""
        request = _make_request(event_data={"contact_phone": "13800000000"})

        async def fake_check(_db, btype, _value):
            return btype == "手机号"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(_mock_db(), request)
        assert result == "手机号"

    @pytest.mark.asyncio
    async def test_no_blacklist_hit(self):
        """都不撞 → 返回 None"""
        request = _make_request(event_data={"contact_phone": "13800000000"})

        async def fake_check(_db, btype, _value):
            return False

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(_mock_db(), request)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_receive_id_skips_addr_and_phone(self):
        """没有区域和手机号时只查经销商。"""
        request = _make_request(receive_id=None)
        call_log = []

        async def fake_check(_db, btype, _value):
            call_log.append(btype)
            return False

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db=_mock_db(), request=request)
        assert result is None
        # 只查了用户, 没查地址/手机号
        assert call_log == ["用户"], f"应只查用户, 实际查了 {call_log}"

    @pytest.mark.asyncio
    async def test_receive_id_no_phone_skips_phone(self):
        """有区域但 event_data 没手机号时不查手机号黑名单。"""
        request = _make_request()
        call_log = []

        async def fake_check(_db, btype, _value):
            call_log.append(btype)
            return False

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(_mock_db(), request)
        assert result is None
        # 查了用户+地址, 没查手机号
        assert "手机号" not in call_log


class TestBlacklistReject:
    """测试 _blacklist_reject 响应构造."""

    def test_blocked_by_field_set(self):
        """blocked_by 字段正确填到响应里"""
        request = _make_request()
        resp = event_module._blacklist_reject(request, "地址")
        assert resp.decision == "拒绝"
        assert resp.risk_level == "极高"
        assert resp.final_score == 100
        assert resp.rule_count == 0
        assert resp.blocked_by == "地址"
        # 没真写库
        assert resp.assessment_id == "blacklist_reject"
        assert resp.event_id == "blacklist_reject"
        # user_id 透传
        assert resp.user_id == "DLR001"

    def test_blocked_by_3_types(self):
        """3 种类型都能正确填"""
        for btype in ("用户", "地址", "手机号"):
            resp = event_module._blacklist_reject(_make_request(), btype)
            assert resp.blocked_by == btype


class TestProcessEventBlacklistIntegration:
    """测试 process_event 端到端: 撞黑后返回 _blacklist_reject, 不走 7 步."""

    @pytest.mark.asyncio
    async def test_blacklist_returns_early_no_decision_engine(self):
        """撞黑后直接返回, 不调 run_risk_check"""
        request = _make_request()
        db = _mock_db()

        # run_risk_check 不该被调
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
             patch.object(event_module, "_check_all_blacklists", return_value="用户"), \
             patch.object(event_module, "run_risk_check", side_effect=fake_run):
            resp = await event_module.process_event(db, request)

        assert resp.decision == "拒绝"
        assert resp.blocked_by == "用户"
        assert run_called["n"] == 0, "撞黑后不应调决策引擎"

    @pytest.mark.asyncio
    async def test_no_blacklist_goes_through_decision(self):
        """没撞黑 → 调 run_risk_check"""
        request = _make_request()
        db = _mock_db()

        run_called = {"n": 0}
        async def fake_run(_db, _req):
            run_called["n"] += 1
            from datetime import datetime
            return RiskCheckResponse(
                assessment_id="ast_test", event_id="evt_test",
                user_id="DLR001", final_score=10, risk_level="低",
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
        assert resp.blocked_by is None
