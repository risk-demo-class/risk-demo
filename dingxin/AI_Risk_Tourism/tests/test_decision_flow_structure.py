"""
决策流程结构测试 (DB-free)
确保 run_risk_check 的 7 步流水线关键步骤未被误删/乱序 (通过源码调用顺序断言).
"""
import inspect

from app.engine import decision

# run_risk_check 内按顺序调用的步骤函数 (业务分支可适配, 但骨架顺序不能乱)
STEP_FUNCTIONS = [
    "_build_context",
    "_create_event_record",
    "_compute_features",
    "_save_feature_snapshot",
    "_evaluate_rules",
    "_calculate_decision",
    "_save_assessment",
    "_maybe_create_case",
    "_update_user_profile",
    "_build_response",
]


class TestDecisionFlowStructure:
    def test_run_risk_check_calls_steps_in_order(self):
        src = inspect.getsource(decision.run_risk_check)
        positions = [src.find(name) for name in STEP_FUNCTIONS]
        missing = [n for n, p in zip(STEP_FUNCTIONS, positions) if p < 0]
        assert not missing, f"run_risk_check 缺少步骤: {missing}"
        assert positions == sorted(positions), "run_risk_check 步骤调用顺序被改动"

    def test_core_scoring_functions_exist(self):
        assert callable(decision.calculate_final_score)
        assert callable(decision.check_veto)
        assert callable(decision._score_to_level)
        assert callable(decision._score_to_decision)
        assert callable(decision._calculate_decision)
