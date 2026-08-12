"""
【银行版】gen_risk_data.py 造评估数据脚本测试 (4 大银行场景).

验证:
- CLI 参数: --balance-pos / --target-pos-ratio / --days / --per-day / --clean / --start / --end / --live
- RISKY_USER_PREFIX = "RISK" 常量 + LIKE 'RISK%' 查高风险用户
- 正例统计: 决策 "拒绝" 或 "人工审核" = 正例, grand_positive 累加
- 完成提示: 整体正例比例 + <15% 警告 (防假收敛)
- 训练数据严格化: reset_ml_score_null (ml_score 强制 NULL)
- Windows GBK 终端 reconfigure UTF-8
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risk_data.py"


class TestGenRiskDataCLI:
    """scripts/gen_risk_data.py 的 CLI 参数."""

    def test_script_accepts_balance_pos_argument(self):
        """必须接受 --balance-pos 参数 (80% 概率挑 RISK 高风险用户)."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--balance-pos" in stdout, f"--help 应含 --balance-pos, 实际: {stdout[:500]}"
        assert re.search(r"--balance-pos\s+\S", stdout), "--balance-pos 应有描述"

    def test_script_accepts_target_pos_ratio_argument(self):
        """必须接受 --target-pos-ratio 参数 (目标正例比例, 配合 --balance-pos)."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--target-pos-ratio" in stdout, f"--help 应含 --target-pos-ratio, 实际: {stdout[:500]}"
        assert re.search(r"--target-pos-ratio\s+\S", stdout), "--target-pos-ratio 应有描述"

    def test_existing_arguments_still_present(self):
        """原有参数 (--days / --per-day / --clean / --start / --end / --live) 仍然存在."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        for arg in ["--days", "--per-day", "--max-per-day", "--clean", "--start", "--end", "--live"]:
            assert arg in stdout, f"--help 应保留 {arg} 参数, 实际: {stdout[:500]}"


class TestGenRiskDataBankLogic:
    """银行版造数逻辑 (静态源码断言)."""

    def test_risky_user_prefix_defined(self):
        """--balance-pos 模式必须用 RISK 前缀查 RISK 高风险用户."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'RISKY_USER_PREFIX = "RISK"' in script or "RISKY_USER_PREFIX='RISK'" in script, (
            "必须定义 RISKY_USER_PREFIX 常量 (跟 gen_risky_users.py 对齐)"
        )
        # 必须用 LIKE :prefix / LIKE 'RISK%' 查 RISK 用户
        assert "LIKE :prefix" in script or "LIKE 'RISK%'" in script or "RISKY_USER_PREFIX" in script

    def test_four_bank_scenarios(self):
        """4 大银行场景必须覆盖: 转账/登录/贷款申请/信用卡."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        for et in ["转账", "登录", "贷款申请", "信用卡"]:
            assert et in script, f"造数脚本必须覆盖 {et} 场景"

    def test_positive_counting_logic(self):
        """正例统计: 决策是 '拒绝' 或 '人工审核' = 正例, 必须用 grand_positive 累加."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "grand_positive" in script, "必须有 grand_positive 正例累加器"
        assert '"拒绝"' in script or "'拒绝'" in script, "必须判断 '拒绝' 决策"
        assert '"人工审核"' in script or "'人工审核'" in script, "必须判断 '人工审核' 决策"

    def test_target_pos_ratio_warning(self):
        """--target-pos-ratio 模式: 跑完必须提示用户正例比例, 低于 15% 警告."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "overall_pos" in script or "grand_positive" in script, (
            "必须计算整体正例比例, 提示用户"
        )
        assert "正例比例" in script, "完成时必须显示正例比例"

    def test_stdout_reconfigure_for_emoji(self):
        """Windows GBK 终端不能编码 emoji, 必须 reconfigure UTF-8."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert 'sys.stdout.reconfigure(encoding="utf-8")' in script, (
            "必须 sys.stdout.reconfigure(encoding='utf-8') 防 Windows GBK 编码 emoji 报错"
        )

    def test_reset_ml_score_null_for_train_purity(self):
        """【训练数据严格化】造数结束后必须统一置 ml_score=NULL (防训练脏数据)."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "reset_ml_score_null" in script, (
            "必须调用 reset_ml_score_null (训练数据严格化: 统一 ml_score=NULL)"
        )

    def test_target_ratio_requires_balance_pos(self):
        """--target-pos-ratio 不带 --balance-pos 时必须自动启用并提示."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "--target-pos-ratio 必须配合 --balance-pos" in script, (
            "target-pos-ratio 应提示配合 balance-pos"
        )
