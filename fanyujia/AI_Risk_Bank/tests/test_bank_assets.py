"""银行版 SQL、规则和造数资产的静态契约。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FRONTEND_COPY_FILES = (
    *(ROOT / "templates").glob("*.html"),
    ROOT / "static" / "app.js",
    ROOT / "app" / "agent" / "chat.py",
    ROOT / "scripts" / "main.py",
)


def test_bank_generator_and_business_tables_are_present():
    generator = ROOT / "scripts" / "gen_business_data.py"
    ddl = (ROOT / "sql" / "init_business_tables.sql").read_text(encoding="utf-8")

    assert generator.exists()
    for table in ("bank_user_info", "bank_card", "bank_transaction", "loan_application", "login_log", "device_fingerprint", "ip_geo_location", "payee_relationship"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in ddl


def test_bank_rule_seed_covers_eight_required_scenarios():
    rules = (ROOT / "sql" / "init_risk_data.sql").read_text(encoding="utf-8")

    for rule_name in ("异地大额转账", "凌晨密集交易", "新设备大额交易", "多卡资金归集", "贷款申请突击", "设备多人共用", "代理IP访问", "Tor出口访问"):
        assert rule_name in rules


def test_user_facing_frontend_has_no_ecommerce_terms():
    """银行版页面、助手文案和应用元数据不应暴露电商领域术语。"""
    forbidden_terms = ("电商", "订单", "售后", "收货", "手机号", "物流", "商品", "退款", "投诉")

    for path in FRONTEND_COPY_FILES:
        text = path.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in text, f"{path.relative_to(ROOT)} still contains {term!r}"
