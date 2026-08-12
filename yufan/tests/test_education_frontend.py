"""阶段 11：教育页面文案、事件选项和规则分类映射测试。"""

from pathlib import Path

from jinja2 import Environment

from app.routers.rule import CORE_TO_EDUCATION_CATEGORY, EDUCATION_TO_CORE_CATEGORY


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def test_all_templates_have_valid_jinja_syntax():
    environment = Environment()
    for path in TEMPLATES.glob("*.html"):
        environment.parse(path.read_text(encoding="utf-8"))


def test_visible_pages_no_longer_use_ecommerce_vocabulary():
    content = "\n".join(path.read_text(encoding="utf-8") for path in TEMPLATES.glob("*.html"))
    for obsolete in (
        "电商风控系统", "下单", "售后申请", "物流投诉", "收货地址", "手机号", "商品", "SKU",
    ):
        assert obsolete not in content


def test_risk_check_has_four_education_events_and_device_field():
    content = (TEMPLATES / "risk_check.html").read_text(encoding="utf-8")
    for event_type in ("课程报名", "退费申请", "直播打赏", "学习行为"):
        assert f'value="{event_type}"' in content
    assert 'id="ck_device_id"' in content
    assert "device_id:" in content


def test_rule_category_mapping_is_bidirectional():
    assert set(EDUCATION_TO_CORE_CATEGORY) == {
        "报名异常", "退费滥用", "账号风险", "学习异常", "打赏风险", "设备风险",
    }
    for education, core in EDUCATION_TO_CORE_CATEGORY.items():
        assert CORE_TO_EDUCATION_CATEGORY[core] == education


def test_base_brand_and_static_script_are_education_specific():
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "教育风控中心" in base
    assert "教育行业风控系统" in script
