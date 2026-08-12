"""
旅游风控版 - one_command.py 一条龙脚本结构测试 (6 步: 重置 → 业务数据 → 评估数据 → 训练 → 趋势 → 今日).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "one_command.py"


class TestOneCommandStructure:
    """6 个 step 函数必须存在."""

    def test_script_exists(self):
        assert SCRIPT.exists(), "one_command.py 必须存在"

    def test_six_step_functions_defined(self):
        src = SCRIPT.read_text(encoding="utf-8")
        for step in [
            "step_1_reset_db", "step_2_business_data", "step_3_train_dataset",
            "step_4_train_xgboost", "step_5_dated_data", "step_6_business_today",
        ]:
            assert f"def {step}" in src, f"缺少 {step}"

    def test_steps_call_right_scripts(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert "init_db.py" in src, "步骤 1 应调 init_db.py"
        assert "gen_business_data.py" in src, "步骤 2 应调 gen_business_data.py"
        assert "gen_risk_data.py" in src, "步骤 3 应调 gen_risk_data.py"
        assert "train_xgb_model.py" in src, "步骤 4 应调 train_xgb_model.py"
        assert "gen_risk_data_with_dates.py" in src, "步骤 5/6 应调 gen_risk_data_with_dates.py"

    def test_step_3_uses_balance_pos(self):
        """步骤 3 必须用 --balance-pos --target-pos-ratio 控制正例比例."""
        src = SCRIPT.read_text(encoding="utf-8")
        m = re.search(r"def step_3_train_dataset.*?(?=\ndef )", src, re.DOTALL)
        assert m, "找不到 step_3_train_dataset"
        assert "--balance-pos" in m.group(0)
        assert "--target-pos-ratio" in m.group(0)

    def test_step_6_uses_live_for_dashboard(self):
        """步骤 6 用 --live (仪表盘'今日'能看到)."""
        src = SCRIPT.read_text(encoding="utf-8")
        m = re.search(r"def step_6_business_today.*?(?=\ndef )", src, re.DOTALL)
        assert m, "找不到 step_6_business_today"
        assert "--live" in m.group(0)


class TestOneCommandSkipOptions:
    """3 个跳过选项: --skip-init / --skip-train / --only-start."""

    def test_has_skip_init_option(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert "--skip-init" in src
        assert "args.skip_init" in src
        m = re.search(r"if not args\.skip_init:(.*?)(?=\n\s+if not args\.skip_train)", src, re.DOTALL)
        assert m, "skip-init 必须跳过 1+2"
        skip_text = m.group(0)
        assert "step_1_reset_db" in skip_text
        assert "step_2_business_data" in skip_text

    def test_has_skip_train_option(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert "--skip-train" in src
        assert "args.skip_train" in src
        m = re.search(r"if not args\.skip_train:(.*?)(?=\n\s+step_5)", src, re.DOTALL)
        assert m, "skip-train 必须跳过 3+4"
        skip_text = m.group(0)
        assert "step_3_train_dataset" in skip_text
        assert "step_4_train_xgboost" in skip_text

    def test_has_only_start_option(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert "--only-start" in src
        assert "args.only_start" in src
        m = re.search(r"if args\.only_start:(.*?)(?=\s+else:)", src, re.DOTALL)
        assert m, "only-start 必须存在"
        assert "step_6_business_today" in m.group(0)


class TestOneCommandErrorHandling:
    """错误处理: 子进程失败要抛 RuntimeError 并打印排查建议."""

    def test_subprocess_failure_raises(self):
        src = SCRIPT.read_text(encoding="utf-8")
        m = re.search(r"def _run_subprocess.*?(?=\ndef )", src, re.DOTALL)
        assert m, "找不到 _run_subprocess"
        assert "RuntimeError" in m.group(0)

    def test_main_catches_runtime_error(self):
        src = SCRIPT.read_text(encoding="utf-8")
        m = re.search(r"def main.*?(?=\nif __name__)", src, re.DOTALL)
        assert m, "找不到 main"
        assert "except RuntimeError" in m.group(0)
        assert "排查建议" in m.group(0)

    def test_prints_next_step_after_success(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert "python run_app.py" in src


class TestOneCommandDocumentation:
    """docstring 跟 6 步工作流一致."""

    def test_docstring_lists_all_six_steps(self):
        src = SCRIPT.read_text(encoding="utf-8")
        m = re.search(r'"""(.*?)"""', src, re.DOTALL)
        assert m, "缺模块 docstring"
        doc = m.group(1)
        for step_num, step_name in [
            ("1", "重置"),
            ("2", "业务"),
            ("3", "评估"),
            ("4", "训练"),
            ("5", "趋势"),
            ("6", "业务"),
        ]:
            assert step_num in doc and step_name in doc, (
                f"docstring 应提到步骤 {step_num} ({step_name})"
            )
