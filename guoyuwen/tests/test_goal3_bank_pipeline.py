from pathlib import Path

from app.engine.ml_model import FEATURE_COLUMNS


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_FEATURE_COLUMNS = [
    "user_txn_count_7d",
    "user_txn_count_30d",
    "user_total_txn_amount",
    "user_avg_txn_amount",
    "user_max_txn_amount",
    "user_bound_card_count",
    "user_failed_login_count_30d",
    "user_device_count",
    "user_loan_apply_count_30d",
    "user_loan_institution_count_30d",
    "user_max_debt_ratio",
    "user_night_operation_count_7d",
    "user_incoming_card_count_1h",
    "user_account_age_days",
    "order_event_amount",
    "order_txn_count_1h",
    "order_is_night",
    "order_new_device_days",
    "order_device_user_count",
    "order_payee_card_count_1h",
    "order_loan_institution_count_30d",
    "order_debt_ratio",
    "addr_is_proxy",
    "addr_is_tor",
    "addr_is_unusual",
]


def test_bank_feature_columns_are_exact_and_ordered():
    assert FEATURE_COLUMNS == EXPECTED_FEATURE_COLUMNS
    assert sum(name.startswith("user_") for name in FEATURE_COLUMNS) == 14
    assert sum(name.startswith("order_") for name in FEATURE_COLUMNS) == 8
    assert sum(name.startswith("addr_") for name in FEATURE_COLUMNS) == 3


def test_bank_rules_cover_seven_database_controls_and_black_card_seed():
    sql = (ROOT / "sql" / "init_risk_data.sql").read_text(encoding="utf-8")
    for rule_name in (
        "异地大额转账",
        "凌晨密集操作",
        "新设备大额",
        "多卡归集",
        "信贷申请突击",
        "设备多人共用",
        "代理/Tor IP",
    ):
        assert rule_name in sql
    assert "risk_blacklist" in sql
    assert "银行卡号" in sql
    assert "教学黑卡" in sql


def test_executable_pipeline_no_longer_imports_removed_ecommerce_models():
    executable_files = [
        ROOT / "app" / "engine" / "feature.py",
        ROOT / "app" / "engine" / "decision.py",
        ROOT / "app" / "service" / "event.py",
        ROOT / "app" / "agent" / "tools.py",
        ROOT / "scripts" / "gen_risky_users.py",
        ROOT / "scripts" / "gen_risk_data.py",
        ROOT / "scripts" / "gen_risk_data_with_dates.py",
        ROOT / "scripts" / "gen_train_dataset.py",
    ]
    removed_names = (
        "goal3_pending",
        "OrderInfo",
        "OrderDetail",
        "Postsale",
        "ReceiveInfo",
        "SkuInfo",
        "LogisticsComplaintsRecord",
    )
    for path in executable_files:
        content = path.read_text(encoding="utf-8")
        for name in removed_names:
            assert name not in content, f"{path.name} 仍引用已删除电商模型 {name}"


def test_risk_check_ui_only_exposes_four_bank_events_and_four_field_request():
    html = (ROOT / "templates" / "risk_check.html").read_text(encoding="utf-8")
    for event_type in ("登录", "转账", "贷款申请", "绑卡"):
        assert f'value="{event_type}"' in html
    for obsolete in ("下单", "售后申请", "物流投诉", "ck_order_id"):
        assert obsolete not in html
    assert "event_data" in html


def test_feature_labels_match_model_columns():
    app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    for feature_name in EXPECTED_FEATURE_COLUMNS:
        assert f'"{feature_name}"' in app_js


def test_blacklist_ui_uses_five_bank_schema_values_and_masks_output():
    html = (ROOT / "templates" / "blacklist.html").read_text(encoding="utf-8")
    for blacklist_type in ("用户", "设备指纹", "IP", "银行卡号", "身份证号"):
        assert f'value="{blacklist_type}"' in html
    assert "function maskValue" in html
    assert "maskValue(it.blacklist_type, it.blacklist_value)" in html
