"""
check_blacklist 软删过滤回归测试 (P4-L5 2026-08-10):
- 真实案例: 用户在前端删除黑名单, 风控检查时仍报"撞黑"
- 根因: case.check_blacklist SQL 没加 deleted_at IS NULL 过滤
- 修复: 跟 add_blacklist / get_blacklist / remove_blacklist 保持一致
"""
from unittest.mock import AsyncMock, MagicMock

import pytest


# ============================================================
# 1. check_blacklist SQL 必须过滤软删
# ============================================================

class TestCheckBlacklistSQL:
    """check_blacklist 必须过滤 deleted_at IS NULL, 跟 add/get/remove 一致."""

    def test_check_blacklist_filters_soft_deleted(self):
        """【P4-L5 修复核心】软删的记录不判为撞黑."""
        from app.service.case import check_blacklist
        import inspect
        src = inspect.getsource(check_blacklist)
        # 必须有 deleted_at.is_(None) 过滤
        assert "deleted_at" in src, (
            "check_blacklist SQL 没过滤 deleted_at, 软删的记录会被误判为撞黑"
        )
        assert "is_(None)" in src or "IS NULL" in src, (
            "check_blacklist SQL 没正确写 deleted_at IS NULL 过滤"
        )

    def test_check_blacklist_signature_unchanged(self):
        """check_blacklist 签名必须是 (db, blacklist_type, value) -> bool."""
        from app.service.case import check_blacklist
        import inspect
        sig = inspect.signature(check_blacklist)
        params = list(sig.parameters.keys())
        assert params == ["db", "blacklist_type", "value"], (
            f"check_blacklist 签名应是 (db, blacklist_type, value), 实际 {params}"
        )

    def test_check_blacklist_returns_bool(self):
        """返回类型保持 bool (前端不需改)."""
        from app.service.case import check_blacklist
        import inspect
        sig = inspect.signature(check_blacklist)
        assert sig.return_annotation is bool, (
            f"check_blacklist 应返回 bool, 实际 {sig.return_annotation}"
        )


# ============================================================
# 2. 黑名单 4 个函数 SQL 都过滤软删 (一致性)
# ============================================================

class TestBlacklistFunctionsConsistency:
    """4 个黑名单管理函数必须都过滤 deleted_at IS NULL (P3-M9 软删规范)."""

    def test_add_blacklist_filters_soft_deleted(self):
        from app.service.case import add_blacklist
        import inspect
        assert "deleted_at" in inspect.getsource(add_blacklist)

    def test_check_blacklist_filters_soft_deleted(self):
        from app.service.case import check_blacklist
        import inspect
        assert "deleted_at" in inspect.getsource(check_blacklist)

    def test_get_blacklist_filters_soft_deleted(self):
        from app.service.case import get_blacklist
        import inspect
        assert "deleted_at" in inspect.getsource(get_blacklist)

    def test_remove_blacklist_filters_soft_deleted(self):
        from app.service.case import remove_blacklist
        import inspect
        assert "deleted_at" in inspect.getsource(remove_blacklist)


# ============================================================
# 3. 端到端: 软删后不撞黑
# ============================================================

class TestSoftDeletedBlacklistBehavior:
    """mock DB, 模拟: 数据库里有一条已软删的 (deleted_at != NULL) 记录, check_blacklist 应该返回 False."""

    def _make_db_with_bl(self, bl):
        """db.execute 返回 awaitable, scalar_one_or_none 返回 bl."""
        db = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none = MagicMock(return_value=bl)
        db.execute = AsyncMock(return_value=result_mock)
        return db

    @pytest.mark.asyncio
    async def test_soft_deleted_record_returns_false(self):
        """【P4-L5 修复】软删记录不应该触发撞黑拦截."""
        from app.service.case import check_blacklist

        # 关键: scalar_one_or_none() 返回 None (因为 SQL 加了 deleted_at IS NULL 过滤)
        # 模拟"SQL 过滤后没找到记录"的情况
        db = self._make_db_with_bl(None)
        is_blocked = await check_blacklist(db, "用户", "1003")
        assert is_blocked is False, (
            "软删的记录 (deleted_at != NULL) 不应该判为撞黑, "
            "check_blacklist 必须过滤 deleted_at IS NULL"
        )

    @pytest.mark.asyncio
    async def test_active_record_returns_true(self):
        """未软删 + 未过期 = 撞黑 (True)."""
        from app.service.case import check_blacklist
        from datetime import datetime, timedelta

        fake_bl = MagicMock()
        fake_bl.blacklist_type = "用户"
        fake_bl.blacklist_value = "U999"
        fake_bl.deleted_at = None
        fake_bl.expire_time = datetime.now() + timedelta(days=30)

        db = self._make_db_with_bl(fake_bl)
        is_blocked = await check_blacklist(db, "用户", "U999")
        assert is_blocked is True, "未软删 + 未过期 应该判为撞黑"

    @pytest.mark.asyncio
    async def test_expired_record_returns_false(self):
        """已过期的记录不撞黑 (业务: 黑名单有 expire_time 字段)."""
        from app.service.case import check_blacklist
        from datetime import datetime, timedelta

        fake_bl = MagicMock()
        fake_bl.blacklist_type = "用户"
        fake_bl.blacklist_value = "U888"
        fake_bl.deleted_at = None
        fake_bl.expire_time = datetime.now() - timedelta(days=1)

        db = self._make_db_with_bl(fake_bl)
        is_blocked = await check_blacklist(db, "用户", "U888")
        assert is_blocked is False, "已过期记录不撞黑"


