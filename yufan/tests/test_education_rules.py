"""阶段 9：教育行业规则 SQL 静态一致性测试。"""

import json
import re
from pathlib import Path

from app.engine.ml_model import FEATURE_COLUMNS


SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "init_risk_data.sql"
SQL = SQL_PATH.read_text(encoding="utf-8")


def _condition_fields(condition):
    if "field" in condition:
        return {condition["field"]}
    fields = set()
    for key in ("and", "or"):
        for child in condition.get(key, []):
            fields.update(_condition_fields(child))
    return fields


def test_has_twelve_unique_education_rules():
    ids = re.findall(r"\('(EDU\d{3})'", SQL)
    assert len(ids) == 12
    assert len(set(ids)) == 12


def test_rules_use_common_event_for_core_enum_compatibility():
    assert SQL.count("'通用'") == 12
    for old_event in ("'下单'", "'支付'", "'售后申请'", "'物流投诉'"):
        assert old_event not in SQL


def test_every_rule_condition_uses_a_known_feature():
    conditions = re.findall(r"\n\s*'(\{.*?\})',\n\s*'(?:低|中|高|极高)'", SQL)
    assert len(conditions) == 12
    for raw in conditions:
        fields = _condition_fields(json.loads(raw))
        assert fields
        assert fields.issubset(FEATURE_COLUMNS)


def test_rules_cover_required_education_risks():
    for phrase in ("课程报名", "退费", "设备", "直播打赏", "代理学习"):
        assert phrase in SQL
