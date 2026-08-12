# -*- coding: utf-8 -*-
"""30 条预置规则 —— 对应教学宝典 1.3「30 条预置规则 / 6 大类风险」

6 大类（教育风控）：学术诚信 / 学习行为 / 账号安全 / 成绩异常 / 设备风险 / 身份风险
字段与 risk_rule 表完全一致；rule_condition 为 JSON 条件表达式（宝典 6.2）。

设计要点：
    · priority 降序匹配（宝典 6.3）—— 越危险的规则优先级越高
    · risk_level = "极高" 的规则触发**一票否决**（宝典 8.1 Step 4）
    · event_type 为空字符串表示**通用规则**（任何事件都加载）
    · R030 与宝典 6.2 的 AND 嵌套示例逐字一致
"""
from __future__ import annotations

import json
from typing import Any, Dict, List


def _rule(rule_id: str, name: str, category: str, event_type: str, condition: Dict[str, Any],
          level: str, score: int, action: str, priority: int, desc: str) -> Dict[str, Any]:
    return {
        "rule_id": rule_id,
        "rule_name": name,
        "rule_category": category,
        "event_type": event_type,
        "rule_condition": json.dumps(condition, ensure_ascii=False),
        "risk_level": level,
        "risk_score": score,
        "action": action,
        "is_enabled": 1,
        "priority": priority,
        "description": desc,
        "hit_count": 0,
    }


