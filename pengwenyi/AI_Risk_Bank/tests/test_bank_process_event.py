"""
【银行版】测试 - process_event 4 步流程 (结构保持) + 业务实体归属校验

4 步业务流 (纪律约束, 结构不可变):
  1. 业务实体校验 validate_risk_check_request
  2. 自动补全 _enrich_request
  3. 黑名单前置拦截 _check_all_blacklists (短路)
  4. 决策引擎 run_risk_check (7 步)
"""
import re
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas import RiskCheckRequest, RiskCheckResponse
from app.service import event as event_module
from app.service.validator import ensure_source_belongs_to_user

ROOT = Path(__file__).resolve().parent.parent


def _make_request(**overrides) -> RiskCheckRequest:
    base = dict(event_type="转账", source_id="txn_001", user_id="1001", ip="10.0.0.1")
    base.update(overrides)
    return RiskCheckRequest(**base)


class TestProcessEventFourSteps:
    """event.py 源码 + mock 集成: 4 步流程结构保持."""

    def test_source_keeps_four_step_structure(self):
        """process_event 源码必须保持 4 步顺序注释 (纪律约束)."""
        src = (ROOT / "app" / "service" / "event.py").read_text(encoding="utf-8")
        func = src.split("async def process_event", 1)[1]
        # 4 步按顺序出现
        step_markers = [
            "1. 业务实体校验",
            "2. 补全 from_card/to_card/device_id/ip",
            "3. 黑名单前置检查",
            "4. 决策引擎 7 步",
        ]
        idx = -1
        for marker in step_markers:
            i = func.index(marker)
            assert i > idx, f"4 步顺序被破坏: {marker}"
            idx = i
        # 4 步必须真实调用对应函数
        assert "validate_risk_check_request(db, request)" in func, "第 1 步校验"
        assert "await _enrich_request(db, request)" in func, "第 2 步补全"
        assert "await _check_all_blacklists(db, request)" in func, "第 3 步黑名单"
        assert "return await run_risk_check(db, request)" in func, "第 4 步决策引擎"

    @pytest.mark.asyncio
    async def test_four_steps_called_in_order(self):
        """mock 集成: 4 步按 validate → enrich → blacklist → run 顺序执行."""
        calls = []
        db = MagicMock()

        async def fake_validate(_db, _req):
            calls.append("validate")

        async def fake_enrich(_db, req):
            calls.append("enrich")
            return req

        async def fake_blacklist(_db, _req):
            calls.append("blacklist")
            return None

        async def fake_run(_db, _req):
            calls.append("run_risk_check")
            return RiskCheckResponse(
                assessment_id="ast_test", event_id="evt_test",
                user_id="1001", final_score=10, risk_level="低",
                decision="通过", rule_count=0, triggered_rules=[],
                features={}, create_time=datetime.now(), blocked_by=None,
            )

        with patch.object(event_module, "validate_risk_check_request", side_effect=fake_validate), \
             patch.object(event_module, "_enrich_request", side_effect=fake_enrich), \
             patch.object(event_module, "_check_all_blacklists", side_effect=fake_blacklist), \
             patch.object(event_module, "run_risk_check", side_effect=fake_run):
            resp = await event_module.process_event(db, _make_request())

        assert calls == ["validate", "enrich", "blacklist", "run_risk_check"], (
            f"4 步调用顺序错误: {calls}"
        )
        assert resp.decision == "通过"

    @pytest.mark.asyncio
    async def test_blacklist_hit_short_circuits_step4(self):
        """撞黑 → 短路, 不调 run_risk_check (只走 1→2→3)."""
        calls = []
        db = MagicMock()

        async def fake_validate(_db, _req):
            calls.append("validate")

        async def fake_enrich(_db, req):
            calls.append("enrich")
            return req

        async def fake_blacklist(_db, _req):
            calls.append("blacklist")
            return "用户"

        async def fake_run(_db, _req):
            calls.append("run_risk_check")
            raise AssertionError("撞黑后不应进第 4 步")

        with patch.object(event_module, "validate_risk_check_request", side_effect=fake_validate), \
             patch.object(event_module, "_enrich_request", side_effect=fake_enrich), \
             patch.object(event_module, "_check_all_blacklists", side_effect=fake_blacklist), \
             patch.object(event_module, "run_risk_check", side_effect=fake_run):
            resp = await event_module.process_event(db, _make_request())

        assert calls == ["validate", "enrich", "blacklist"]
        assert resp.decision == "拒绝"
        assert resp.blocked_by == "用户"


