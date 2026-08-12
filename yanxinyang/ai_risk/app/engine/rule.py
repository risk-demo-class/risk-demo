# -*- coding: utf-8 -*-
"""规则引擎 —— 对应教学宝典《第 6 章：规则引擎》

🛂 类比：安检员（死板但精准）—— 拿着"违禁品清单"（30 条规则）逐项比对。

三个关键设计（宝典 6.3）：
    1. unknown field = 不命中：特征算不出来返回 False，**不抛异常、不阻塞**
    2. 按 priority 降序：load_enabled_rules 排序 priority DESC —— 优先级高的先匹配
    3. event_type 限定：只加载该类型 + 通用规则 —— 提升匹配效率
    4. 软删过滤：WHERE deleted_at IS NULL（2026-08-07 加）
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("ai_risk.engine.rule")

Features = Dict[str, float]


# ====================================================================== 14 种 op
def _num(value: Any) -> Optional[float]:
    """安全转数值；转不了返回 None（→ 不命中）。"""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _cmp(op: str) -> Callable[[Any, Any], bool]:
    table = {
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
    }
    func = table[op]

    def run(left: Any, right: Any) -> bool:
        a, b = _num(left), _num(right)
        if a is None or b is None:
            return False
        return func(a, b)

    return run


def _op_eq(left: Any, right: Any) -> bool:
    a, b = _num(left), _num(right)
    if a is not None and b is not None:
        return abs(a - b) < 1e-9
    return str(left) == str(right)


def _op_ne(left: Any, right: Any) -> bool:
    return not _op_eq(left, right)


def _op_in(left: Any, right: Any) -> bool:
    if not isinstance(right, (list, tuple, set)):
        return False
    return any(_op_eq(left, item) for item in right)


def _op_not_in(left: Any, right: Any) -> bool:
    if not isinstance(right, (list, tuple, set)):
        return False
    return not _op_in(left, right)


def _op_between(left: Any, right: Any) -> bool:
    """区间（含两端）。"""
    if not isinstance(right, (list, tuple)) or len(right) != 2:
        return False
    value, low, high = _num(left), _num(right[0]), _num(right[1])
    if value is None or low is None or high is None:
        return False
    if low > high:
        low, high = high, low
    return low <= value <= high


def _op_not_between(left: Any, right: Any) -> bool:
    if not isinstance(right, (list, tuple)) or len(right) != 2:
        return False
    return not _op_between(left, right)


def _op_exists(left: Any, right: Any) -> bool:
    """字段存在且非空（right=True 要求存在，False 要求不存在）。"""
    present = left is not None
    expect = True if right is None else bool(right)
    return present is expect


#: 14 种运算符（宝典 1.3「14 种 op」）。
#: 宝典 6.1 表格列出 11 个基础 op，本实现在其基础上补齐 3 个逻辑完备算子
#: （not_between / not / exists），凑齐 14 种并保持语义一致。
COMPARE_OPS: Dict[str, Callable[[Any, Any], bool]] = {
    ">": _cmp(">"), ">=": _cmp(">="), "<": _cmp("<"), "<=": _cmp("<="),
    "==": _op_eq, "!=": _op_ne,
    "in": _op_in, "not_in": _op_not_in,
    "between": _op_between, "not_between": _op_not_between,
    "exists": _op_exists,
}
LOGIC_OPS: Tuple[str, ...] = ("and", "or", "not")
ALL_OPS: Tuple[str, ...] = tuple(COMPARE_OPS) + LOGIC_OPS
OP_COUNT = len(ALL_OPS)          # == 14

OP_DOC: List[Dict[str, str]] = [
    {"op": ">", "kind": "比较", "desc": "大于", "example": '{"field":"order_total_amount","op":">","value":5000}'},
    {"op": ">=", "kind": "比较", "desc": "大于等于", "example": '{"field":"user_refund_rate","op":">=","value":0.5}'},
    {"op": "<", "kind": "比较", "desc": "小于", "example": '{"field":"user_total_orders","op":"<","value":1}'},
    {"op": "<=", "kind": "比较", "desc": "小于等于", "example": '{"field":"user_avg_order_amount","op":"<=","value":500}'},
    {"op": "==", "kind": "等值", "desc": "等于", "example": '{"field":"addr_is_new","op":"==","value":1}'},
    {"op": "!=", "kind": "等值", "desc": "不等于", "example": '{"field":"order_is_night","op":"!=","value":0}'},
    {"op": "in", "kind": "集合", "desc": "在列表中", "example": '{"field":"order_is_night","op":"in","value":[1]}'},
    {"op": "not_in", "kind": "集合", "desc": "不在列表中", "example": '{"field":"order_sku_count","op":"not_in","value":[1,2]}'},
    {"op": "between", "kind": "区间", "desc": "区间（含两端）", "example": '{"field":"order_pay_interval","op":"between","value":[0,3]}'},
    {"op": "not_between", "kind": "区间", "desc": "区间外", "example": '{"field":"order_discount_rate","op":"not_between","value":[0,0.3]}'},
    {"op": "exists", "kind": "存在", "desc": "字段是否存在", "example": '{"field":"order_total_amount","op":"exists","value":true}'},
    {"op": "and", "kind": "逻辑", "desc": "与（递归）", "example": '{"and":[{...},{...}]}'},
    {"op": "or", "kind": "逻辑", "desc": "或（递归）", "example": '{"or":[{...},{...}]}'},
    {"op": "not", "kind": "逻辑", "desc": "非（递归）", "example": '{"not":{...}}'},
]


# ====================================================================== 条件求值
def evaluate(condition: Any, features: Features) -> bool:
    """JSON 条件表达式求值（宝典 6.2 关键代码 1）。

    支持三种形态：
        单条：  {"field": ..., "op": ..., "value": ...}
        嵌套：  {"and": [...]} / {"or": [...]} / {"not": {...}}
        兜底：  未知 op / 未知 field → False（**不抛异常**，防脏数据炸流程）
    """
    ok, _ = evaluate_with_trace(condition, features)
    return ok


def evaluate_with_trace(condition: Any, features: Features,
                        depth: int = 0) -> Tuple[bool, List[Dict[str, Any]]]:
    """带求值轨迹的版本 —— 前端「规则测试器」用它展示每一步为什么命中/不命中。"""
    trace: List[Dict[str, Any]] = []
    if not isinstance(condition, dict) or depth > 10:
        trace.append({"depth": depth, "node": "非法条件", "result": False,
                      "note": "条件必须是 dict 且嵌套深度 ≤ 10"})
        return False, trace

    # ---------------- 逻辑节点（递归） ----------------
    for logic in ("and", "or"):
        if logic in condition:
            children = condition[logic]
            if not isinstance(children, list) or not children:
                trace.append({"depth": depth, "node": logic, "result": False,
                              "note": f"{logic} 的值必须是非空数组"})
                return False, trace
            results: List[bool] = []
            for child in children:
                ok, sub = evaluate_with_trace(child, features, depth + 1)
                results.append(ok)
                trace.extend(sub)
            final = all(results) if logic == "and" else any(results)
            trace.append({"depth": depth, "node": logic.upper(), "result": final,
                          "note": f"子条件结果 {results}"})
            return final, trace

    if "not" in condition:
        ok, sub = evaluate_with_trace(condition["not"], features, depth + 1)
        trace.extend(sub)
        trace.append({"depth": depth, "node": "NOT", "result": not ok, "note": f"取反 {ok}"})
        return (not ok), trace

    # ---------------- 叶子节点 ----------------
    field = condition.get("field")
    op = condition.get("op")
    expect = condition.get("value")

    if not field or op is None:
        trace.append({"depth": depth, "node": "叶子", "result": False,
                      "note": "缺少 field 或 op"})
        return False, trace

    if op not in COMPARE_OPS:
        # 宝典 6.1：未知 op 兜底返回 False（不抛异常）
        logger.warning("未知运算符 op=%s，按不命中处理", op)
        trace.append({"depth": depth, "node": f"{field} {op}", "result": False,
                      "note": f"未知 op={op}，兜底不命中"})
        return False, trace

    if field not in features and op != "exists":
        # 宝典 6.3：unknown field = 不命中
        trace.append({"depth": depth, "node": f"{field} {op} {expect}", "result": False,
                      "note": f"特征 {field} 不存在，兜底不命中"})
        return False, trace

    actual = features.get(field)
    result = COMPARE_OPS[op](actual, expect)
    trace.append({"depth": depth, "node": f"{field} {op} {expect}", "result": result,
                  "note": f"实际值 = {actual}"})
    return result, trace


def parse_condition(raw: Any) -> Dict[str, Any]:
    """rule_condition 字段（TEXT）→ dict。非法 JSON 返回空 dict（不命中）。"""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        logger.warning("规则条件不是合法 JSON，按不命中处理: %s", raw)
        return {}


def validate_condition(condition: Any, depth: int = 0) -> List[str]:
    """规则新增/修改时的条件静态校验，返回错误列表（空 = 合法）。"""
    errors: List[str] = []
    if depth > 10:
        return ["嵌套深度超过 10 层"]
    if not isinstance(condition, dict) or not condition:
        return ["条件必须是非空 JSON 对象"]
    logic_keys = [k for k in ("and", "or", "not") if k in condition]
    if logic_keys:
        key = logic_keys[0]
        children = condition[key]
        if key == "not":
            return validate_condition(children, depth + 1)
        if not isinstance(children, list) or not children:
            return [f"{key} 的值必须是非空数组"]
        for child in children:
            errors.extend(validate_condition(child, depth + 1))
        return errors
    if "field" not in condition:
        errors.append("叶子条件缺少 field")
    if "op" not in condition:
        errors.append("叶子条件缺少 op")
    elif condition["op"] not in COMPARE_OPS:
        errors.append(f"不支持的 op: {condition['op']}（支持 {', '.join(COMPARE_OPS)}）")
    else:
        op, value = condition["op"], condition.get("value")
        if op in ("in", "not_in") and not isinstance(value, list):
            errors.append(f"op={op} 的 value 必须是数组")
        if op in ("between", "not_between") and (not isinstance(value, list) or len(value) != 2):
            errors.append(f"op={op} 的 value 必须是长度为 2 的数组")
    return errors


# ====================================================================== 规则加载
def load_enabled_rules(db: Any, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """加载启用中的规则。

    · is_enabled = 1
    · deleted_at IS NULL          —— 软删过滤（宝典 6.3）
    · event_type 限定 + 通用规则   —— 只加载该类型 + event_type 为空的通用规则
    · ORDER BY priority DESC      —— 优先级高的先匹配
    """
    sql = ("SELECT * FROM risk_rule WHERE is_enabled = 1 AND deleted_at IS NULL")
    params: List[Any] = []
    if event_type:
        sql += " AND (event_type = ? OR event_type IS NULL OR event_type = '')"
        params.append(event_type)
    sql += " ORDER BY priority DESC, rule_id ASC"
    rules = db.fetch_all(sql, params)
    for rule in rules:
        rule["condition_obj"] = parse_condition(rule.get("rule_condition"))
    logger.debug("加载启用规则 %d 条（event_type=%s）", len(rules), event_type)
    return rules


def match(rules: List[Dict[str, Any]], features: Features,
          with_trace: bool = False) -> List[Dict[str, Any]]:
    """逐条匹配，返回命中列表 hits（按 priority 降序，与加载顺序一致）。"""
    hits: List[Dict[str, Any]] = []
    for rule in rules:
        condition = rule.get("condition_obj") or parse_condition(rule.get("rule_condition"))
        try:
            ok, trace = evaluate_with_trace(condition, features)
        except Exception:  # noqa: BLE001  —— 绝不让单条规则炸掉整个流程
            logger.exception("规则 %s 求值异常，按不命中处理", rule.get("rule_id"))
            continue
        if not ok:
            continue
        hit = {
            "rule_id": rule["rule_id"],
            "rule_name": rule["rule_name"],
            "rule_category": rule.get("rule_category"),
            "risk_level": rule.get("risk_level"),
            "risk_score": int(rule.get("risk_score") or 0),
            "action": rule.get("action"),
            "priority": int(rule.get("priority") or 0),
            "condition": condition,
            "description": rule.get("description"),
        }
        if with_trace:
            hit["trace"] = trace
        hits.append(hit)
    return hits


def match_rules(db: Any, features: Features, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """便捷入口：加载 + 匹配。"""
    return match(load_enabled_rules(db, event_type), features)
