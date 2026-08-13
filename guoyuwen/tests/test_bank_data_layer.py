"""Goal 2 银行数据层、事件契约和核心表冻结测试。"""

import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import Settings, settings
from app.models_business import (
    BankCard,
    BlacklistExtra,
    DeviceFingerprint,
    IpGeoLocation,
    LoanApplication,
    LoginLog,
    Transaction,
    UserInfo,
)
from app.schemas import BlacklistCreate, RiskCheckRequest, RuleCreate
from app.service import validator
from scripts import init_db

ROOT = Path(__file__).resolve().parents[1]

BUSINESS_TABLES = {
    "user_info",
    "bank_card",
    "bank_transaction",
    "loan_application",
    "login_log",
    "device_fingerprint",
    "ip_geo_location",
    "blacklist_extra",
}

CORE_TABLE_COLUMNS = {
    "risk_rule": {
        "rule_id",
        "rule_name",
        "rule_category",
        "event_type",
        "rule_condition",
        "risk_level",
        "risk_score",
        "action",
        "is_enabled",
        "priority",
        "description",
        "create_time",
        "update_time",
        "deleted_at",
    },
    "risk_event": {
        "event_id",
        "event_type",
        "event_source_id",
        "user_id",
        "event_data",
        "create_time",
    },
    "risk_feature": {
        "feature_id",
        "event_id",
        "entity_type",
        "entity_id",
        "feature_name",
        "feature_value",
        "compute_time",
    },
    "risk_assessment": {
        "assessment_id",
        "event_id",
        "user_id",
        "rule_results",
        "rule_count",
        "final_score",
        "risk_level",
        "decision",
        "ml_score",
        "ml_decision",
        "create_time",
    },
    "risk_case": {
        "case_id",
        "assessment_id",
        "user_id",
        "case_status",
        "case_category",
        "risk_detail",
        "reviewer",
        "review_comment",
        "review_time",
        "create_time",
        "update_time",
        "source_id",
        "event_type",
    },
    "risk_blacklist": {
        "blacklist_id",
        "blacklist_type",
        "blacklist_value",
        "reason",
        "expire_time",
        "create_time",
        "deleted_at",
    },
    "risk_user_profile": {
        "user_id",
        "risk_score",
        "risk_level",
        "total_orders",
        "total_refunds",
        "refund_rate",
        "avg_order_amount",
        "address_count",
        "complaint_count",
        "assessment_count",
        "last_assessment_time",
        "profile_data",
        "update_time",
    },
    "risk_action_log": {
        "log_id",
        "operator",
        "action_type",
        "target_type",
        "target_id",
        "before_value",
        "after_value",
        "ip",
        "remark",
        "create_time",
    },
    "risk_alert": {
        "alert_id",
        "alert_type",
        "alert_level",
        "alert_title",
        "alert_content",
        "metric_name",
        "metric_value",
        "threshold",
        "status",
        "handler",
        "resolve_time",
        "create_time",
    },
}


def _create_table_blocks(sql: str) -> dict[str, str]:
    pattern = re.compile(
        r"CREATE TABLE IF NOT EXISTS `(?P<name>[^`]+)`\s*\((?P<body>.*?)\)\s*ENGINE=",
        re.DOTALL | re.IGNORECASE,
    )
    return {match["name"]: match["body"] for match in pattern.finditer(sql)}


def _column_names(block: str) -> set[str]:
    return set(re.findall(r"^\s*`([^`]+)`\s+", block, re.MULTILINE))


