"""黑名单软删/过期逻辑测试 (P1-2 修复验证: check_blacklist 必须过滤软删)"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.service.case import check_blacklist


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDB:
    def __init__(self, row):
        self._row = row

    async def execute(self, stmt):
        return _FakeResult(self._row)


def _row(deleted_at=None, expire_time=None):
    return SimpleNamespace(blacklist_id=1, deleted_at=deleted_at, expire_time=expire_time)


def _check(row) -> bool:
    return asyncio.run(check_blacklist(_FakeDB(row), "手机号", "13800000000"))


def test_active_blacklist_hit():
    assert _check(_row()) is True


def test_soft_deleted_blacklist_miss():
    """已移除(软删)的黑名单不应再命中 — P1-2 修复点"""
    assert _check(_row(deleted_at=datetime.now())) is False


def test_expired_blacklist_miss():
    assert _check(_row(expire_time=datetime.now() - timedelta(days=1))) is False


def test_not_expired_blacklist_hit():
    assert _check(_row(expire_time=datetime.now() + timedelta(days=1))) is True


def test_no_record_miss():
    assert _check(None) is False
