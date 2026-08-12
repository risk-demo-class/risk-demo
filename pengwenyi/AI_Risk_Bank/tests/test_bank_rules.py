"""
【银行版】测试 - 12 条预置规则 (sql/init_risk_data.sql)

验证:
  1. 12 条规则 ID/名称/类别/场景/等级/动作 齐全 (4 大场景 + 通用)
  2. 每条规则的条件字段都在 48 维 FEATURE_COLUMNS 中 (特征对齐)
  3. 每条规则有"命中示例"与"未命中示例" (evaluate_condition 纯函数求值)
  4. 每条规则含行业有效性说明 description
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SQL_PATH = ROOT / "sql" / "init_risk_data.sql"

from app.engine.ml_model import FEATURE_COLUMNS  # noqa: E402
from app.engine.rule import evaluate_condition  # noqa: E402

# 规则 ID → (名称, 类别, 事件场景, 等级, 分数, 动作)
EXPECTED_RULES = {
    "R001": ("异地大额转账", "交易风险", "转账", "极高", 92, "拒绝"),
    "R002": ("凌晨密集操作", "交易风险", "转账", "高", 68, "人工审核"),
    "R003": ("深夜异常登录", "账户风险", "登录", "高", 65, "人工审核"),
    "R005": ("新设备信用卡大额", "设备风险", "信用卡", "高", 84, "人工审核"),
    "R008": ("多卡归集", "交易风险", "转账", "极高", 90, "拒绝"),
    "R010": ("高负债大额申贷", "信贷风险", "贷款申请", "高", 85, "人工审核"),
    "R012": ("信贷申请突击", "信贷风险", "贷款申请", "高", 80, "人工审核"),
    "R015": ("低信用分大额交易", "账户风险", "转账", "高", 82, "人工审核"),
    "R018": ("设备多人共用", "设备风险", "通用", "中", 42, "标记"),
    "R020": ("登录异常后大额转账", "网络风险", "转账", "高", 80, "人工审核"),
    "R025": ("IP 代理/秒拨", "网络风险", "通用", "中", 40, "标记"),
    "R030": ("黑卡拦截", "交易风险", "转账", "极高", 95, "拒绝"),
}

# 每条规则的"命中示例"特征 (构造边界值, 保证命中)
HIT_FEATURES = {
    "R001": {"txn_city_match": 1, "txn_amount": 60000},
    "R002": {"txn_is_night": 1, "txn_1h_count": 4},
    "R003": {"login_is_night": 1, "user_failed_login_7d": 4},
    "R005": {"card_device_new": 1, "card_amount": 35000},
    "R008": {"txn_1h_into_count": 4},
    "R010": {"loan_debt_ratio": 0.7, "loan_amount_income_ratio": 6},
    "R012": {"loan_month_count": 4},
    "R015": {"user_credit_score": 450, "txn_amount": 25000},
    "R018": {"txn_device_user_count": 6},
    "R020": {"user_failed_login_7d": 4, "txn_amount": 15000},
    "R025": {"txn_geo_risk": 1},
    "R030": {"txn_to_card_black": 1},
}

# 每条规则的"未命中示例" (只改 1 个关键字段, 保证不命中)
MISS_FEATURES = {
    "R001": {"txn_city_match": 0, "txn_amount": 60000},      # 非异地
    "R002": {"txn_is_night": 0, "txn_1h_count": 5},          # 非夜间
    "R003": {"login_is_night": 1, "user_failed_login_7d": 2},  # 失败次数不足
    "R005": {"card_device_new": 0, "card_amount": 35000},    # 非新设备
    "R008": {"txn_1h_into_count": 2},                        # 不足 3 卡
    "R010": {"loan_debt_ratio": 0.5, "loan_amount_income_ratio": 6},  # 负债率不足
    "R012": {"loan_month_count": 2},                         # 不足 3 次
    "R015": {"user_credit_score": 550, "txn_amount": 25000},  # 信用分不低
    "R018": {"txn_device_user_count": 3},                    # 不足 5 人
    "R020": {"user_failed_login_7d": 1, "txn_amount": 15000},  # 失败次数不足
    "R025": {"txn_geo_risk": 0},                             # 非代理 IP
    "R030": {"txn_to_card_black": 0},                        # 非黑卡
}

_RE_BLOCK = re.compile(r"INSERT INTO risk_rule.*?;", re.S)
_RE_RULE = re.compile(
    r"\('(R\d{3})', '([^']+)', '([^']+)', '([^']+)',\s*"
    r"'(.+?)',\s*'(极高|高|中)', (\d+), '(拒绝|人工审核|标记)', 1, (\d+),\s*'([^']*)'\)"
)


def _parse_rules() -> dict:
    """从 SQL 解析全部规则 → {rule_id: {字段...}}."""
    sql = SQL_PATH.read_text(encoding="utf-8")
    rules = {}
    for block in _RE_BLOCK.findall(sql):
        m = _RE_RULE.search(block)
        assert m, f"无法解析规则块: {block[:120]}"
        rid, name, cat, evt, cond, level, score, action, priority, desc = m.groups()
        rules[rid] = dict(
            rule_name=name, rule_category=cat, event_type=evt,
            condition=json.loads(cond), risk_level=level, risk_score=int(score),
            action=action, priority=int(priority), description=desc,
        )
    return rules


def _collect_fields(cond: dict) -> list:
    """递归收集条件表达式里用到的所有特征字段."""
    if "and" in cond:
        return [f for sub in cond["and"] for f in _collect_fields(sub)]
    if "or" in cond:
        return [f for sub in cond["or"] for f in _collect_fields(sub)]
    return [cond["field"]]


@pytest.fixture(scope="module")
def rules():
    return _parse_rules()


class TestTwelveRulesPresent:
    """12 条规则齐全, 元数据与计划表一致."""

    def test_all_12_rules_present(self, rules):
        assert set(rules.keys()) == set(EXPECTED_RULES.keys()), (
            f"规则 ID 不齐: 缺 {set(EXPECTED_RULES) - set(rules)}, "
            f"多 {set(rules) - set(EXPECTED_RULES)}"
        )

    def test_rule_metadata_matches_plan(self, rules):
        for rid, (name, cat, evt, level, score, action) in EXPECTED_RULES.items():
            r = rules[rid]
            assert r["rule_name"] == name, f"{rid} 名称"
            assert r["rule_category"] == cat, f"{rid} 类别"
            assert r["event_type"] == evt, f"{rid} 场景"
            assert r["risk_level"] == level, f"{rid} 等级"
            assert r["risk_score"] == score, f"{rid} 分数"
            assert r["action"] == action, f"{rid} 动作"

    def test_user_specified_8_rules_included(self, rules):
        """用户指定的 8 条规则必须全部在内."""
        for rid in ("R001", "R002", "R005", "R008", "R012", "R018", "R025", "R030"):
            assert rid in rules, f"缺少用户指定规则 {rid}"

    def test_covers_four_bank_scenarios(self, rules):
        """4 大场景全覆盖: 转账/登录/贷款申请/信用卡 (+ 通用)."""
        events = {r["event_type"] for r in rules.values()}
        assert {"转账", "登录", "贷款申请", "信用卡", "通用"} <= events

    def test_every_rule_has_industry_description(self, rules):
        """每条规则必须有行业有效性说明 (description 非空)."""
        for rid, r in rules.items():
            assert r["description"] and len(r["description"]) >= 20, (
                f"{rid} 缺少行业有效性说明"
            )


class TestRuleConditionAlignment:
    """规则条件字段与 48 维特征对齐."""

    def test_condition_json_parses(self, rules):
        for rid, r in rules.items():
            assert isinstance(r["condition"], dict), f"{rid} 条件 JSON 解析失败"
            assert r["condition"], f"{rid} 条件不能为空"

    def test_all_fields_in_feature_columns(self, rules):
        """条件里的每个字段都必须是 48 维 FEATURE_COLUMNS 之一."""
        feature_set = set(FEATURE_COLUMNS)
        assert len(FEATURE_COLUMNS) == 48
        for rid, r in rules.items():
            for field in _collect_fields(r["condition"]):
                assert field in feature_set, (
                    f"{rid} 条件字段 '{field}' 不在 48 维特征中"
                )

    def test_rule_fields_match_event_subset(self, rules):
        """转账/登录/贷款/信用卡 事件的特征前缀与规则事件对应."""
        # 转账规则只能引用 user_*/txn_* 前缀
        txn_rules = [r for r in rules.values() if r["event_type"] == "转账"]
        for r in txn_rules:
            for field in _collect_fields(r["condition"]):
                assert field.startswith(("user_", "txn_")), (
                    f"转账规则引用了非转账特征: {field}"
                )
        # 登录规则只能引用 user_*/login_* 前缀
        login_rules = [r for r in rules.values() if r["event_type"] == "登录"]
        for r in login_rules:
            for field in _collect_fields(r["condition"]):
                assert field.startswith(("user_", "login_")), (
                    f"登录规则引用了非登录特征: {field}"
                )


class TestRuleHitExamples:
    """每条规则都有可讲清的命中示例与未命中示例."""

    def test_hit_examples(self, rules):
        """构造特征 → 规则必须命中."""
        for rid, features in HIT_FEATURES.items():
            assert evaluate_condition(rules[rid]["condition"], features), (
                f"{rid} 命中示例未命中: {features}"
            )

    def test_miss_examples(self, rules):
        """边界反例 → 规则必须不命中."""
        for rid, features in MISS_FEATURES.items():
            assert not evaluate_condition(rules[rid]["condition"], features), (
                f"{rid} 未命中示例却命中了: {features}"
            )

    def test_high_risk_rules_veto_or_review(self, rules):
        """极高等级规则必须拒绝 (一票否决), 高等级人工审核."""
        for rid, r in rules.items():
            if r["risk_level"] == "极高":
                assert r["action"] == "拒绝", f"{rid} 极高应拒绝"
            elif r["risk_level"] == "高":
                assert r["action"] == "人工审核", f"{rid} 高应人工审核"
            else:
                assert r["action"] == "标记", f"{rid} 中应标记"