class TestBusinessModels:
    def test_exactly_eight_bank_business_tables(self):
        models = (
            UserInfo,
            BankCard,
            Transaction,
            LoanApplication,
            LoginLog,
            DeviceFingerprint,
            IpGeoLocation,
            BlacklistExtra,
        )
        assert {model.__tablename__ for model in models} == BUSINESS_TABLES

    def test_primary_keys_and_relationships(self):
        assert list(UserInfo.__table__.primary_key.columns.keys()) == ["user_id"]
        assert list(BankCard.__table__.primary_key.columns.keys()) == ["card_id"]
        assert list(Transaction.__table__.primary_key.columns.keys()) == ["txn_id"]
        assert list(LoanApplication.__table__.primary_key.columns.keys()) == ["loan_id"]
        assert list(LoginLog.__table__.primary_key.columns.keys()) == ["login_id"]
        assert set(DeviceFingerprint.__table__.primary_key.columns.keys()) == {
            "device_id",
            "user_id",
        }
        assert list(IpGeoLocation.__table__.primary_key.columns.keys()) == ["ip"]
        assert list(BlacklistExtra.__table__.primary_key.columns.keys()) == ["entry_id"]

        bank_card_fks = {fk.target_fullname for fk in BankCard.__table__.foreign_keys}
        login_fks = {fk.target_fullname for fk in LoginLog.__table__.foreign_keys}
        txn_fks = {fk.target_fullname for fk in Transaction.__table__.foreign_keys}
        assert "user_info.user_id" in bank_card_fks
        assert {"user_info.user_id", "ip_geo_location.ip"} <= login_fks
        assert {"bank_card.card_id", "ip_geo_location.ip"} <= txn_fks

    def test_required_query_indexes_exist(self):
        expected = {
            BankCard: {"ix_bank_card_user_active", "uq_bank_card_no_hash"},
            Transaction: {
                "ix_bank_transaction_from_time",
                "ix_bank_transaction_to_time",
                "ix_bank_transaction_device_time",
                "ix_bank_transaction_ip_time",
            },
            LoanApplication: {"ix_loan_user_apply", "ix_loan_institution_apply"},
            LoginLog: {
                "ix_login_user_time",
                "ix_login_device_time",
                "ix_login_ip_time",
            },
            DeviceFingerprint: {
                "ix_device_fingerprint_hash",
                "ix_device_user_last_seen",
            },
            IpGeoLocation: {"ix_ip_proxy_tor"},
            BlacklistExtra: {
                "uq_blacklist_extra_type_value",
                "ix_blacklist_extra_expire",
            },
        }
        for model, required_names in expected.items():
            actual_names = {index.name for index in model.__table__.indexes}
            actual_names.update(
                constraint.name
                for constraint in model.__table__.constraints
                if constraint.name is not None
            )
            assert required_names <= actual_names

    def test_orm_and_business_ddl_have_same_tables_and_columns(self):
        sql = (ROOT / "sql" / "init_business_tables.sql").read_text(encoding="utf-8")
        blocks = _create_table_blocks(sql)
        assert set(blocks) == BUSINESS_TABLES

        models = (
            UserInfo,
            BankCard,
            Transaction,
            LoanApplication,
            LoginLog,
            DeviceFingerprint,
            IpGeoLocation,
            BlacklistExtra,
        )
        for model in models:
            orm_columns = set(model.__table__.columns.keys())
            assert _column_names(blocks[model.__tablename__]) == orm_columns
            for column in model.__table__.columns:
                definition = next(
                    (
                        line
                        for line in blocks[model.__tablename__].splitlines()
                        if line.lstrip().startswith(f"`{column.name}`")
                    ),
                    None,
                )
                assert definition, (
                    f"DDL 缺少字段定义: {model.__tablename__}.{column.name}"
                )
                ddl_column = definition.upper()
                assert ("NOT NULL" in ddl_column) == (not column.nullable)


class TestFrozenCoreTables:
    def test_core_nine_table_names_and_columns_are_unchanged(self):
        sql = (ROOT / "sql" / "init_risk_tables.sql").read_text(encoding="utf-8")
        blocks = _create_table_blocks(sql)
        assert set(blocks) == set(CORE_TABLE_COLUMNS)
        for table_name, expected_columns in CORE_TABLE_COLUMNS.items():
            assert _column_names(blocks[table_name]) == expected_columns


class TestBankConfigurationAndSchemas:
    def test_database_names_are_dedicated(self):
        assert Settings.model_fields["DB_NAME"].default == "bank_risk"
        assert Settings.model_fields["TEST_DB_NAME"].default == "bank_risk_test"
        assert Settings.model_fields["DB_PASSWORD"].default == ""

    def test_four_event_thresholds_and_bank_taxonomies(self):
        assert set(settings.BANK_EVENT_TYPES) == {"登录", "转账", "贷款申请", "绑卡"}
        assert set(settings.RISK_EVENT_THRESHOLDS) >= set(settings.BANK_EVENT_TYPES) | {
            "通用"
        }
        assert set(settings.BANK_RULE_CATEGORIES) == {
            "账户接管",
            "交易欺诈",
            "信贷风险",
            "卡片风险",
            "设备风险",
            "名单风险",
        }
        assert set(settings.BLACKLIST_TYPES) == {
            "用户",
            "设备指纹",
            "IP",
            "银行卡号",
            "身份证号",
        }

    @pytest.mark.parametrize("event_type", ["登录", "转账", "贷款申请", "绑卡"])
    def test_risk_check_accepts_bank_events(self, event_type):
        request = RiskCheckRequest(
            event_type=event_type, source_id="SRC_DEMO_001", user_id="USR_DEMO_001"
        )
        assert request.event_type == event_type

    def test_ecommerce_event_is_rejected(self):
        with pytest.raises(ValidationError):
            RiskCheckRequest(
                event_type="下单", source_id="SRC_DEMO_001", user_id="USR_DEMO_001"
            )

    @pytest.mark.parametrize(
        "blacklist_type", ["用户", "设备指纹", "IP", "银行卡号", "身份证号"]
    )
    def test_blacklist_schema_accepts_bank_types(self, blacklist_type):
        assert (
            BlacklistCreate(
                blacklist_type=blacklist_type, blacklist_value="MASKED_DEMO"
            ).blacklist_type
            == blacklist_type
        )

    @pytest.mark.parametrize(
        "category",
        ["账户接管", "交易欺诈", "信贷风险", "卡片风险", "设备风险", "名单风险"],
    )
    def test_rule_schema_accepts_bank_categories(self, category):
        rule = RuleCreate(
            rule_id="R_DEMO",
            rule_name="教学规则",
            rule_category=category,
            event_type="通用",
            rule_condition={"field": "demo", "op": "==", "value": 1},
            risk_level="低",
            risk_score=10,
            action="标记",
        )
        assert rule.rule_category == category