class TestEnrichRequestBankMapping:
    """_enrich_request 按事件补全 (转账/登录/贷款/信用卡)."""

    @pytest.mark.asyncio
    async def test_transfer_enriches_card_device_ip(self):
        """转账: 从交易记录补全 from_card/to_card/device_id/ip."""
        db = MagicMock()
        row = MagicMock(from_card="C1", to_card="C2", device_id="D1", ip="1.2.3.4")
        db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=row)))
        request = _make_request(from_card=None, to_card=None, device_id=None, ip=None)
        enriched = await event_module._enrich_request(db, request)
        assert enriched.from_card == "C1"
        assert enriched.to_card == "C2"
        assert enriched.device_id == "D1"
        assert enriched.ip == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_loan_enriches_amount_to_event_data(self):
        """贷款申请: 金额/期限/负债率/月收入 补到 event_data."""
        db = MagicMock()
        row = MagicMock(amount=100000, term_months=12, debt_ratio=0.65, monthly_income=8000)
        db.execute = AsyncMock(return_value=MagicMock(first=MagicMock(return_value=row)))
        request = _make_request(event_type="贷款申请", source_id="loan_001")
        enriched = await event_module._enrich_request(db, request)
        ed = enriched.event_data or {}
        assert ed["amount"] == 100000
        assert ed["term_months"] == 12
        assert ed["debt_ratio"] == 0.65
        assert ed["monthly_income"] == 8000


class TestBelongsToUserOwnership:
    """归属校验 (防水平越权): source_id 必须属于请求用户."""

    @pytest.mark.asyncio
    async def test_transfer_owner_match_passes(self):
        """转账: txn_id 付款卡归属 == 请求用户 → 通过."""
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="1001"))
        )
        await ensure_source_belongs_to_user(db, _make_request())

    @pytest.mark.asyncio
    async def test_transfer_owner_mismatch_raises_403(self):
        """转账: 归属他人 → 403 越权拒绝."""
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="9999"))
        )
        with pytest.raises(HTTPException) as ei:
            await ensure_source_belongs_to_user(db, _make_request())
        assert ei.value.status_code == 403
        assert "9999" in ei.value.detail

    @pytest.mark.asyncio
    async def test_source_not_found_raises_404(self):
        """source_id 不存在 → 404."""
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        with pytest.raises(HTTPException) as ei:
            await ensure_source_belongs_to_user(db, _make_request())
        assert ei.value.status_code == 404

    @pytest.mark.asyncio
    async def test_login_owner_match_passes(self):
        """登录: login_id 归属 == 请求用户 → 通过."""
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="1001"))
        )
        await ensure_source_belongs_to_user(
            db, _make_request(event_type="登录", source_id="login_001"),
        )

    @pytest.mark.asyncio
    async def test_card_owner_match_passes(self):
        """信用卡: card_id 归属 == 请求用户 → 通过."""
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="1001"))
        )
        await ensure_source_belongs_to_user(
            db, _make_request(event_type="信用卡", source_id="card_001"),
        )

    def test_ownership_mapping_uses_bank_tables(self):
        """源码断言: 4 场景归属查询映射到银行表 (转账走卡归属 join)."""
        src = (ROOT / "app" / "service" / "validator.py").read_text(encoding="utf-8")
        body = src.split("async def ensure_source_belongs_to_user", 1)[1]
        assert "Transaction.from_card == BankCard.card_id" in body, "转账: 付款卡归属"
        assert "LoginLog.user_id" in body, "登录: login_log.user_id"
        assert "LoanApplication.user_id" in body, "贷款: loan_application.user_id"
        assert "BankCard.user_id" in body, "信用卡: bank_card.user_id"
        # 不允许回退到电商订单表
        assert "Order" not in body, "银行版不应引用电商订单表"
