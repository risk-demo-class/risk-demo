"""按业务日期生成银行评估脚本的兼容性与标签纯度测试。"""

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "gen_risk_data_with_dates.py"


@pytest.fixture(scope="module")
def source() -> str:
    return SCRIPT_PATH.read_text(encoding="utf-8")


class TestGenRiskDataWithDatesCLI:
    def test_legacy_cli_arguments_remain_parseable(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True,
            timeout=10,
            check=True,
        )
        output = result.stdout.decode("utf-8", errors="replace")
        for argument in [
            "--days", "--per-day", "--max-per-day", "--clean", "--start",
            "--end", "--live", "--balance-pos", "--target-pos-ratio",
            "--force-pos-ratio", "--seed",
        ]:
            assert argument in output

    def test_deprecated_ratio_flags_are_documented_as_non_mutating(self, source):
        assert "兼容参数；不操纵标签" in source
        assert "已弃用；不允许强改标签" in source
        assert "标签仍完全来自规则/决策" in source


class TestGenRiskDataWithDatesLogic:
    def test_delegates_to_real_pipeline_dataset_generator(self, source):
        assert "from scripts.gen_train_dataset import gen_train_dataset" in source
        assert "count=days * per_day" in source
        assert "clean=clean" in source
        assert "seed=seed" in source

    def test_no_ecommerce_picker_or_label_retry_path(self, source):
        forbidden = [
            "_pick_forced_postsale", "_pick_forced_logistics_complaint",
            "_pick_order_for_balance", "RISKY_USER_PREFIX", "decision_hit",
            "grand_positive", "max_tries",
        ]
        for name in forbidden:
            assert name not in source

    @pytest.mark.asyncio
    async def test_days_times_per_day_forwarded_once(self, monkeypatch):
        from scripts import gen_risk_data_with_dates as module

        calls = []

        async def fake_generate(*, count, seed, clean, spread_days=None, live=False):
            calls.append((count, seed, clean, spread_days, live))
            return {"count": count}

        monkeypatch.setattr(module, "gen_train_dataset", fake_generate)
        result = await module.generate_risk_data_with_dates(7, 13, clean=True, seed=99)
        assert result == {"count": 91}
        assert calls == [(91, 99, True, 7, False)]

    def test_windows_stdout_is_utf8(self, source):
        assert 'sys.stdout.reconfigure(encoding="utf-8")' in source
