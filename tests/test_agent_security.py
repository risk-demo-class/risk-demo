"""Agent 安全测试 (2026-08-11 P1): LLM 上下文脱敏 + 业务数据访问审计."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent import tools as tools_module
from app.config import settings
from app.models_risk import RiskDataAccessLog


class FakeRow:
    """模拟 SQLAlchemy Row: 有 _mapping 属性即可."""

    def __init__(self, data: dict):
        self._mapping = data


def _make_db(rows: list[dict]) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[FakeRow(r) for r in rows])))
    db.commit = AsyncMock()
    return db


class TestBusinessDataMasking:
    async def _run(self, db, monkeypatch, mask: bool):
        monkeypatch.setattr(settings, "LLM_DATA_MASK", mask)
        return await tools_module._query_business_data_impl(
            db=db, query_type="drug_orders", user_id="RISK001", order_id="", limit=5,
        )

    @pytest.mark.asyncio
    async def test_mask_on_masks_receiver_name(self, monkeypatch):
        db = _make_db([{"drug_order_id": "DG_1", "receiver_name": "赵大勇", "total_amount": 120}])
        out = json.loads(await self._run(db, monkeypatch, mask=True))
        assert out[0]["receiver_name"] == "****"
        assert out[0]["total_amount"] == 120

    @pytest.mark.asyncio
    async def test_mask_off_keeps_raw(self, monkeypatch):
        db = _make_db([{"drug_order_id": "DG_1", "receiver_name": "赵大勇", "total_amount": 120}])
        out = json.loads(await self._run(db, monkeypatch, mask=False))
        assert out[0]["receiver_name"] == "赵大勇"

    @pytest.mark.asyncio
    async def test_diagnosis_masked_in_rx_query(self, monkeypatch):
        db = _make_db([{"rx_id": "RX_1", "diagnosis_name": "原发性高血压"}])
        out = json.loads(await tools_module._query_business_data_impl(
            db=db, query_type="user_rxs", user_id="RISK001", order_id="", limit=5,
        ))
        assert out[0]["diagnosis_name"] == "****"


class TestDataAccessAudit:
    @pytest.mark.asyncio
    async def test_audit_row_inserted(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_DATA_MASK", True)
        db = _make_db([{"drug_order_id": "DG_1", "receiver_name": "x"}])
        await tools_module._query_business_data_impl(
            db=db, query_type="drug_orders", user_id="RISK001", order_id="ORD1", limit=5,
        )
        # 审计行写入: RiskDataAccessLog 且字段正确
        added = [c for c in db.add.call_args.args if isinstance(c, RiskDataAccessLog)]
        assert added, "应写入 RiskDataAccessLog 审计行"
        log = added[0]
        assert log.operator == "ai_agent"
        assert log.query_type == "drug_orders"
        assert log.user_id == "RISK001"
        assert log.order_id == "ORD1"
        assert log.limit_count == 5
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_audit_on_unknown_query_type(self):
        db = _make_db([])
        result = await tools_module._query_business_data_impl(
            db=db, query_type="hack", user_id="RISK001", order_id="", limit=5,
        )
        assert "不支持的查询类型" in result
        db.add.assert_not_called()
