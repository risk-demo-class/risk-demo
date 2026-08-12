"""制造业风险数据生成器 source_id 与事件来源映射回归测试。

旧版测试绑定已删除的电商 forced picker。迁移后保护同一关键目标：生成器只能
使用业务表真实主键，且必须与 validator 的三类制造业来源一致。
"""

import inspect
from pathlib import Path

from app.service import validator
from scripts import gen_risk_data


ROOT = Path(__file__).resolve().parent.parent
DDL = (ROOT / "sql" / "init_business_tables.sql").read_text(encoding="utf-8")


class TestManufacturingSourceIds:
    def test_generator_collects_all_three_real_source_tables(self):
        src = inspect.getsource(gen_risk_data._collect_sources)
        assert "PurchaseOrder.po_id" in src
        assert "WarrantyClaim.claim_id" in src
        assert "cross_region_report" in src
        assert "report_id" in src

    def test_generator_uses_frozen_internal_event_codes(self):
        src = inspect.getsource(gen_risk_data._collect_sources)
        assert '"下单"' in src
        assert '"支付"' in src
        assert '"售后申请"' in src
        assert '"物流投诉"' in src

    def test_source_primary_keys_match_six_table_ddl(self):
        assert "`po_id` VARCHAR(50) NOT NULL" in DDL
        assert "`claim_id` VARCHAR(50) NOT NULL" in DDL
        assert "`report_id` VARCHAR(50) NOT NULL" in DDL
        assert "logistics_complaints_record" not in DDL

    def test_validator_dispatches_without_legacy_integer_cast(self):
        src = inspect.getsource(validator.ensure_source_matches_event_type)
        assert '"purchase_order"' in src
        assert '"warranty_claim"' in src
        assert '"cross_region_report"' in src
        assert "cast_value=int" not in inspect.getsource(validator)
