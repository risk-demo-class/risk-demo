# -*- coding: utf-8 -*-
"""智学安·教育风控平台 核心引擎单元测试（零依赖，标准库 unittest）

覆盖宝典要求的 4 个必测点：
    1. 规则引擎 14 个算子 + and/or/not 递归
    2. 双轨融合公式 + 一票否决 + 降级归一化
    3. 案件 5 态状态机 7 条边白名单
    4. 25 维特征定义完整性 + 升级校验（validator ensure_*）

运行：
    python -m unittest discover -s tests -v
    或直接： python tests/test_core.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config import settings                                    # noqa: E402
from app.engine import decision as decision_engine                 # noqa: E402
from app.engine import rule as rule_engine                         # noqa: E402
from app.engine.feature import (                                   # noqa: E402
    ADDR_FEATURES, FEATURE_DEFS, FEATURE_DIM, FEATURE_NAMES,
    ORDER_FEATURES, USER_FEATURES,
)
from app.service import case as case_service                       # noqa: E402


# ====================================================================== 1
class TestRuleEngine(unittest.TestCase):
    """规则引擎：14 个算子 + 3 个逻辑算子递归求值。"""

    F = {"order_amount": 500.0, "user_order_count": 3.0, "user_refund_rate": 0.6,
         "addr_user_count": 8.0}

    def _hit(self, cond) -> bool:
        return rule_engine.evaluate(cond, self.F)

    def test_op_count_is_14(self):
        self.assertEqual(rule_engine.OP_COUNT, 14)
        self.assertEqual(len(rule_engine.OP_DOC), 14)

    def test_compare_ops(self):
        self.assertTrue(self._hit({"field": "order_amount", "op": ">", "value": 100}))
        self.assertFalse(self._hit({"field": "order_amount", "op": ">", "value": 1000}))
        self.assertTrue(self._hit({"field": "order_amount", "op": ">=", "value": 500}))
        self.assertTrue(self._hit({"field": "order_amount", "op": "<", "value": 501}))
        self.assertTrue(self._hit({"field": "order_amount", "op": "<=", "value": 500}))

    def test_equality_ops(self):
        self.assertTrue(self._hit({"field": "user_order_count", "op": "==", "value": 3}))
        self.assertTrue(self._hit({"field": "user_order_count", "op": "!=", "value": 9}))

    def test_set_ops(self):
        self.assertTrue(self._hit({"field": "user_order_count", "op": "in", "value": [1, 2, 3]}))
        self.assertTrue(self._hit({"field": "user_order_count", "op": "not_in", "value": [7, 8]}))

    def test_range_ops(self):
        self.assertTrue(self._hit({"field": "order_amount", "op": "between", "value": [100, 1000]}))
        self.assertFalse(self._hit({"field": "order_amount", "op": "between", "value": [600, 1000]}))
        self.assertTrue(self._hit({"field": "order_amount", "op": "not_between", "value": [600, 1000]}))

    def test_exists_op(self):
        self.assertTrue(self._hit({"field": "order_amount", "op": "exists", "value": True}))
        self.assertFalse(self._hit({"field": "no_such_field", "op": "exists", "value": True}))

    def test_logic_and_or_not_recursive(self):
        cond = {"and": [
            {"field": "order_amount", "op": ">", "value": 100},
            {"or": [
                {"field": "user_order_count", "op": ">=", "value": 100},
                {"not": {"field": "user_refund_rate", "op": "<", "value": 0.5}},
            ]},
        ]}
        self.assertTrue(self._hit(cond))

    def test_unknown_field_does_not_hit(self):
        """未知字段必须判不命中，绝不能抛异常打断流水线。"""
        self.assertFalse(self._hit({"field": "ghost_feature", "op": ">", "value": 0}))

    def test_trace_records_every_node(self):
        cond = {"and": [
            {"field": "order_amount", "op": ">", "value": 100},
            {"field": "user_refund_rate", "op": ">", "value": 0.5},
        ]}
        hit, trace = rule_engine.evaluate_with_trace(cond, self.F)
        self.assertTrue(hit)
        self.assertEqual(len(trace), 3)                    # 2 个叶子 + 1 个 and
        for node in trace:
            self.assertIn("depth", node)
            self.assertIn("result", node)
            self.assertIn("note", node)


# ====================================================================== 2
class TestDecisionFusion(unittest.TestCase):
    """双轨融合：final = α×rule + β×ml，一票否决抬到 veto_min，未加载模型降级。"""

    # 命中记录的字段名与 risk_rule 表一致：risk_score / risk_level / rule_name
    VETO_HIT = [{"rule_id": "R020", "rule_name": "黑名单命中", "risk_score": 10,
                 "risk_level": "极高"}]
    NORMAL_HIT = [{"rule_id": "R001", "rule_name": "单次学习投入过高", "risk_score": 70,
                   "risk_level": "高"},
                  {"rule_id": "R003", "rule_name": "高退款率", "risk_score": 40,
                   "risk_level": "中"}]

    def test_rule_score_is_max_plus_3_per_extra_hit(self):
        """宝典 8.1：R001(70) + R003(40) → 70 + 3×1 = 73。"""
        self.assertEqual(decision_engine.calc_rule_score(self.NORMAL_HIT), 73)
        self.assertEqual(decision_engine.calc_rule_score([]), 0)

    def test_rule_score_capped_at_100(self):
        hits = [{"risk_score": 100, "risk_level": "极高"}] + \
               [{"risk_score": 50, "risk_level": "中"} for _ in range(10)]
        self.assertEqual(decision_engine.calc_rule_score(hits), 100)

    def test_weighted_fusion(self):
        # α=β=0.5 → 0.5×80 + 0.5×40 = 60
        fused = decision_engine.fuse_scores(80, 40.0, 0.5, 0.5, ml_loaded=True)
        self.assertAlmostEqual(fused, 60.0, places=4)

    def test_degrade_to_pure_rule_when_model_absent(self):
        a, b = decision_engine.effective_weights(0.5, 0.5, ml_loaded=False)
        self.assertAlmostEqual(a, 1.0, places=6)
        self.assertAlmostEqual(b, 0.0, places=6)
        # 模型未加载：规则分不能被腰斩
        fused = decision_engine.fuse_scores(70, 0.0, 0.5, 0.5, ml_loaded=False)
        self.assertAlmostEqual(fused, 70.0, places=4)

    def test_weights_kept_when_model_loaded(self):
        a, b = decision_engine.effective_weights(0.5, 0.5, ml_loaded=True)
        self.assertAlmostEqual(a, 0.5, places=6)
        self.assertAlmostEqual(b, 0.5, places=6)

    def test_veto_lifts_score_to_min(self):
        final, is_veto = decision_engine.apply_veto(10.0, self.VETO_HIT)
        self.assertTrue(is_veto)
        self.assertGreaterEqual(final, settings.RISK_VETO_MIN_SCORE)
        self.assertEqual(decision_engine.score_to_decision(final), "拒绝")

    def test_veto_never_lowers_score(self):
        final, is_veto = decision_engine.apply_veto(100.0, self.VETO_HIT)
        self.assertTrue(is_veto)
        self.assertAlmostEqual(final, 100.0, places=4)

    def test_no_veto_without_extreme_level(self):
        final, is_veto = decision_engine.apply_veto(20.0, self.NORMAL_HIT)
        self.assertFalse(is_veto)
        self.assertAlmostEqual(final, 20.0, places=4)

    def test_four_decision_thresholds(self):
        # 阈值是"区间下界"：score < PASS → 低/通过；< MARK → 中/标记；
        #                   < REVIEW → 高/人工审核；>= REVIEW → 极高/拒绝
        table = [
            (0, "通过"),
            (settings.RISK_PASS_THRESHOLD - 1, "通过"),
            (settings.RISK_PASS_THRESHOLD, "标记"),
            (settings.RISK_MARK_THRESHOLD - 1, "标记"),
            (settings.RISK_MARK_THRESHOLD, "人工审核"),
            (settings.RISK_REVIEW_THRESHOLD - 1, "人工审核"),
            (settings.RISK_REVIEW_THRESHOLD, "拒绝"),
            (100, "拒绝"),
        ]
        for score, expect in table:
            self.assertEqual(decision_engine.score_to_decision(score), expect,
                             f"score={score}")

    def test_risk_level_to_decision_mapping(self):
        pairs = {"低": "通过", "中": "标记", "高": "人工审核", "极高": "拒绝"}
        for level, dec in pairs.items():
            self.assertEqual(decision_engine.risk_level_to_decision(level), dec)

    def test_need_case_only_for_review_and_reject(self):
        self.assertTrue(decision_engine.need_case("人工审核"))
        self.assertTrue(decision_engine.need_case("拒绝"))
        self.assertFalse(decision_engine.need_case("通过"))
        self.assertFalse(decision_engine.need_case("标记"))

    def test_calculate_end_to_end_returns_4_steps(self):
        features = {name: 0.0 for name in FEATURE_NAMES}
        r = decision_engine.calculate(features, self.VETO_HIT)
        self.assertEqual(len(r["steps"]), 4)
        self.assertTrue(r["is_veto"])
        self.assertEqual(r["decision"], "拒绝")
        self.assertGreaterEqual(r["final_score"], settings.RISK_VETO_MIN_SCORE)


# ====================================================================== 3
class TestCaseStateMachine(unittest.TestCase):
    """5 态 7 边状态机白名单，终态不可再流转。"""

    def test_five_states_seven_edges(self):
        doc = case_service.state_machine_doc()
        self.assertEqual(len(doc["statuses"]), 5)
        self.assertEqual(doc["edge_count"], 7)
        self.assertEqual(case_service.TRANSITION_COUNT, 7)

    def test_legal_paths(self):
        legal = [("待审核", "审核中"), ("待审核", "已关闭"), ("审核中", "已通过"),
                 ("审核中", "已拒绝"), ("审核中", "已关闭")]
        for src, dst in legal:
            self.assertTrue(case_service.can_transition(src, dst), f"{src}->{dst} 应合法")

    def test_illegal_paths_blocked(self):
        illegal = [("已通过", "待审核"), ("已拒绝", "审核中"), ("已关闭", "已通过"),
                   ("已通过", "已拒绝")]
        for src, dst in illegal:
            self.assertFalse(case_service.can_transition(src, dst), f"{src}->{dst} 应被拒")

    def test_terminal_states_have_no_outgoing_edge(self):
        doc = case_service.state_machine_doc()
        for st in doc["terminal"]:
            self.assertEqual(case_service.allowed_transitions(st), [], f"{st} 应是终态")


# ====================================================================== 4
class TestFeatureDefs(unittest.TestCase):
    """25 维特征：14 用户 + 8 学习 + 3 账号，定义与实现必须自洽。"""

    def test_total_is_25(self):
        self.assertEqual(len(FEATURE_DEFS), 25)
        self.assertEqual(len(FEATURE_NAMES), 25)

    def test_dimension_split_14_8_3(self):
        self.assertEqual(len(USER_FEATURES), 14)
        self.assertEqual(len(ORDER_FEATURES), 8)
        self.assertEqual(len(ADDR_FEATURES), 3)
        self.assertEqual(len(USER_FEATURES) + len(ORDER_FEATURES) + len(ADDR_FEATURES), 25)
        self.assertEqual({f["dim"] for f in FEATURE_DEFS}, {"用户", "学习", "账号"})

    def test_no_duplicate_names(self):
        self.assertEqual(len(set(FEATURE_NAMES)), 25, "特征名不能重复（会覆盖快照）")

    def test_every_def_has_required_keys(self):
        for d in FEATURE_DEFS:
            for key in ("name", "dim", "label", "formula"):
                self.assertIn(key, d, f"{d.get('name')} 缺少 {key}")
            self.assertIn(d["dim"], ("用户", "学习", "账号"))

    def test_dim_lookup_consistent(self):
        for d in FEATURE_DEFS:
            self.assertEqual(FEATURE_DIM[d["name"]], d["dim"])


# ====================================================================== 5
class TestValidator(unittest.TestCase):
    """请求校验：6 个 ensure_* 必须齐全，非法枚举与金额不一致必须拒绝。"""

    def test_six_ensure_functions_exist(self):
        from app.service import validator
        expected = ["ensure_event_type_valid", "ensure_user_exists",
                    "ensure_source_matches_event_type", "ensure_order_belongs_to_user",
                    "ensure_receive_id_belongs_to_user", "ensure_amount_consistent"]
        for fn in expected:
            self.assertTrue(callable(getattr(validator, fn, None)), f"缺少 {fn}")
        self.assertEqual(len(expected), 6)

    def test_invalid_event_type_rejected(self):
        from app.service import validator
        with self.assertRaises(Exception):
            validator.ensure_event_type_valid("不存在的事件")

    def test_valid_event_types_pass(self):
        from app.service import validator
        for t in ("考试", "作业", "选课", "成绩申诉"):
            self.assertEqual(validator.ensure_event_type_valid(t), t)

    def test_amount_inconsistent_rejected(self):
        from app.service import validator
        order = {"order_id": "ORD1", "total_amount": 100.0}
        validator.ensure_amount_consistent(order, 100.0)          # 一致 → 放行
        validator.ensure_amount_consistent(order, None)            # 未传 → 跳过
        with self.assertRaises(Exception):
            validator.ensure_amount_consistent(order, 999.0)       # 不一致 → 拒绝


if __name__ == "__main__":
    unittest.main(verbosity=2)
