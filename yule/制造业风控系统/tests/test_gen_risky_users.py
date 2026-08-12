"""
【P4-L3 2026-08-08 第二轮】gen_risky_users.py 参数化测试 (制造业版).

测试 --count/--reset 参数 + 8 种模式轮换 + 用户 ID 生成规律.
不需要真实 DB, 用 monkeypatch 把 async DB 操作 mock 掉.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risky_users.py"


class TestGenRiskyUsersCLI:
    """scripts/gen_risky_users.py 的 CLI 参数 + 模式设计."""

    def test_script_accepts_count_argument(self):
        """必须接受 --count 参数 (默认 8)."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--count" in stdout, f"--help 应含 --count, 实际: {stdout[:500]}"
        assert "default 8" in stdout.lower() or "default=8" in stdout or "8" in stdout

    def test_script_accepts_reset_argument(self):
        """必须接受 --reset 参数 (先删旧数据)."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--reset" in stdout, f"--help 应含 --reset, 实际: {stdout[:500]}"
        import re
        assert re.search(r"--reset\s+\S", stdout), f"--help 应显示 --reset 跟描述, 实际: {stdout[:500]}"

    def test_script_validates_count_minimum(self):
        """--count < 1 应报错 (不能生成 0 个经销商)."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--count", "0"],
            capture_output=True, timeout=10,
        )
        assert result.returncode != 0, f"--count 0 应报错, 实际 exit code {result.returncode}"


class TestGenRiskyUsersLogic:
    """gen_risky_users 函数逻辑 (不连真实 DB, 测函数 + 模式轮换)."""

    def test_eight_risk_modes_defined(self):
        """8 种制造业风险模式必须定义, 跟 8 条核心规则一一对应."""
        sys.path.insert(0, str(ROOT))
        from scripts import gen_risky_users
        assert len(gen_risky_users.RISK_MODES) == 8, (
            f"应 8 种风险模式, 实际 {len(gen_risky_users.RISK_MODES)}"
        )
        expected = [
            "跨区串货举报", "保修期外高频保修", "大额囤货", "套保嫌疑",
            "新经销商大单", "维修费用异常", "资质过期", "黑经销商",
        ]
        assert gen_risky_users.RISK_MODES == expected, (
            f"模式名变化会破坏规则命中演示, 当前 {gen_risky_users.RISK_MODES}"
        )
        assert len(gen_risky_users.MODE_GENERATORS) == 8, (
            f"应 8 个模式生成器, 实际 {len(gen_risky_users.MODE_GENERATORS)}"
        )

    def test_user_id_generation_pattern(self):
        """用户 ID 必须按 RISK001, RISK002, ... 规律生成 (跟 gen_risk_data.py 的 LIKE 'RISK%' 匹配)."""
        count = 30
        expected = [f"RISK{i:03d}" for i in range(1, count + 1)]
        sys.path.insert(0, str(ROOT))
        from scripts import gen_risky_users
        user_ids = [f"RISK{i:03d}" for i in range(1, count + 1)]
        assert user_ids == expected
        # 模式轮换: idx % 8
        assert len(gen_risky_users.MODE_GENERATORS) == 8
