"""
旅游风控版 - gen_risky_users.py 测试.

实现复用 gen_business_data.py: 40 用户内置 7 个 RISK 高风险画像用户
(RISK001-RISK007), 保证演示时规则可命中.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risky_users.py"


class TestGenRiskyUsersCLI:
    """scripts/gen_risky_users.py 的 CLI 参数."""

    def test_script_accepts_count_argument(self):
        """必须接受 --count 参数 (默认 40)."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--count" in stdout, f"--help 应含 --count, 实际: {stdout[:500]}"

    def test_script_accepts_export_sql_argument(self):
        """必须接受 --export-sql 参数 (无需 DB 导出 SQL 快照)."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, timeout=10,
        )
        stdout = result.stdout.decode("utf-8", errors="replace")
        assert "--export-sql" in stdout, f"--help 应含 --export-sql, 实际: {stdout[:500]}"


class TestGenRiskyUsersLogic:
    """高风险用户逻辑: 7 个 RISK 画像 + RISK% 前缀."""

    def test_seven_risk_users_built(self):
        """build_rows 必须内置 7 个 RISK 高风险用户 (RISK001-RISK007)."""
        sys.path.insert(0, str(ROOT))
        from scripts.gen_business_data import build_rows
        rows = build_rows(40)
        risk_users = [u for u in rows["user_info"] if u["user_id"].startswith("RISK")]
        assert len(risk_users) == 7, f"应 7 个 RISK 用户, 实际 {len(risk_users)}"
        ids = sorted(u["user_id"] for u in risk_users)
        assert ids == [f"RISK{i:03d}" for i in range(1, 8)]

    def test_risk_users_have_orders_and_passengers(self):
        """RISK 用户必须有关联订单和乘客, 保证规则/黑名单演示可命中."""
        sys.path.insert(0, str(ROOT))
        from scripts.gen_business_data import build_rows
        rows = build_rows(40)
        risk_order_ids = {
            o["order_id"] for o in rows["order_info"] if o["user_id"].startswith("RISK")
        }
        assert len(risk_order_ids) >= 20, f"RISK 用户订单数应 >= 20, 实际 {len(risk_order_ids)}"
        risk_passengers = [p for p in rows["passenger_info"] if p["order_id"] in risk_order_ids]
        assert len(risk_passengers) >= 20, f"RISK 用户乘客应 >= 20, 实际 {len(risk_passengers)}"

    def test_black_passport_uid_pattern(self):
        """gen_risk_data.py 用 LIKE 'RISK%' 查高风险用户, 脚本必须定义该前缀."""
        script = SCRIPT_PATH.read_text(encoding="utf-8")
        assert "RISK" in script
