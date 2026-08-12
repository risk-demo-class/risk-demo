"""
黑名单镜像同步测试 (DB-free)
验证 risk_blacklist 增删时, 业务台账 blacklist_extra 同步写入/软删:
  - 支持 护照号/签证号/设备指纹 (blacklist_extra ENUM 限定)
  - 用户/地址/手机号 不入台账 (ENUM 不支持, 决策仍走 risk_blacklist)
  - 移除统一走软删 (含台账同步 + 审计)
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import BlacklistCreate
from app.service import case as case_module
from app.models import BlacklistExtra


class _FakeDB:
    """极简 DB mock: 记录 execute 次数与 db.add 的对象."""

    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.executed = 0

    async def execute(self, stmt):
        self.executed += 1
        class _R:
            def __init__(self, e):
                self.e = e
            def scalar_one_or_none(self):
                return self.e
        return _R(self.existing)

    def add(self, obj):
        self.added.append(obj)


class TestMirrorTypes:
    def test_supported_types(self):
        assert {"护照号", "签证号", "设备指纹"} == case_module._MIRROR_TYPES

    def test_user_not_in_mirror(self):
        assert "用户" not in case_module._MIRROR_TYPES
        assert "地址" not in case_module._MIRROR_TYPES


class TestSyncBlacklistExtra:
    @pytest.mark.asyncio
    async def test_unsupported_type_noop(self):
        """用户/地址/手机号不入台账: 不查询不写入."""
        db = _FakeDB()
        await case_module._sync_blacklist_extra(db, "用户", "U1", "r", None)
        assert db.executed == 0
        assert db.added == []

    @pytest.mark.asyncio
    async def test_supported_type_new_insert(self):
        """护照号不存在 → 新增台账行."""
        db = _FakeDB(existing=None)
        await case_module._sync_blacklist_extra(
            db, "护照号", "E11223344", "涉黑护照", None,
        )
        assert db.executed == 1
        assert len(db.added) == 1
        row = db.added[0]
        assert isinstance(row, BlacklistExtra)
        assert row.type == "护照号"
        assert row.value == "E11223344"
        assert row.reason == "涉黑护照"
        assert row.deleted_at is None

    @pytest.mark.asyncio
    async def test_supported_type_update_existing(self):
        """已存在台账行 → 更新 reason/expire_at/deleted_at, 不新增."""
        row = SimpleNamespace(reason="old", expire_at=None, deleted_at=None)
        db = _FakeDB(existing=row)
        now = datetime.now()
        await case_module._sync_blacklist_extra(
            db, "设备指纹", "DEVICE_001", "新原因", now, deleted_at=None,
        )
        assert db.added == []
        assert row.reason == "新原因"
        assert row.expire_at == now
        assert row.deleted_at is None

    @pytest.mark.asyncio
    async def test_soft_deleted_row_can_reactivate(self):
        """软删后的台账行重新加黑 → 置回 deleted_at=None (解除软删)."""
        row = SimpleNamespace(reason="旧", expire_at=None, deleted_at=datetime.now())
        db = _FakeDB(existing=row)
        await case_module._sync_blacklist_extra(
            db, "签证号", "VISA_001", "重新加入", None, deleted_at=None,
        )
        assert row.deleted_at is None
        assert row.reason == "重新加入"


class TestAddBlacklistSync:
    """add_blacklist 两条路径 (新增/更新) 都会触发台账同步."""

    def _mock_db(self, existing):
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=existing),
        ))
        # 模拟 db.add + flush: 给新对象赋自增 ID (否则 BlacklistResponse 校验失败)
        def fake_add(obj):
            if hasattr(obj, "blacklist_id") and obj.blacklist_id is None:
                obj.blacklist_id = 1
                obj.create_time = datetime.now()
        db.add = fake_add
        db.flush = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_new_insert_syncs_mirror(self):
        db = self._mock_db(existing=None)
        with patch.object(case_module, "record_action", new=AsyncMock()), \
             patch.object(case_module, "_sync_blacklist_extra", new=AsyncMock()) as sync:
            await case_module.add_blacklist(db, BlacklistCreate(
                blacklist_type="护照号", blacklist_value="E999", reason="测试",
            ))
        sync.assert_awaited_once()
        args = sync.call_args.args
        assert args[1] == "护照号"
        assert args[2] == "E999"
        assert args[3] == "测试"
        assert args[4] is None      # expire_time
        assert sync.call_args.kwargs["deleted_at"] is None

    @pytest.mark.asyncio
    async def test_existing_update_syncs_mirror(self):
        existing = SimpleNamespace(
            blacklist_id=1, blacklist_type="护照号", blacklist_value="E999",
            reason="旧", expire_time=None, create_time=None,
        )
        db = self._mock_db(existing=existing)
        with patch.object(case_module, "record_action", new=AsyncMock()), \
             patch.object(case_module, "_sync_blacklist_extra", new=AsyncMock()) as sync:
            await case_module.add_blacklist(db, BlacklistCreate(
                blacklist_type="护照号", blacklist_value="E999", reason="新",
            ))
        sync.assert_awaited_once()
        assert sync.call_args.args[1:3] == ("护照号", "E999")


class TestRemoveBlacklistSync:
    """remove_blacklist 软删时同步软删台账行."""

    @pytest.mark.asyncio
    async def test_remove_syncs_mirror_with_deleted_at(self):
        bl = SimpleNamespace(
            blacklist_id=1, blacklist_type="护照号", blacklist_value="E999",
            reason="r", expire_time=None,
        )
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=bl),
        ))
        db.commit = AsyncMock()
        with patch.object(case_module, "record_action", new=AsyncMock()), \
             patch.object(case_module, "_sync_blacklist_extra", new=AsyncMock()) as sync:
            ok = await case_module.remove_blacklist(db, 1)
        assert ok is True
        sync.assert_awaited_once()
        args = sync.call_args.args
        kwargs = sync.call_args.kwargs
        assert args[1:3] == ("护照号", "E999")
        assert kwargs["deleted_at"] is not None
        assert bl.deleted_at is not None
