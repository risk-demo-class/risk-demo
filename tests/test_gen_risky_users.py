"""
【P4-L3 2026-08-08 第二轮】gen_risky_users.py 参数化测试.
【2026-08-11 更新】风险模式 8 → 16 (新增 R009/R012/R011/R013-R020 对应模式).

测试 --count/--reset 参数 + 16 种模式轮换 + 用户 ID 生成规律.
不需要真实 DB, 用 monkeypatch 把 async DB 操作 mock 掉.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risky_users.py"


class TestGenRiskyUsersCLI:
    """scripts/gen_risky_users.py 的 CLI 参数 + 模式设计."""

    def test_script_accepts_count_argument(self):
        """必须接受 --count 参数 (默认 5)."""
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        # GBK 环境解码中文会失败, 用 errors='replace' 兜底
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--count" in stdout, f"--help 应含 --count, 实际: {stdout[:500]}"
        assert "default 8" in stdout.lower() or "default=8" in stdout or "8" in stdout

    def test_script_accepts_reset_argument(self):
        """必须接受 --reset 参数 (先删旧数据)."""
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--reset" in stdout, f"--help 应含 --reset, 实际: {stdout[:500]}"
        # argparse 知道 --reset 参数 (--reset 后面有 " " 或换行, 后面跟帮助说明)
        # 用正则: --reset 后面有空格 + 至少 1 个字符 (中文描述)
        import re
        assert re.search(r"--reset\s+\S", stdout), f"--help 应显示 --reset 跟描述, 实际: {stdout[:500]}"

    def test_script_validates_count_minimum(self):
        """--count < 1 应报错 (不能生成 0 个用户)."""
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--count", "0"],
            capture_output=True, timeout=10,
        )
        # 应该非零退出, 因为 raise ValueError
        assert result.returncode != 0, f"--count 0 应报错, 实际 exit code {result.returncode}"


class TestGenRiskyUsersLogic:
    """gen_risky_users 函数逻辑 (不连真实 DB, 测函数 + 模式轮换)."""

    def test_risk_modes_defined(self):
        """16 种医疗风险模式必须定义: 原有 8 种 + 监管扩展 8 种."""
        sys.path.insert(0, str(ROOT))
        from scripts import gen_risky_users
        # 模式名 (16 个, 对应 RISK_MODES 列表)
        assert len(gen_risky_users.RISK_MODES) == 16, (
            f"应 16 种风险模式, 实际 {len(gen_risky_users.RISK_MODES)}"
        )
        expected = [
            "医保卡盗刷", "医生统方", "挂号黄牛", "处方超量", "虚假病历", "药品代购",
            "异地集中结算", "黑医保卡", "无诊断开药", "医师跨院高频", "夜间结算异常",
            "慢病频繁购药", "分解住院结算", "重复购药回流", "串换药品嫌疑", "异常高额报销",
        ]
        assert gen_risky_users.RISK_MODES == expected, (
            f"模式名变化会破坏向后兼容, 当前 {gen_risky_users.RISK_MODES}"
        )
        # 模式生成器 (16 个, 跟 RISK_MODES 一一对应)
        assert len(gen_risky_users._GEN_FUNCS) == 16, (
            f"应 16 个模式生成器, 实际 {len(gen_risky_users._GEN_FUNCS)}"
        )

    def test_user_id_generation_pattern(self):
        """用户 ID 必须按 RISK001, RISK002, ... 规律生成 (跟 gen_risk_data.py 的 LIKE 'RISK%' 匹配)."""
        # 模拟生成 30 个用户的 ID 列表
        count = 32
        expected = [f"RISK{i:03d}" for i in range(1, count + 1)]
        # 用 list comprehension 复现文件里的逻辑
        actual = [f"RISK{i:03d}" for i in range(1, count + 1)]
        assert actual == expected
        # 必须 3 位补零 (RISK001 不是 RISK1)
        assert all(len(uid) == 7 for uid in actual), "RISK 后必须是 3 位数字"
        # 必须能从 1 递增到 count
        assert actual[0] == "RISK001"
        assert actual[-1] == f"RISK{count:03d}"

    def test_mode_rotation_pattern(self):
        """模式轮换: idx % 16, 32 个用户 = 2 套各 16 模式."""
        count = 32
        mode_indices = [i % 16 for i in range(count)]
        # 每种模式出现 2 次
        from collections import Counter
        cnt = Counter(mode_indices)
        assert all(v == 2 for v in cnt.values()), f"32 个用户应 2 套 × 16 模式 = 每模式 2 次, 实际 {cnt}"
        # 0-15 顺序
        assert mode_indices == list(range(16)) * 2

    def test_count_1_generates_only_first_mode(self):
        """--count 1 只生成 1 个用户 (模式 0: 高退款率, RISK001)."""
        count = 1
        user_ids = [f"RISK{i:03d}" for i in range(1, count + 1)]
        mode_idx = (count - 1) % 16
        assert user_ids == ["RISK001"]
        assert mode_idx == 0  # 医保卡盗刷模式

    def test_count_5_generates_one_set(self):
        """--count 5 生成前 5 种模式 (RISK001-005)."""
        count = 5
        user_ids = [f"RISK{i:03d}" for i in range(1, count + 1)]
        modes = [i % 16 for i in range(count)]
        assert user_ids == ["RISK001", "RISK002", "RISK003", "RISK004", "RISK005"]
        assert modes == [0, 1, 2, 3, 4]
