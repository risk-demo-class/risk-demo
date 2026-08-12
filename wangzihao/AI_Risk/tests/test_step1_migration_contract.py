"""Step 1 制造业迁移核心兼容契约（纯静态、无需数据库）。

本文件只保护迁移边界，不验证制造业业务实现：
1. 九张核心风控表的 DDL 与 ORM 定义保持冻结；
2. 固定 25 维特征名称、顺序和 14/8/3 前缀分组；
3. process_event 四步与 run_risk_check 七步主流程顺序保持不变。
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


# 对文本统一换行并移除行尾空白，避免仅因 CRLF/LF 差异触发失败。
def _normalized_text(relative_path: str) -> str:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def _sha256(relative_path: str) -> str:
    return hashlib.sha256(_normalized_text(relative_path).encode("utf-8")).hexdigest()


# Step 1 迁移基线：任何生产变更都必须先显式更新兼容契约，而不能被行业迁移顺手修改。
FROZEN_FILE_SHA256 = {
    "app/models_risk.py": "1577ad054779319f65b240884b4c10cedaff972fc2502692e2f84a7ecca9d2f2",
    "sql/init_risk_tables.sql": "fdb3a9cc5d767d032de87bf4c5b337a01de125e96d3716f68296e849103a0875",
}


CORE_TABLE_COLUMNS = {
    "risk_rule": (
        "rule_id", "rule_name", "rule_category", "event_type", "rule_condition",
        "risk_level", "risk_score", "action", "is_enabled", "priority",
        "description", "create_time", "update_time", "deleted_at",
    ),
    "risk_event": (
        "event_id", "event_type", "event_source_id", "user_id", "event_data",
        "create_time",
    ),
    "risk_feature": (
        "feature_id", "event_id", "entity_type", "entity_id", "feature_name",
        "feature_value", "compute_time",
    ),
    "risk_assessment": (
        "assessment_id", "event_id", "user_id", "rule_results", "rule_count",
        "final_score", "risk_level", "decision", "ml_score", "ml_decision",
        "create_time",
    ),
    "risk_case": (
        "case_id", "assessment_id", "user_id", "case_status", "case_category",
        "risk_detail", "source_id", "event_type", "reviewer", "review_comment",
        "review_time", "create_time", "update_time",
    ),
    "risk_blacklist": (
        "blacklist_id", "blacklist_type", "blacklist_value", "reason",
        "expire_time", "create_time", "deleted_at",
    ),
    "risk_user_profile": (
        "user_id", "risk_score", "risk_level", "total_orders", "total_refunds",
        "refund_rate", "avg_order_amount", "address_count", "complaint_count",
        "assessment_count", "last_assessment_time", "profile_data", "update_time",
    ),
    "risk_action_log": (
        "log_id", "operator", "action_type", "target_type", "target_id",
        "before_value", "after_value", "ip", "remark", "create_time",
    ),
    "risk_alert": (
        "alert_id", "alert_type", "alert_level", "alert_title", "alert_content",
        "metric_name", "metric_value", "threshold", "status", "handler",
        "resolve_time", "create_time",
    ),
}


CORE_TABLE_INDEXES = {
    "risk_rule": (),
    "risk_event": ("idx_risk_event_user_id", "idx_risk_event_create_time"),
    "risk_feature": ("idx_risk_feature_event_id", "idx_risk_feature_entity"),
    "risk_assessment": (
        "idx_risk_assessment_user_id", "idx_risk_assessment_decision",
        "idx_risk_assessment_create_time",
    ),
    "risk_case": ("idx_risk_case_status", "idx_risk_case_user_id", "idx_risk_case_source_id"),
    "risk_blacklist": ("idx_blacklist_type_value",),
    "risk_user_profile": (),
    "risk_action_log": (
        "idx_action_log_operator", "idx_action_log_target", "idx_action_log_create_time",
    ),
    "risk_alert": ("idx_alert_status", "idx_alert_level", "idx_alert_create_time"),
}


FEATURE_COLUMNS_BASELINE = [
    "user_total_orders", "user_orders_30d", "user_orders_7d", "user_total_amount",
    "user_avg_order_amount", "user_max_order_amount", "user_refund_count",
    "user_postsale_count", "user_refund_rate", "user_postsale_rate",
    "user_refund_amount", "user_cancel_count", "user_complaint_count",
    "user_address_count", "order_total_amount", "order_item_count",
    "order_sku_count", "order_discount_amount", "order_discount_rate",
    "order_pay_interval_sec", "order_is_night", "order_category_count",
    "addr_total_count", "addr_province_count", "addr_is_new",
]


def _table_ddl(sql: str, table: str) -> str:
    pattern = rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`{table}`\s*\((.*?)\)\s*ENGINE="
    match = re.search(pattern, sql, flags=re.IGNORECASE | re.DOTALL)
    assert match, f"未找到核心表 DDL: {table}"
    return match.group(1)


def _ddl_columns(ddl: str) -> tuple[str, ...]:
    return tuple(re.findall(r"^\s*`([^`]+)`\s+", ddl, flags=re.MULTILINE))


def _ddl_indexes(ddl: str) -> tuple[str, ...]:
    names = re.findall(
        r"^\s*(?:UNIQUE\s+)?INDEX\s+`([^`]+)`",
        ddl,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return tuple(names)


def _module_tree(relative_path: str) -> ast.Module:
    return ast.parse(_normalized_text(relative_path), filename=relative_path)


def _find_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"未找到异步函数: {name}")


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _relevant_calls(function: ast.AsyncFunctionDef, expected: list[str]) -> list[str]:
    calls = sorted(
        (node for node in ast.walk(function) if isinstance(node, ast.Call)),
        key=lambda node: (node.lineno, node.col_offset),
    )
    expected_set = set(expected)
    return [_call_name(call) for call in calls if _call_name(call) in expected_set]


def test_core_risk_files_match_step1_baseline():
    """冻结核心 ORM 与 DDL；字段类型、ENUM、索引和约束不能静默漂移。"""
    actual = {path: _sha256(path) for path in FROZEN_FILE_SHA256}
    assert actual == FROZEN_FILE_SHA256


def test_all_nine_core_tables_and_columns_are_frozen():
    sql = _normalized_text("sql/init_risk_tables.sql")
    assert tuple(CORE_TABLE_COLUMNS) == (
        "risk_rule", "risk_event", "risk_feature", "risk_assessment", "risk_case",
        "risk_blacklist", "risk_user_profile", "risk_action_log", "risk_alert",
    )
    for table, expected_columns in CORE_TABLE_COLUMNS.items():
        assert _ddl_columns(_table_ddl(sql, table)) == expected_columns


def test_all_core_named_indexes_are_frozen():
    sql = _normalized_text("sql/init_risk_tables.sql")
    for table, expected_indexes in CORE_TABLE_INDEXES.items():
        assert _ddl_indexes(_table_ddl(sql, table)) == expected_indexes


def test_feature_columns_keep_exact_25_dim_contract():
    tree = _module_tree("app/engine/ml_model.py")
    assignment = next(
        node for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "FEATURE_COLUMNS"
    )
    actual = ast.literal_eval(assignment.value)
    assert actual == FEATURE_COLUMNS_BASELINE
    assert len(actual) == 25
    assert sum(name.startswith("user_") for name in actual) == 14
    assert sum(name.startswith("order_") for name in actual) == 8
    assert sum(name.startswith("addr_") for name in actual) == 3


def test_process_event_keeps_four_step_order():
    function = _find_function(_module_tree("app/service/event.py"), "process_event")
    expected = [
        "validate_risk_check_request",
        "_enrich_request",
        "_check_all_blacklists",
        "run_risk_check",
    ]
    assert _relevant_calls(function, expected) == expected


def test_run_risk_check_keeps_seven_stage_order():
    function = _find_function(_module_tree("app/engine/decision.py"), "run_risk_check")
    expected = [
        "_build_context",
        "_enrich_receive_id",
        "_create_event_record",
        "_compute_features",
        "_save_feature_snapshot",
        "_evaluate_rules",
        "_calculate_decision",
        "flush",
        "_save_assessment",
        "_maybe_create_case",
        "_update_user_profile",
        "commit",
        "_build_response",
    ]
    assert _relevant_calls(function, expected) == expected
