"""银行信贷风控 - 前端页面文案断言 (RED 基线).

期望: 华信银行品牌 + 4 银行事件 + 6 银行规则分类,
      不含电商文案 (订单/下单/支付/物流投诉).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

BANK_EVENTS = ["贷款申请", "放款", "还款", "客户投诉"]
BANK_CATEGORIES = ["欺诈风险", "信用风险", "反洗钱", "账户风险", "贷后风险", "合规风险"]
ECOM_WORDS = ["下单", "支付", "售后申请", "物流投诉", "订单欺诈", "物流风险"]


def _read(name: str) -> str:
    return (TEMPLATES / name).read_text(encoding="utf-8")


def test_base_bank_brand():
    """base.html: 华信银行 · 信贷风控品牌."""
    html = _read("base.html")
    assert ("华信银行" in html or "信贷风控" in html), "品牌栏应为华信银行/信贷风控"
    assert "电商风控" not in html, "不应残留电商字样"


def test_dashboard_bank_copy():
    """dashboard.html: 银行指标文案, 无电商订单语义."""
    html = _read("dashboard.html")
    assert ("贷款申请" in html or "申请量" in html or "放款" in html), "仪表盘应有银行指标"
    assert "订单量" not in html and "订单总数" not in html, "不应残留订单指标"


def test_risk_check_bank_events():
    """risk_check.html: 4 个银行事件类型."""
    html = _read("risk_check.html")
    for ev in BANK_EVENTS:
        assert f'value="{ev}"' in html or ev in html, f"缺少银行事件 {ev}"
    for w in ["下单", "支付", "售后申请", "物流投诉"]:
        assert f'value="{w}"' not in html, f"不应残留电商事件 {w}"


def test_rules_bank_categories():
    """rules.html: 6 个银行规则分类."""
    html = _read("rules.html")
    for cat in BANK_CATEGORIES:
        assert f'value="{cat}"' in html or cat in html, f"缺少银行分类 {cat}"
    for w in ["订单欺诈", "支付风险", "售后滥用"]:
        assert f'value="{w}"' not in html, f"不应残留电商分类 {w}"