class TestInitializationSafety:
    def test_init_script_only_allows_dedicated_databases(self):
        assert init_db.ALLOWED_DATABASES == {"bank_risk", "bank_risk_test"}

    def test_primary_sql_files_do_not_switch_to_another_database(self):
        for filename in (
            "init_business_tables.sql",
            "init_risk_tables.sql",
            "init_business_data.sql",
            "init_risk_data.sql",
        ):
            sql = (ROOT / "sql" / filename).read_text(encoding="utf-8")
            assert not re.search(r"^\s*USE\s+", sql, re.MULTILINE | re.IGNORECASE)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("row, expected", [((1,), True), (None, False)])
    async def test_keep_data_detects_existing_rules(self, row, expected):
        class _Cursor:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def execute(self, statement):
                assert statement == "SELECT 1 FROM `risk_rule` LIMIT 1"

            async def fetchone(self):
                return row

        class _Connection:
            def cursor(self):
                return _Cursor()

        assert await init_db.has_existing_risk_rules(_Connection()) is expected


class _ScalarResult:
    def __init__(self, scalar=None, row=None):
        self._scalar = scalar
        self._row = row

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def first(self):
        return self._row


class _FakeDB:
    def __init__(self, results):
        self.results = iter(results)

    async def execute(self, _statement):
        return next(self.results)


class TestBankEventValidation:
    def test_dispatch_table_maps_four_sources(self):
        assert {
            event: (spec.model, spec.field_name)
            for event, spec in validator._EVENT_SOURCE_VALIDATORS.items()
        } == {
            "登录": (LoginLog, "login_id"),
            "转账": (Transaction, "txn_id"),
            "贷款申请": (LoanApplication, "loan_id"),
            "绑卡": (BankCard, "card_id"),
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("event_type", ["登录", "贷款申请", "绑卡"])
    async def test_owned_source_is_accepted(self, event_type):
        request = RiskCheckRequest(
            event_type=event_type, source_id="SRC_DEMO_001", user_id="USR_DEMO_001"
        )
        db = _FakeDB([_ScalarResult(scalar="USR_DEMO_001")])
        await validator.ensure_source_matches_event_type(db, request)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("event_type", ["登录", "贷款申请", "绑卡"])
    async def test_horizontal_access_is_rejected(self, event_type):
        request = RiskCheckRequest(
            event_type=event_type, source_id="SRC_DEMO_001", user_id="USR_DEMO_001"
        )
        db = _FakeDB([_ScalarResult(scalar="USR_DEMO_999")])
        with pytest.raises(HTTPException) as exc_info:
            await validator.ensure_source_matches_event_type(db, request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("event_type", ["登录", "转账", "贷款申请", "绑卡"])
    async def test_wrong_source_type_returns_clear_4xx(self, event_type):
        request = RiskCheckRequest(
            event_type=event_type, source_id="WRONG_DEMO_001", user_id="USR_DEMO_001"
        )
        db = _FakeDB([_ScalarResult()])
        with pytest.raises(HTTPException) as exc_info:
            await validator.ensure_source_matches_event_type(db, request)
        assert exc_info.value.status_code == 400
        assert "不匹配" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_valid_transfer_checks_both_cards_and_owner(self):
        request = RiskCheckRequest(
            event_type="转账", source_id="TXN_DEMO_001", user_id="USR_DEMO_001"
        )
        row = type(
            "TransferRow",
            (),
            {
                "from_card": "CARD_DEMO_001",
                "to_card": "CARD_DEMO_002",
                "from_owner": "USR_DEMO_001",
                "from_active": True,
                "to_active": True,
            },
        )()
        await validator.ensure_source_matches_event_type(
            _FakeDB([_ScalarResult(row=row)]), request
        )

    @pytest.mark.asyncio
    async def test_transfer_with_inactive_recipient_card_is_rejected(self):
        request = RiskCheckRequest(
            event_type="转账", source_id="TXN_DEMO_001", user_id="USR_DEMO_001"
        )
        row = type(
            "TransferRow",
            (),
            {
                "from_card": "CARD_DEMO_001",
                "to_card": "CARD_DEMO_002",
                "from_owner": "USR_DEMO_001",
                "from_active": True,
                "to_active": False,
            },
        )()
        with pytest.raises(HTTPException) as exc_info:
            await validator.ensure_source_matches_event_type(
                _FakeDB([_ScalarResult(row=row)]), request
            )
        assert exc_info.value.status_code == 400
        assert "卡关系无效" in exc_info.value.detail
