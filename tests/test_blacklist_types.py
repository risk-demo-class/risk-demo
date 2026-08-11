"""
测试 - 黑名单 5 种类型 (用户/医保卡/身份证/医院编码/执业证) 拦截 (医疗版)
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_module


def _make_request(**overrides) -> RiskCheckRequest:
    """构造医疗版 RiskCheckRequest, 默认医保结算事件."""
    base = dict(
        event_type="医保结算",
        source_id="CLM001",
        user_id="1001",
        order_id="CLM001",
        receive_id="H001",
    )
    base.update(overrides)
    return RiskCheckRequest(**base)


def _row(*values):
    """构造 SQLAlchemy Row-like (tuple, 支持下标访问 u[0])."""
    return values


def _mock_db(ui_row=None, doc_row=None):
    """mock AsyncSession: execute 按序返回 UserInfo 行 / Doctor 行."""
    db = MagicMock()
    results = []
    if ui_row is not None:
        results.append(MagicMock(first=MagicMock(return_value=ui_row)))
    if doc_row is not None:
        results.append(MagicMock(first=MagicMock(return_value=doc_row)))
    if not results:
        results.append(MagicMock(first=MagicMock(return_value=None)))
    db.execute = AsyncMock(side_effect=results)
    db.commit = AsyncMock()
    return db


class TestCheckAllBlacklists:
    """医疗版 _check_all_blacklists: 5 种类型按顺序查, 短路返回."""

    @pytest.mark.asyncio
    async def test_user_blacklist_hit(self):
        """用户撞黑 → 返回 '用户' (短路, 不查医保卡等)"""
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
    async def test_medical_card_blacklist_hit(self):
        """用户不撞, 医保卡撞 → 返回 '医保卡'"""
        request = _make_request()
        call_count = {"n": 0}

        async def fake_check(_db, btype, _value):
            call_count["n"] += 1
            return btype == "医保卡"

        db = _mock_db(ui_row=_row("MC001", "HASH001"))
        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db, request)
        assert result == "医保卡"
        assert call_count["n"] == 2, f"用户+医保卡应共查 2 次, 实际 {call_count['n']}"

    @pytest.mark.asyncio
    async def test_id_card_blacklist_hit(self):
        """用户/医保卡不撞, 身份证撞 → 返回 '身份证'"""
        request = _make_request()

        async def fake_check(_db, btype, _value):
            return btype == "身份证"

        db = _mock_db(ui_row=_row("MC001", "HASH001"))
        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db, request)
        assert result == "身份证"

    @pytest.mark.asyncio
    async def test_hospital_blacklist_hit(self):
        """医保卡/身份证不撞, 医院编码撞 (receive_id) → 返回 '医院编码'"""
        request = _make_request()

        async def fake_check(_db, btype, _value):
            return btype == "医院编码"

        db = _mock_db(ui_row=_row("MC001", "HASH001"))
        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db, request)
        assert result == "医院编码"

    @pytest.mark.asyncio
    async def test_license_blacklist_hit(self):
        """执业证撞 (event_data.doctor_id → Doctor.license_no) → 返回 '执业证'"""
        request = _make_request(event_data={"doctor_id": "D001"})

        async def fake_check(_db, btype, _value):
            return btype == "执业证"

        db = _mock_db(ui_row=_row("MC001", "HASH001"), doc_row=_row("LIC110001"))
        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db, request)
        assert result == "执业证"

    @pytest.mark.asyncio
    async def test_no_blacklist_hit(self):
        """都不撞 → 返回 None"""
        request = _make_request()

        async def fake_check(_db, btype, _value):
            return False

        db = _mock_db(ui_row=_row("MC001", "HASH001"))
        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db, request)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_receive_id_skips_hospital(self):
        """receive_id=None → 跳过医院编码检查"""
        request = _make_request(receive_id=None)
        call_log = []

        async def fake_check(_db, btype, _value):
            call_log.append(btype)
            return False

        db = _mock_db(ui_row=_row("MC001", "HASH001"))
        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db, request)
        assert result is None
        assert "医院编码" not in call_log, "receive_id=None 时不该查医院编码"

    @pytest.mark.asyncio
    async def test_no_doctor_skips_license(self):
        """event_data 无 doctor_id → 跳过执业证检查"""
        request = _make_request()  # 无 doctor_id
        call_log = []

        async def fake_check(_db, btype, _value):
            call_log.append(btype)
            return False

        db = _mock_db(ui_row=_row("MC001", "HASH001"))
        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db, request)
        assert result is None
        assert "执业证" not in call_log


class TestBlacklistReject:
    """_blacklist_reject 响应形状 (医疗版)."""

    def test_blocked_by_field_set(self):
        resp = event_module._blacklist_reject(_make_request(), "医保卡")
        assert isinstance(resp, RiskCheckResponse)
        assert resp.blocked_by == "医保卡"
        assert resp.decision == "拒绝"
        assert resp.ml_score is None
        assert resp.rule_count == 0

    def test_blocked_by_types(self):
        for t in ["用户", "医保卡", "身份证", "医院编码", "执业证"]:
            resp = event_module._blacklist_reject(_make_request(), t)
            assert resp.blocked_by == t
            assert resp.message == f"撞黑名单: {t}"


class TestProcessEventBlacklistIntegration:
    """process_event: 撞黑提前返回, 不走决策引擎."""

    @pytest.mark.asyncio
    async def test_blacklist_returns_early_no_decision_engine(self, monkeypatch):
        call_log = []
        async def fake_validate(db, req):
            call_log.append("validate")
        async def fake_enrich(db, req):
            return req
        async def fake_check(db, req):
            return "医保卡"
        async def fake_run(db, req):
            call_log.append("run")
            raise AssertionError("撞黑不该进决策引擎")
        monkeypatch.setattr(event_module, "validate_risk_check_request", fake_validate)
        monkeypatch.setattr(event_module, "_enrich_request", fake_enrich)
        monkeypatch.setattr(event_module, "_check_all_blacklists", fake_check)
        monkeypatch.setattr(event_module, "run_risk_check", fake_run)
        resp = await event_module.process_event(_mock_db(), _make_request())
        assert resp.decision == "拒绝"
        assert resp.blocked_by == "医保卡"
        assert "run" not in call_log, "撞黑时不该调用 run_risk_check"

    @pytest.mark.asyncio
    async def test_no_blacklist_goes_through_decision(self, monkeypatch):
        call_log = []
        async def fake_validate(db, req):
            call_log.append("validate")
        async def fake_enrich(db, req):
            return req
        async def fake_check(db, req):
            return None
        async def fake_run(db, req):
            call_log.append("run")
            return SimpleNamespace(decision="通过", ml_score=0.1)
        monkeypatch.setattr(event_module, "validate_risk_check_request", fake_validate)
        monkeypatch.setattr(event_module, "_enrich_request", fake_enrich)
        monkeypatch.setattr(event_module, "_check_all_blacklists", fake_check)
        monkeypatch.setattr(event_module, "run_risk_check", fake_run)
        resp = await event_module.process_event(_mock_db(), _make_request())
        assert "run" in call_log
        assert resp.decision == "通过"