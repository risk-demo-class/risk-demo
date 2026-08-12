"""
测试 - 旅游黑名单多类型拦截 (用户/手机号/设备指纹/IP/护照号/身份证号)
【P1-S9 同款设计】黑名单拦截是独立 1 步, 撞黑就拒, 不再跑 7 步决策.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_module


def _make_request(**overrides) -> RiskCheckRequest:
    """默认: 预订 / ORD00001 / U0001."""
    base = dict(
        event_type="预订",
        source_id="ORD00001",
        user_id="U0001",
        order_id="ORD00001",
        event_data={},
    )
    base.update(overrides)
    return RiskCheckRequest(**base)


def _mock_db(phone="13800001111", passenger_ids=("PBLK00000000001", "ID00000002")):
    """mock AsyncSession: user_info.phone 查询 + passenger 查询."""
    db = MagicMock()

    async def fake_execute(stmt):
        s = str(stmt)
        if "user_info" in s:
            return MagicMock(first=MagicMock(return_value=SimpleNamespace(phone=phone)))
        if "passenger_info" in s:
            return MagicMock(
                scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=list(passenger_ids)))),
            )
        return MagicMock(first=MagicMock(return_value=None))

    db.execute = AsyncMock(side_effect=fake_execute)
    return db


class TestCheckAllBlacklists:
    """测试 _check_all_blacklists: 类型按顺序查, 短路返回."""

    @pytest.mark.asyncio
    async def test_user_blacklist_hit(self):
        """用户撞黑 → 返回 '用户' (短路, 不再查其他)"""
        request = _make_request()
        calls = []

        async def fake_check(_db, btype, _value):
            calls.append(btype)
            return btype == "用户"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(_mock_db(), request)
        assert result == "用户"
        assert calls == ["用户"], f"短路应只查 1 次, 实际 {calls}"

    @pytest.mark.asyncio
    async def test_phone_blacklist_hit(self):
        """用户不撞, 手机号撞 → 返回 '手机号'"""
        request = _make_request()
        calls = []

        async def fake_check(_db, btype, _value):
            calls.append(btype)
            return btype == "手机号"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(_mock_db(), request)
        assert result == "手机号"
        assert "手机号" in calls

    @pytest.mark.asyncio
    async def test_device_blacklist_hit(self):
        """设备指纹撞黑 → 返回 '设备指纹'"""
        request = _make_request(event_data={"device_id": "DEV_RISK_BOT"})
        calls = []

        async def fake_check(_db, btype, _value):
            calls.append((btype, _value))
            return btype == "设备指纹"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(_mock_db(), request)
        assert result == "设备指纹"
        assert ("设备指纹", "DEV_RISK_BOT") in calls

    @pytest.mark.asyncio
    async def test_ip_blacklist_hit(self):
        """IP 撞黑 → 返回 'IP'"""
        request = _make_request(event_data={"ip": "45.155.204.101"})
        calls = []

        async def fake_check(_db, btype, _value):
            calls.append((btype, _value))
            return btype == "IP"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(_mock_db(), request)
        assert result == "IP"
        assert ("IP", "45.155.204.101") in calls

    @pytest.mark.asyncio
    async def test_passport_blacklist_hit(self):
        """乘客证件撞黑 → 返回 '护照号'"""
        request = _make_request()
        calls = []

        async def fake_check(_db, btype, _value):
            calls.append((btype, _value))
            return btype == "护照号" and _value == "PBLK00000000001"

        with patch.object(event_module, "check_blacklist", side_effect=fake_check):
            result = await event_module._check_all_blacklists(_mock_db(), request)
        assert result == "护照号"
        assert ("护照号", "PBLK00000000001") in calls

    @pytest.mark.asyncio
    async def test_no_hit(self):
        """全没撞 → None"""
        request = _make_request()
        with patch.object(event_module, "check_blacklist", return_value=False):
            result = await event_module._check_all_blacklists(_mock_db(), request)
        assert result is None


class TestBlacklistReject:
    """撞黑拒绝响应: 不写库, 直接返 100 分拒绝."""

    def test_blacklist_reject_response(self):
        req = _make_request()
        resp = event_module._blacklist_reject(req, blocked_by="护照号")
        assert isinstance(resp, RiskCheckResponse)
        assert resp.final_score == 100
        assert resp.decision == "拒绝"
        assert resp.blocked_by == "护照号"
        assert resp.rule_count == 0
