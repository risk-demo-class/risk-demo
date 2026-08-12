"""
业务枚举一致性测试 (DB-free)
保证 config.py 集中定义的业务枚举, 与 schemas.py 的 Pydantic Literal / ORM 枚举一致.
"""
import typing

from app.config import (
    BUSINESS_BLACKLIST_TYPES,
    BUSINESS_EVENT_TYPES,
    BUSINESS_RULE_CATEGORIES,
)
from app.models_risk import RiskBlacklist, RiskCase, RiskEvent, RiskRule
from app.schemas import BlacklistCreate, RiskCheckRequest, RuleCreate, RuleUpdate


def _literal_values(annotation) -> set:
    """提取 Literal / Optional[Literal] 的字面值集合."""
    out = []
    for a in typing.get_args(annotation):
        if a is type(None):
            continue
        if typing.get_origin(a) is typing.Literal:
            out.extend(typing.get_args(a))
        else:
            out.append(a)
    return set(out)


class TestBusinessEventTypes:
    def test_request_literal_matches_config(self):
        vals = _literal_values(RiskCheckRequest.model_fields["event_type"].annotation)
        assert vals == set(BUSINESS_EVENT_TYPES)

    def test_rule_literals_match_config(self):
        create_vals = _literal_values(RuleCreate.model_fields["event_type"].annotation)
        update_vals = _literal_values(RuleUpdate.model_fields["event_type"].annotation)
        assert create_vals == set(BUSINESS_EVENT_TYPES) | {"通用"}
        assert update_vals == set(BUSINESS_EVENT_TYPES) | {"通用"}

    def test_orm_enums_contain_tourism_values(self):
        for col in (
            RiskRule.__table__.c.event_type,
            RiskEvent.__table__.c.event_type,
            RiskCase.__table__.c.event_type,
        ):
            assert set(BUSINESS_EVENT_TYPES) <= set(col.type.enums), f"{col} 缺旅游事件枚举"


class TestBlacklistTypes:
    def test_create_literal_matches_config(self):
        vals = _literal_values(BlacklistCreate.model_fields["blacklist_type"].annotation)
        assert vals == set(BUSINESS_BLACKLIST_TYPES)

    def test_orm_enum_contains_tourism_values(self):
        col = RiskBlacklist.__table__.c.blacklist_type
        assert set(BUSINESS_BLACKLIST_TYPES) <= set(col.type.enums)


class TestRuleCategories:
    def test_rule_literals_match_config(self):
        create_vals = _literal_values(RuleCreate.model_fields["rule_category"].annotation)
        update_vals = _literal_values(RuleUpdate.model_fields["rule_category"].annotation)
        assert create_vals == set(BUSINESS_RULE_CATEGORIES)
        assert update_vals == set(BUSINESS_RULE_CATEGORIES)

    def test_orm_enum_contains_tourism_values(self):
        col = RiskRule.__table__.c.rule_category
        assert set(BUSINESS_RULE_CATEGORIES) <= set(col.type.enums)
