"""Step 7 Agent、展示映射和旧电商依赖迁移回归保护。"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.chat import SYSTEM_PROMPT
from app.agent.explanation import FEATURE_DISPLAY_NAMES, explain_persisted_evidence
from app.agent import tools as agent_tools
from app.agent.tools import ALL_TOOLS, _BIZ_QUERY_HANDLERS
from app.industry_mapping import EVENT_MAPPINGS
from app.engine.ml_model import FEATURE_COLUMNS
from scripts.main import app


ROOT = Path(__file__).resolve().parent.parent


def test_agent_keeps_eight_tools_and_manufacturing_dispatch():
    assert len(ALL_TOOLS) == 8
    assert tuple(_BIZ_QUERY_HANDLERS) == (
        "dealer_info", "dealer_purchase_orders", "device_history",
        "warranty_claims", "cross_region_reports", "high_value_purchase_orders",
        "blacklist_extra", "risk_assessment_evidence",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_keys"),
    [
        ("add", {"db", "blacklist_type", "value", "reason"}),
        ("check", {"db", "blacklist_type", "value"}),
        ("list", {"db"}),
        ("remove", {"db", "blacklist_type", "value"}),
    ],
)
async def test_agent_blacklist_dispatch_passes_only_supported_arguments(
    monkeypatch, action, expected_keys,
):
    captured = {}

    async def handler(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setitem(agent_tools._BLACKLIST_ACTIONS, action, handler)
    result = await agent_tools._manage_blacklist_impl(
        db=object(), action=action, blacklist_type="用户",
        value="DLR001", reason="主体风险",
    )
    assert result == "ok"
    assert set(captured) == expected_keys


def test_agent_has_no_removed_ecommerce_orm_imports():
    text = (ROOT / "app" / "agent" / "tools.py").read_text(encoding="utf-8")
    for removed in ("UserInfo", "OrderInfo", "OrderDetail", "PostSale", "ReceiveInfo"):
        assert removed not in text
    for model in ("Dealer", "Device", "PurchaseOrder", "WarrantyClaim", "CrossRegionReport", "BlacklistExtra"):
        assert model in text


def test_agent_prompt_translates_internal_compatibility_codes():
    for term in ("经销商", "采购", "设备保修", "跨区域串货", "user_id 表示 dealer_id"):
        assert term in SYSTEM_PROMPT
    for forbidden in ("电商用户", "购物订单", "收货地址", "优惠券", "SKU购买行为"):
        assert forbidden not in SYSTEM_PROMPT


def test_evidence_explanation_quotes_persisted_result_without_recalculation():
    evidence = {
        "event_type_internal_code": "物流投诉",
        "decision": "拒绝",
        "risk_level": "极高",
        "final_score": 93,
        "ml_score": 0.8123,
        "triggered_rules": [{
            "rule_id": "R001", "rule_name": "跨区域串货",
            "condition": {"field": "addr_is_new", "op": "==", "value": 1},
        }],
        "features": [{"name": "addr_is_new", "value": 1.0, "entity_type": "地址"}],
    }
    result = explain_persisted_evidence(evidence)
    assert "串货举报" in result
    assert "拒绝" in result and "极高" in result and "最终分 93" in result
    assert "R001 跨区域串货" in result
    assert "addr_is_new" in result and "0.8123" in result


def test_feature_display_map_covers_frozen_25_dimensions():
    assert len(FEATURE_COLUMNS) == 25
    assert set(FEATURE_DISPLAY_NAMES) == set(FEATURE_COLUMNS)


def test_templates_use_manufacturing_labels_and_keep_internal_values():
    template_dir = ROOT / "templates"
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in template_dir.glob("*.html"))
    assert "电商风控系统" not in public_text
    for label in ("经销商采购提交", "设备保修申请", "串货举报/跨区域检查", "经销商ID"):
        assert label in public_text
    risk_page = (template_dir / "risk_check.html").read_text(encoding="utf-8")
    for internal_code in EVENT_MAPPINGS:
        assert f'value="{internal_code}"' in risk_page


def test_frontend_has_display_only_compatibility_mapping():
    app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "displayEventType" in app_js
    assert "displayRuleCategory" in app_js
    assert "displayBlacklistType" in app_js
    assert "制造业设备经销商智能风控平台" in app_js


def test_openapi_metadata_is_manufacturing_oriented():
    assert app.title == "制造业设备经销商智能风控平台"
    assert "XGBoost" in app.description
    assert "设备经销商" in app.description


@pytest.mark.asyncio
async def test_app_lifespan_loads_standard_25_feature_model():
    model = MagicMock()
    model.num_features.return_value = 25
    model.feature_names = FEATURE_COLUMNS
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock(return_value=None)
    with (
        patch("app.engine.ml_model.load_model", return_value=True),
        patch("app.engine.ml_model.get_model", return_value=model),
        patch("app.scheduler.start_scheduler"),
        patch("app.scheduler.stop_scheduler", new=AsyncMock(return_value=None)),
        patch("app.scheduler.is_running", return_value=True),
        patch("app.database.async_engine", new=fake_engine),
    ):
        async with app.router.lifespan_context(app):
            assert app.state.xgb_model_loaded is True
            assert app.state.xgb_model_feature_count == 25
            assert app.state.xgb_feature_contract_ok is True