PRESET_RULES: List[Dict[str, Any]] = [
    # ============================ 一、学术诚信 R001-R005 ============================
    _rule("R001", "单次学习投入过高", "学术诚信", "考试",
          {"field": "order_total_amount", "op": ">=", "value": 5000},
          "高", 70, "人工审核", 90, "单次考试/课程投入金额 ≥ 5000，需人工复核"),
    _rule("R002", "极端高额学习投入", "学术诚信", "考试",
          {"field": "order_total_amount", "op": ">=", "value": 20000},
          "极高", 90, "拒绝", 98, "单次投入 ≥ 20000，疑似批量买分/机构代刷，一票否决"),
    _rule("R003", "投入远超历史均值", "学术诚信", "",
          {"and": [{"field": "order_total_amount", "op": ">=", "value": 3000},
                   {"field": "user_avg_order_amount", "op": "<=", "value": 500}]},
          "高", 65, "人工审核", 82, "本次投入 ≥ 3000 但历史均值 ≤ 500，投入突变"),
    _rule("R004", "异常高频优惠", "学术诚信", "作业",
          {"field": "order_discount_rate", "op": ">=", "value": 0.7},
          "中", 45, "标记", 60, "优惠率 ≥ 70%，疑似内部资源套利"),
    _rule("R005", "突破历史最大单笔", "学术诚信", "",
          {"and": [{"field": "order_total_amount", "op": ">=", "value": 2000},
                   {"field": "user_max_order_amount", "op": "<=", "value": 300}]},
          "中", 50, "标记", 70, "本次投入远超历史最大单笔（≤300）"),

    # ============================ 二、学习行为 R006-R010 ============================
    _rule("R006", "7 天学习行为异常", "学习行为", "",
          {"field": "user_orders_7d", "op": ">=", "value": 20},
          "高", 70, "人工审核", 86, "近 7 天学习行为 ≥ 20 次，疑似刷课"),
    _rule("R007", "30 天学习行为异常", "学习行为", "",
          {"field": "user_orders_30d", "op": ">=", "value": 50},
          "中", 55, "标记", 72, "近 30 天学习行为 ≥ 50 次"),
    _rule("R008", "极速提交", "学习行为", "作业",
          {"field": "order_pay_interval", "op": "between", "value": [0, 3]},
          "中", 40, "标记", 56, "交卷 ≤ 3 秒，疑似脚本/复制粘贴"),
    _rule("R009", "深夜大额学习", "学习行为", "考试",
          {"and": [{"field": "order_is_night", "op": "in", "value": [1]},
                   {"field": "order_total_amount", "op": ">=", "value": 3000}]},
          "高", 65, "人工审核", 76, "0-6 点学习且投入 ≥ 3000"),
    _rule("R010", "新账号高频学习", "学习行为", "",
          {"and": [{"field": "user_total_orders", "op": "<=", "value": 2},
                   {"field": "user_orders_7d", "op": ">=", "value": 5}]},
          "高", 60, "人工审核", 74, "账号行为极少却 7 天内学习 ≥ 5 次"),

    # ============================ 三、账号安全 R011-R015 ============================
    _rule("R011", "成绩申诉率过高", "账号安全", "",
          {"field": "user_refund_rate", "op": ">=", "value": 0.5},
          "高", 70, "人工审核", 88, "历史成绩申诉率 ≥ 50%"),
    _rule("R012", "申诉次数过多", "账号安全", "",
          {"field": "user_refund_count", "op": ">", "value": 9},
          "中", 50, "标记", 66, "累计申诉次数 > 9"),
    _rule("R013", "申诉金额过大", "账号安全", "",
          {"field": "user_refund_amount", "op": ">=", "value": 10000},
          "高", 65, "人工审核", 78, "累计申诉涉及金额 ≥ 10000"),
    _rule("R014", "高申诉叠加大额", "账号安全", "",
          {"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.3},
                   {"field": "order_total_amount", "op": ">=", "value": 2000}]},
          "高", 68, "人工审核", 80, "申诉率 ≥ 30% 且本次投入 ≥ 2000"),
    _rule("R015", "申诉率极高", "账号安全", "",
          {"field": "user_refund_rate", "op": ">=", "value": 0.8},
          "极高", 90, "拒绝", 96, "成绩申诉率 ≥ 80%，一票否决"),

    # ============================ 四、成绩异常 R016-R020 ============================
    _rule("R016", "退课率过高", "成绩异常", "选课",
          {"field": "user_postsale_rate", "op": ">=", "value": 0.5},
          "高", 65, "人工审核", 84, "历史退课率 ≥ 50%"),
    _rule("R017", "退课次数过多", "成绩异常", "选课",
          {"field": "user_postsale_count", "op": ">=", "value": 8},
          "中", 50, "标记", 62, "累计退课 ≥ 8 次"),
    _rule("R018", "取消选课过多", "成绩异常", "",
          {"field": "user_cancel_count", "op": ">=", "value": 10},
          "中", 45, "标记", 58, "累计取消选课 ≥ 10 次"),
    _rule("R019", "反馈投诉过多", "成绩异常", "成绩申诉",
          {"field": "user_complaint_count", "op": ">=", "value": 5},
          "高", 60, "人工审核", 71, "累计反馈投诉 ≥ 5 次，疑似恶意申诉"),
    _rule("R020", "退课+申诉双高", "成绩异常", "",
          {"and": [{"field": "user_postsale_rate", "op": ">=", "value": 0.4},
                   {"field": "user_refund_rate", "op": ">=", "value": 0.4}]},
          "极高", 85, "拒绝", 92, "退课率与申诉率同时 ≥ 40%，一票否决"),

    # ============================ 五、设备风险 R021-R025 ============================
    _rule("R021", "关联账号数异常", "设备风险", "",
          {"field": "user_address_count", "op": ">=", "value": 10},
          "中", 50, "标记", 61, "关联账号/设备/IP ≥ 10 个"),
    _rule("R022", "新设备大额投入", "设备风险", "考试",
          {"and": [{"field": "addr_is_new", "op": "==", "value": 1},
                   {"field": "order_total_amount", "op": ">=", "value": 3000}]},
          "高", 65, "人工审核", 77, "使用 7 天内新设备且投入 ≥ 3000"),
    _rule("R023", "跨地域过多", "设备风险", "",
          {"field": "addr_province_count", "op": ">=", "value": 5},
          "中", 45, "标记", 57, "关联实体覆盖 ≥ 5 个地域"),
    _rule("R024", "关联实体极多", "设备风险", "",
          {"field": "addr_total_count", "op": ">=", "value": 20},
          "高", 60, "人工审核", 68, "关联实体总数 ≥ 20，疑似号商"),
    _rule("R025", "新设备+新账号", "设备风险", "考试",
          {"and": [{"field": "addr_is_new", "op": "!=", "value": 0},
                   {"field": "user_total_orders", "op": "<=", "value": 1}]},
          "中", 40, "标记", 52, "新账号首行为即用新设备"),

    # ============================ 六、身份风险 R026-R030 ============================
    _rule("R026", "单次行为明细异常", "身份风险", "考试",
          {"field": "order_item_count", "op": ">=", "value": 30},
          "中", 45, "标记", 54, "单条记录明细 ≥ 30 项"),
    _rule("R027", "资源种类异常", "身份风险", "考试",
          {"field": "order_sku_count", "op": ">=", "value": 20},
          "中", 40, "标记", 51, "单次涉及资源种类 ≥ 20"),
    _rule("R028", "跨类分散", "身份风险", "考试",
          {"field": "order_category_count", "op": ">=", "value": 8},
          "中", 35, "标记", 46, "单次跨 ≥ 8 个资源分类"),
    _rule("R029", "行为总数异常区间", "身份风险", "",
          {"or": [{"field": "user_total_orders", "op": ">=", "value": 100},
                  {"field": "user_total_orders", "op": "<", "value": 1}]},
          "中", 35, "标记", 42, "行为数 ≥ 100（疑似号商）或 = 0（全新账号）"),
    _rule("R030", "综合高危画像", "身份风险", "",
          {"and": [{"field": "user_refund_rate", "op": ">=", "value": 0.5},
                   {"field": "user_avg_order_amount", "op": ">=", "value": 2000},
                   {"field": "user_address_count", "op": ">=", "value": 3}]},
          "极高", 95, "拒绝", 100, "高申诉率 + 高客单价 + 多关联实体三合一，一票否决"),
]

assert len(PRESET_RULES) == 30, "预置规则必须是 30 条（宝典 1.3）"
assert len({r["rule_id"] for r in PRESET_RULES}) == 30, "规则 ID 不允许重复"

# ---------------------------------------------------------------- 统计（前端元数据用）
CATEGORY_STATS: Dict[str, int] = {}
for _r in PRESET_RULES:
    CATEGORY_STATS[_r["rule_category"]] = CATEGORY_STATS.get(_r["rule_category"], 0) + 1

LEVEL_STATS: Dict[str, int] = {}
for _r in PRESET_RULES:
    LEVEL_STATS[_r["risk_level"]] = LEVEL_STATS.get(_r["risk_level"], 0) + 1

#: 一票否决规则（risk_level == 极高）
VETO_RULE_IDS = tuple(r["rule_id"] for r in PRESET_RULES if r["risk_level"] == "极高")