# ============================================================
# 4. P3-M9 软删: 删黑名单后再加回 (id 复用 / 不冲突)
# ============================================================

class TestRemoveAndReaddBlacklist:
    """P3-M9: 软删 (UPDATE deleted_at) 不是硬删, 再 add 时应该找到现有行更新 reason/expire_time."""

    @pytest.mark.asyncio
    async def test_add_after_soft_delete_finds_existing(self):
        """验证 add_blacklist 的 SELECT 用 deleted_at IS NULL (避免找到已软删的)."""
        # 通过静态源码检查确保 add_blacklist 查 (type, value) 唯一时过滤 deleted_at
        from app.service.case import add_blacklist
        import inspect
        src = inspect.getsource(add_blacklist)
        # 1. SELECT 那块必须有 deleted_at 过滤
        select_block = src[src.index("select(RiskBlacklist)"):src.index("))", src.index("select(RiskBlacklist)"))]
        assert "deleted_at" in select_block, (
            "add_blacklist 第一次 SELECT 没过滤 deleted_at, 会把已软删的当 existing, 走更新分支 (bug)"
        )
        # 2. 修复后行为: 用 (deleted_at IS NULL) 过滤, 软删的不算 existing
        #    → 重新 add 走插入分支, db.add(bl) 被调
        #    修复前: 软删的会被找到 → 走更新分支, 不会调 db.add(bl)
        # 这里只验证 SQL 写法对, 实际跑通需要真 DB, 留给集成测试
        assert "is_(None)" in select_block, "应用 deleted_at.is_(None) 过滤"

    @pytest.mark.asyncio
    async def test_add_after_soft_delete_resurrects_same_row(self):
        """【P1 修复 2026-08-12】软删后重建必须复活同一行, 而不是新插入 (否则撞唯一索引 500).

        修复前: 唯一索引 (type, value) 不含 deleted_at, 软删行仍占位 → INSERT IntegrityError → 500.
        修复后: add_blacklist 先找软删行, 复活 (deleted_at=None + 更新 reason/expire).
        """
        from datetime import datetime

        from app.schemas import BlacklistCreate
        from app.service.case import add_blacklist
        from app.models_risk import RiskBlacklist

        soft = RiskBlacklist(
            blacklist_id=99, blacklist_type="用户", blacklist_value="U999",
            reason="旧原因", expire_time=None,
        )
        soft.deleted_at = datetime(2026, 8, 1, 12, 0, 0)

        db = MagicMock()
        active_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        soft_result = MagicMock(
            scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=soft)))
        )
        db.execute = AsyncMock(side_effect=[active_result, soft_result])

        resp = await add_blacklist(
            db, BlacklistCreate(blacklist_type="用户", blacklist_value="U999", reason="新原因"),
        )
        assert resp.blacklist_id == 99, "应复用软删行的同一 ID"
        assert soft.deleted_at is None, "deleted_at 应被清空 (复活)"
        assert soft.reason == "新原因"
        # 复活路径不调用 db.add 插入新行 (record_action 用 db.add 记审计)
        calls = [c.args[0] for c in db.add.call_args_list]
        assert all(not isinstance(x, RiskBlacklist) for x in calls), "不应插入新的 RiskBlacklist 行"

    @pytest.mark.asyncio
    async def test_readd_active_duplicate_returns_409_not_500(self):
        """【P1 修复 2026-08-12】并发撞唯一索引时, 路由应返回 409 而非裸 500."""
        from fastapi import HTTPException
        from sqlalchemy.exc import IntegrityError
        from unittest.mock import patch

        from app.routers import blacklist as bl_router
        from app.schemas import BlacklistCreate

        db = MagicMock()
        db.rollback = AsyncMock()

        async def boom(_db, _data):
            raise IntegrityError("stmt", {}, Exception("dup"))

        with patch.object(bl_router, "add_blacklist", side_effect=boom):
            with pytest.raises(HTTPException) as exc:
                await bl_router.api_add_blacklist(
                    BlacklistCreate(blacklist_type="用户", blacklist_value="U1"), db,
                )
        assert exc.value.status_code == 409
        assert "已存在" in exc.value.detail
