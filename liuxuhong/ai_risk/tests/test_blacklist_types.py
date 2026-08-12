"""
测试 - 黑名单 5 种类型 (用户/学号/身份证/设备指纹/直播账号) 拦截
教育行业: 用户 > 学号 > 设备指纹 > 直播账号 (按顺序查, 短路).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_module


def _make_request(**overrides) -> RiskCheckRequest:
    """构造一个 RiskCheckRequest, 默认值是"课程报名/order_001/1001"."""
    base = dict(
        event_type="课程报名",
        source_id="order_001",
        user_id="1001",
        order_id="order_001",
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
    """测试 _check_all_blacklists: 教育 5 种类型按顺序查, 短路返回."""

    @pytest.mark.asyncio
    async def test_user_blacklist_hit(self):
        """用户撞黑 → 返回 '用户' (短路, 不查学号/设备指纹)"""
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
    async def test_student_id_blacklist_hit(self):
        """用户不撞, 学号撞 → 返回 '学号'"""
        request = _make_request()
        call_log = []

        async def fake_check(_db, btype, _value):
            call_log.append(btype)
            return btype == "学号"

        # mock UserInfo 查询返回 student_id
        db = _mock_db()
        db.execute = AsyncMock(return_value=MagicMock(
            first=MagicMock(return_value=_row(student_id="STU2024001")),
        ))

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db, request)
        assert result == "学号"
        assert "用户" in call_log, "应先查用户"
        assert "学号" in call_log

    @pytest.mark.asyncio
    async def test_device_fingerprint_blacklist_hit(self):
        """用户/学号不撞, 设备指纹撞 → 返回 '设备指纹'"""
        request = _make_request()
        call_log = []

        async def fake_check(_db, btype, _value):
            call_log.append(btype)
            return btype == "设备指纹"

        db = _mock_db()
        # 第一次 execute: UserInfo.student_id 查询 → 无学号
        # 第二次 execute: DeviceFingerprint.fingerprint 查询 → 命中
        db.execute = AsyncMock(side_effect=[
            MagicMock(first=MagicMock(return_value=None)),                    # student_id 无
            MagicMock(first=MagicMock(return_value=_row(fingerprint="fp_x"))), # device 有
        ])

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db, request)
        assert result == "设备指纹"
        assert "设备指纹" in call_log

    @pytest.mark.asyncio
    async def test_no_blacklist_hit(self):
        """都不撞 → 返回 None"""
        request = _make_request()
        call_log = []

        async def fake_check(_db, btype, _value):
            call_log.append(btype)
            return False

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[
            MagicMock(first=MagicMock(return_value=None)),   # student_id 无
            MagicMock(first=MagicMock(return_value=None)),   # device 无
        ])

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db, request)
        assert result is None
        # 非直播打赏事件: 只查用户+学号+设备指纹, 不查直播账号
        assert "直播账号" not in call_log

    @pytest.mark.asyncio
    async def test_live_gift_checks_stream_account(self):
        """直播打赏事件 → 额外查直播账号黑名单"""
        request = _make_request(event_type="直播打赏")
        call_log = []

        async def fake_check(_db, btype, _value):
            call_log.append(btype)
            return btype == "直播账号"

        db = _mock_db()
        db.execute = AsyncMock(side_effect=[
            MagicMock(first=MagicMock(return_value=None)),   # student_id 无
            MagicMock(first=MagicMock(return_value=None)),   # device 无
        ])

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(db, request)
        assert result == "直播账号"
        assert "直播账号" in call_log, "直播打赏事件应查直播账号黑名单"


class TestBlacklistReject:
    """测试 _blacklist_reject 响应构造."""

    def test_blocked_by_field_set(self):
        """blocked_by 字段正确填到响应里"""
        request = _make_request()
        resp = event_module._blacklist_reject(request, "用户")
        assert resp.decision == "拒绝"
        assert resp.risk_level == "极高"
        assert resp.final_score == 100
        assert resp.rule_count == 0
        assert resp.blocked_by == "用户"
        # 没真写库
        assert resp.assessment_id == "blacklist_reject"
        assert resp.event_id == "blacklist_reject"
        assert resp.user_id == "1001"

    def test_blocked_by_all_types(self):
        """5 种类型都能正确填"""
        for btype in ("用户", "学号", "身份证", "设备指纹", "直播账号"):
            resp = event_module._blacklist_reject(_make_request(), btype)
            assert resp.blocked_by == btype


class TestProcessEventBlacklistIntegration:
    """测试 process_event 端到端: 撞黑后返回 _blacklist_reject, 不走 7 步."""

    @pytest.mark.asyncio
    async def test_blacklist_returns_early_no_decision_engine(self):
        """撞黑后直接返回, 不调 run_risk_check"""
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
        assert resp.blocked_by is None
