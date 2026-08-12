"""
【P4-L3 2026-08-08 第三轮】gen_risk_data_with_dates.py --balance-pos / --target-pos-ratio 测试 (制造业版).

验证:
  1. CLI 参数完整 (--days/--per-day/--balance-pos/--target-pos-ratio/--live/--clean 等)
  2. 事件 picker 覆盖 3 种制造业事件
  3. 正例比例统计逻辑
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risk_data_with_dates.py"


class TestGenRiskDataWithDatesCLI:
    """scripts/gen_risk_data_with_dates.py 的 CLI 参数."""

    def test_script_accepts_balance_pos_argument(self):
        """必须接受 --balance-pos 参数."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--balance-pos" in stdout, f"--help 应含 --balance-pos, 实际: {stdout[:500]}"
        assert re.search(r"--balance-pos\s+\S", stdout), "--balance-pos 应有描述"

    def test_script_accepts_target_pos_ratio_argument(self):
        """必须接受 --target-pos-ratio 参数."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--target-pos-ratio" in stdout, f"--help 应含 --target-pos-ratio, 实际: {stdout[:500]}"
        assert re.search(r"--target-pos-ratio\s+\S", stdout), "--target-pos-ratio 应有描述"

    def test_existing_arguments_still_present(self):
        """原有参数 (--days / --per-day / --clean 等) 仍然存在."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        for arg in ["--days", "--per-day", "--max-per-day", "--clean", "--start", "--end", "--live"]:
            assert arg in stdout, f"--help 应保留 {arg} 参数, 实际: {stdout[:500]}"


class TestGenRiskDataWithDatesLogic:
    """脚本结构: 3 种制造业事件 picker + 正例统计 + 编码兼容."""

    def test_three_manufacturing_events(self):
        """脚本应支持 经销商订货 / 设备保修 / 跨区串货举报 3 种事件."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "经销商订货" in script
        assert "设备保修" in script
        assert "跨区串货举报" in script

    def test_balance_pos_uses_risky_dealer_prefix(self):
        """--balance-pos 用 RISK 高风险经销商前缀."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "RISKY_DEALER_PREFIX" in script
        assert '"RISK"' in script, "应有 RISK 前缀"

    def test_positive_counting_logic(self):
        """正例 = 拒绝/人工审核, 统计 pos_ratio."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'result.decision in ("拒绝", "人工审核")' in script, "应按 拒绝/人工审核 计正例"
        assert "pos_ratio" in script, "应计算 pos_ratio"

    def test_target_pos_ratio_warning(self):
        """目标正例比例未达标时打印警告."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "target_pos_ratio" in script
        assert "未达目标" in script or "正例比例未达" in script, "应有未达标警告"

    def test_stdout_reconfigure_for_utf8(self):
        """Windows GBK 终端兼容: 脚本开头 reconfigure UTF-8."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'sys.stdout.reconfigure(encoding="utf-8")' in script

    def test_source_ids_use_db_values(self):
        """source_id 直接用 DB 原始 ID (order_id/warranty_id/report_id), 不拼前缀."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'return "经销商订货", row.order_id, row.dealer_id' in script
        assert 'return "设备保修", row.warranty_id, row.dealer_id' in script
        assert 'return "跨区串货举报", row.report_id, row.dealer_id' in script
