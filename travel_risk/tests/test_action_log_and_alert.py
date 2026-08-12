"""审计日志 + 告警服务单测 (mock DB)"""
import asyncio
from types import SimpleNamespace

from app.service.action_log import record_action


class _RecordingDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def test_record_action():
    db = _RecordingDB()
    asyncio.run(record_action(
        db, operator="admin", action_type="CREATE_RULE",
        target_type="rule", target_id="R001",
        after_value={"rule_name": "测试"},
        remark="创建规则",
    ))
    assert len(db.added) == 1
    log = db.added[0]
    assert log.operator == "admin"
    assert log.target_id == "R001"
    assert log.after_value is not None
    assert log.before_value is None


class _FakeScalar:
    def __init__(self, value):
        self._v = value

    def scalar_one_or_none(self):
        return self._v


def test_alert_dedupe_same_pending():
    """同标题 PENDING 告警不重复写."""
    from app.service.alert import _create_alert

    class _DB:
        def __init__(self):
            self.added = []
            self.returns = [1]  # 第一次查已有 PENDING

        async def execute(self, stmt):
            v = self.returns.pop(0)
            return _FakeScalar(v)

        def add(self, obj):
            self.added.append(obj)

    db = _DB()
    ok = asyncio.run(_create_alert(
        db, "BUSINESS", "P1", "待审核案件积压", "内容",
        "pending_case_count", 60, 50,
    ))
    assert ok is False
    assert db.added == []
