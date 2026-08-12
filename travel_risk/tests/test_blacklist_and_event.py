"""黑名单 + 事件流水线单测: 优先级短路 / 撞黑拒绝 / 不写库"""
import asyncio
from types import SimpleNamespace

from app.schemas import RiskCheckRequest
from app.service.event import _blacklist_reject, _check_all_blacklists


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """模拟执行器: 按调用序列返回固定结果.

    call_values: 每次 execute 返回的对象列表.
    """

    def __init__(self, call_values):
        self.call_values = list(call_values)
        self.idx = 0

    async def execute(self, stmt):
        value = self.call_values[self.idx]
        self.idx += 1
        return _FakeResult(value)


def test_blacklist_priority_user_first():
    """用户撞黑时短路, 不再查手机号/设备."""
    db = _FakeDB([
        SimpleNamespace(blacklist_id=1, expire_time=None),  # 用户撞黑
    ])
    req = RiskCheckRequest(event_type="下单", source_id="B001", user_id="U001", booking_id="B001")
    assert asyncio.run(_check_all_blacklists(db, req)) == "用户"


def test_blacklist_phone_hit():
    """用户未撞, 手机号撞黑."""
    db = _FakeDB([
        None,                                   # 用户黑名单未命中
        SimpleNamespace(contact_phone="13800000001"),  # 查联系人手机号
        SimpleNamespace(blacklist_id=2, expire_time=None),  # 手机号撞黑
    ])
    req = RiskCheckRequest(event_type="下单", source_id="B001", user_id="U001", booking_id="B001")
    assert asyncio.run(_check_all_blacklists(db, req)) == "手机号"


def test_blacklist_device_hit():
    """用户/手机号未撞, 设备撞黑."""
    db = _FakeDB([
        None,                                   # 用户未撞
        SimpleNamespace(contact_phone="13800000001"),  # 手机号存在
        None,                                   # 手机号未撞
        SimpleNamespace(blacklist_id=3, expire_time=None),  # 设备撞黑
    ])
    req = RiskCheckRequest(event_type="下单", source_id="B001", user_id="U001",
                           booking_id="B001", device_id="DEV001")
    assert asyncio.run(_check_all_blacklists(db, req)) == "设备"


def test_blacklist_no_hit():
    db = _FakeDB([None, SimpleNamespace(contact_phone="13800000001"), None, None])
    req = RiskCheckRequest(event_type="下单", source_id="B001", user_id="U001",
                           booking_id="B001", device_id="DEV001")
    assert asyncio.run(_check_all_blacklists(db, req)) is None


def test_blacklist_reject_response():
    req = RiskCheckRequest(event_type="下单", source_id="B001", user_id="U001")
    resp = _blacklist_reject(req, blocked_by="用户")
    assert resp.decision == "拒绝"
    assert resp.final_score == 100
    assert resp.blocked_by == "用户"
    assert resp.rule_count == 0
    assert resp.ml_score is None


def test_blacklist_types_schema():
    from app.schemas import BlacklistCreate
    item = BlacklistCreate(blacklist_type="设备", blacklist_value="DEV001", reason="测试")
    assert item.blacklist_type == "设备"
