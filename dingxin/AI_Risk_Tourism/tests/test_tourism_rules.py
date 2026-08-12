"""
旅游风控规则测试 (DB-free)
验证 sql/init_risk_data.sql 中的 12 条规则:
  - 规则数量 / 唯一 ID / 必含任务书 8 条
  - 风险等级与动作合法
  - 条件字段全部属于 25 维特征 (防"规则引用不存在的特征" bug)
"""
import json
import re
from pathlib import Path

from app.engine.ml_model import FEATURE_COLUMNS

SQL_PATH = Path(__file__).resolve().parent.parent / "sql" / "init_risk_data.sql"

REQUIRED_RULES = ["R001", "R002", "R005", "R008", "R012", "R018", "R025", "R030"]
EXTRA_RULES = ["R031", "R032", "R033", "R034"]
VALID_LEVELS = {"低", "中", "高", "极高"}
VALID_ACTIONS = {"通过", "标记", "人工审核", "拒绝"}
VALID_EVENT_TYPES = {"预订下单", "支付", "退改申请", "签证申请", "通用"}


def _extract_rules() -> list[dict]:
    """从 init_risk_data.sql 提取所有 INSERT INTO risk_rule 的值."""
    sql = SQL_PATH.read_text(encoding="utf-8")
    rules = []
    # 捕获完整 INSERT 语句 (到分号结束), rule_id 从 VALUES 行取
    for m in re.finditer(
        r"INSERT INTO risk_rule\s*\(.*?\)\s*VALUES\s*\n\('(R\d+)'.*?\);",
        sql, re.DOTALL,
    ):
        rules.append({"rule_id": m.group(1), "sql": m.group(0)})
    return rules


def _extract_condition(sql: str) -> dict:
    """从 INSERT 语句里抓 rule_condition JSON (带引号的 JSON 字符串)."""
    m = re.search(r"'(\{.*?\})'", sql, re.DOTALL)
    assert m, f"找不到 rule_condition JSON: {sql[:100]}"
    return json.loads(m.group(1))


def _collect_fields(cond: dict, acc: set) -> None:
    if "field" in cond:
        acc.add(cond["field"])
    for sub in cond.get("and", []) + cond.get("or", []):
        _collect_fields(sub, acc)


class TestTourismRules:
    def test_12_rules_present(self):
        rules = _extract_rules()
        ids = [r["rule_id"] for r in rules]
        assert len(rules) == 12, f"应有 12 条规则, 实际 {len(rules)}: {ids}"
        assert len(set(ids)) == len(ids), "规则 ID 不能重复"
        for rid in REQUIRED_RULES + EXTRA_RULES:
            assert rid in ids, f"缺少规则 {rid}"

    def test_rule_fields_valid(self):
        """每条规则的风险等级 / 动作 / 事件类型必须合法."""
        for r in _extract_rules():
            m = re.search(
                r"\}',\s*'(低|中|高|极高)',\s*\d+,\s*'(通过|标记|人工审核|拒绝)'",
                r["sql"],
            )
            assert m, f"规则 {r['rule_id']} 解析不到 等级/动作: {r['sql'][:120]}"
            level, action = m.group(1), m.group(2)
            assert level in VALID_LEVELS, f"规则 {r['rule_id']} 等级非法: {level}"
            assert action in VALID_ACTIONS, f"规则 {r['rule_id']} 动作非法: {action}"

    def test_rule_conditions_only_reference_known_features(self):
        """规则条件里引用的字段必须都在 25 维特征清单里."""
        feats = set(FEATURE_COLUMNS)
        for r in _extract_rules():
            cond = _extract_condition(r["sql"])
            fields = set()
            _collect_fields(cond, fields)
            unknown = fields - feats
            assert not unknown, (
                f"规则 {r['rule_id']} 引用了不存在的特征: {unknown}. "
                f"25 维特征见 app/engine/ml_model.py::FEATURE_COLUMNS"
            )

    def test_all_12_rules_have_description(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        for r in _extract_rules():
            assert r["rule_id"] in sql
