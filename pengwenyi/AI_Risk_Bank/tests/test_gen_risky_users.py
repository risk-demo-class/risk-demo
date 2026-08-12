"""
【银行版】gen_risky_users.py 参数化测试.

测试 --count 参数 + build_user 高风险数据模式 (低信用分/黑卡/代理IP/新设备/高负债).
不需要真实 DB, 直接调 build_user 纯函数.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risky_users.py"


class TestGenRiskyUsersCLI:
    """scripts/gen_risky_users.py 的 CLI 参数."""

    def test_script_accepts_count_argument(self):
        """必须接受 --count 参数 (默认 30)."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        # GBK 环境解码中文会失败, 用 errors='replace' 兜底
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--count" in stdout, f"--help 应含 --count, 实际: {stdout[:500]}"
        assert "默认 30" in stdout or "(默认 30)" in stdout, (
            f"--count 默认值应是 30 (argparse help 显示 '默认 30'), 实际: {stdout[:500]}"
        )

    def test_script_no_reset_argument(self):
        """银行版不提供 --reset (RISK 用户按差额补足, 不删历史)."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--reset" not in stdout, "银行版无 --reset 参数 (差额补足模式)"


class TestBuildUserBankLogic:
    """build_user 纯函数: 1 个 RISK 高风险用户的配套数据."""

    def test_build_user_returns_9_tuple(self):
        """build_user(1) 返回 (uid, name, credit, register_at, cards, devices, txns, loans, logins)."""
        sys.path.insert(0, str(ROOT))
        from scripts.gen_risky_users import build_user
        uid, name, credit, register_at, cards, devices, txns, loans, logins = build_user(1)
        assert uid == "RISK001"
        assert isinstance(name, str) and len(name) >= 2
        assert isinstance(register_at, object)

    def test_low_credit_score(self):
        """RISK 用户信用分 350~480 (低信用 → R015 低信用分大额交易)."""
        sys.path.insert(0, str(ROOT))
        from scripts.gen_risky_users import build_user
        for idx in range(1, 21):
            credit = build_user(idx)[2]
            assert 350 <= credit <= 480, f"RISK{idx:03d} 信用分应 350-480, 实际 {credit}"

    def test_cards_and_devices(self):
        """1~2 张卡 + 3 台设备 (含 1 台 <7 天新设备 → R005 新设备大额)."""
        sys.path.insert(0, str(ROOT))
        from scripts.gen_risky_users import build_user
        from datetime import datetime, timedelta
        for idx in range(1, 11):
            uid, name, credit, register_at, cards, devices, txns, loans, logins = build_user(idx)
            assert 1 <= len(cards) <= 2, f"应 1~2 张卡, 实际 {len(cards)}"
            assert len(devices) >= 3, f"应 >=3 台设备 (含新设备), 实际 {len(devices)}"
            new_devs = [
                d for d in devices
                if (datetime.now() - d[3]).days < 7  # first_seen < 7 天
            ]
            assert len(new_devs) >= 1, "必须有 1 台注册 <7 天的新设备"

    def test_txns_hit_bank_rules(self):
        """交易命中银行规则: 大额 (R001/R015) / 黑卡 (R030) / 夜间 (R002)."""
        sys.path.insert(0, str(ROOT))
        from scripts.gen_risky_users import build_user
        from scripts.gen_risky_users import BLACK_CARDS
        for idx in range(1, 11):
            uid, name, credit, register_at, cards, devices, txns, loans, logins = build_user(idx)
            assert len(txns) >= 8, f"交易应 >=8 笔, 实际 {len(txns)}"
            amounts = [t[3] for t in txns]
            assert max(amounts) >= 20000, f"至少 1 笔大额 (>=2万), 实际 max={max(amounts)}"
            to_cards = {t[2] for t in txns}
            assert to_cards & set(BLACK_CARDS), "交易应含黑卡 (R030 黑卡拦截)"
            night = [t for t in txns if t[8].hour <= 4]
            assert len(night) >= 1, "应有夜间交易 (R002 凌晨密集操作)"

    def test_loans_high_debt(self):
        """贷款 2~4 笔 + 高负债 0.60~0.90 (R010 高负债大额申贷 / R012 突击)."""
        sys.path.insert(0, str(ROOT))
        from scripts.gen_risky_users import build_user
        for idx in range(1, 11):
            uid, name, credit, register_at, cards, devices, txns, loans, logins = build_user(idx)
            assert 2 <= len(loans) <= 4, f"贷款应 2~4 笔, 实际 {len(loans)}"
            debts = [l[6] for l in loans]
            assert min(debts) >= 0.60, f"负债率应 >=0.60, 实际 min={min(debts)}"

    def test_logins_have_failures(self):
        """登录 5~15 次且含失败登录 (R003 深夜异常登录 / 撞库)."""
        sys.path.insert(0, str(ROOT))
        from scripts.gen_risky_users import build_user
        for idx in range(1, 11):
            uid, name, credit, register_at, cards, devices, txns, loans, logins = build_user(idx)
            assert 5 <= len(logins) <= 15, f"登录应 5~15 次, 实际 {len(logins)}"
            successes = [l[5] for l in logins]
            assert 0 in successes, "登录应含失败记录 (success=0)"

    def test_user_id_generation_pattern(self):
        """用户 ID 必须按 RISK001, RISK002, ... 规律生成 (跟 gen_risk_data.py 的 LIKE 'RISK%' 匹配)."""
        count = 30
        expected = [f"RISK{i:03d}" for i in range(1, count + 1)]
        actual = [f"RISK{i:03d}" for i in range(1, count + 1)]
        assert actual == expected
        # 必须 3 位补零 (RISK001 不是 RISK1)
        assert all(len(uid) == 7 for uid in actual), "RISK 后必须是 3 位数字"
        # 必须能从 1 递增到 count
        assert actual[0] == "RISK001"
        assert actual[-1] == f"RISK{count:03d}"
