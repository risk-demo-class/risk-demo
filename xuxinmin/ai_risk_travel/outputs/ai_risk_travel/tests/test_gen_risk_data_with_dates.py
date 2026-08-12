"""
旅游风控版 - gen_risk_data_with_dates.py CLI 参数与逻辑测试.

事件类型: 预订 / 支付 / 签证申请 / 退改签
--balance-pos / --target-pos-ratio 控制正例比例 (训练用).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risk_data_with_dates.py"


class TestGenRiskDataWithDatesCLI:
    """scripts/gen_risk_data_with_dates.py 的 CLI 参数."""

    def _help(self) -> str:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        return result.stdout.decode("utf-8", errors="replace")

    def test_script_accepts_balance_pos_argument(self):
        stdout = self._help()
        assert "--balance-pos" in stdout
        assert re.search(r"--balance-pos\s+\S", stdout)

    def test_script_accepts_target_pos_ratio_argument(self):
        stdout = self._help()
        assert "--target-pos-ratio" in stdout
        assert re.search(r"--target-pos-ratio\s+\S", stdout)

    def test_existing_arguments_still_present(self):
        stdout = self._help()
        for arg in ["--days", "--per-day", "--max-per-day", "--clean", "--start", "--end"]:
            assert arg in stdout, f"--help 应保留 {arg} 参数"

    def test_script_accepts_live_argument(self):
        stdout = self._help()
        assert "--live" in stdout
        assert re.search(r"--live\s+\S", stdout)


class TestGenRiskDataWithDatesLogic:
    """脚本逻辑: RISK 前缀 + 事件类型 + 正例判断."""

    def test_balance_pos_uses_risky_user_prefix(self):
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'RISKY_USER_PREFIX = "RISK"' in script
        assert "user_id LIKE :prefix" in script, "必须用 LIKE :prefix 查 RISK 用户"
        assert "预订" in script and "签证申请" in script and "退改签" in script

    def test_positive_counting_logic(self):
        """正例统计: 决策是'拒绝'或'人工审核' = 正例."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert '"拒绝"' in script and '"人工审核"' in script

    def test_target_pos_ratio_warning(self):
        """--target-pos-ratio 模式必须显示正例比例."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "正例比例" in script

    def test_stdout_reconfigure_for_emoji(self):
        """Windows GBK 终端不能编码 emoji, 必须 reconfigure UTF-8."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'sys.stdout.reconfigure(encoding="utf-8")' in script
