"""旧日期入口必须安全转发到教育生成器。"""
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gen_risk_data_with_dates.py"


def test_help_is_available_without_database():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0
    for option in ("--days", "--per-day", "--seed"):
        assert option in result.stdout


def test_compatibility_entry_uses_education_generator():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "generate_business_data" in source
    assert "OrderDetail" not in source
    assert "Postsale" not in source
