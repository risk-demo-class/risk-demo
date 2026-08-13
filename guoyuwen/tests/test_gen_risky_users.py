"""银行风险模式业务数据入口测试。"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risky_users.py"


class TestGenRiskyUsersCLI:
    def test_cli_exposes_count_seed_db_and_safe_reset(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            timeout=10,
            check=True,
        )
        output = result.stdout.decode("utf-8", errors="replace")
        for argument in ["--count", "--seed", "--db", "--reset"]:
            assert argument in output
        assert "不会在本脚本清库" in output

    def test_count_zero_fails_before_database_access(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--count", "0"],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode != 0
        assert "--count 必须 >= 1" in result.stderr.decode("utf-8", errors="replace")


class TestGenRiskyUsersLogic:
    def test_five_bank_risk_modes_are_explicit(self):
        from scripts import gen_risky_users

        assert gen_risky_users.RISK_MODES == [
            "异地大额", "凌晨密集", "新设备大额", "多头借贷", "设备多人共用"
        ]

    @pytest.mark.asyncio
    async def test_generation_delegates_to_seeded_bank_generator(self, monkeypatch):
        from scripts import gen_risky_users

        calls = []

        def fake_build(count, seed):
            calls.append(("build", count, seed))
            return {"user_info": [object()] * 80, "risk_patterns": {"异地大额": 10}}

        async def fake_write(data, database):
            calls.append(("write", len(data["user_info"]), database))

        monkeypatch.setattr(gen_risky_users, "build_business_data", fake_build)
        monkeypatch.setattr(gen_risky_users, "write_business_data", fake_write)
        result = await gen_risky_users.gen_risky_users(5, seed=123, db_name="bank_risk_test")
        assert calls == [("build", 80, 123), ("write", 80, "bank_risk_test")]
        assert result["seed"] == 123
        assert result["requested_users"] == 5

    @pytest.mark.asyncio
    async def test_reset_is_refused_without_touching_database(self):
        from scripts.gen_risky_users import gen_risky_users

        with pytest.raises(ValueError, match="不清库"):
            await gen_risky_users(5, reset=True)

    def test_script_has_no_deleted_ecommerce_orm_imports(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        for old_model in ["OrderInfo", "OrderItem", "AfterSale", "LogisticsComplaint"]:
            assert old_model not in source
