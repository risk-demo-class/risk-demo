"""The dated generator remains a manufacturing compatibility wrapper."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "gen_risk_data_with_dates.py"


def test_compatibility_cli_keeps_historical_arguments():
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, timeout=15)
    text = result.stdout.decode("utf-8", errors="replace")
    for option in ("--days", "--per-day", "--max-per-day", "--clean", "--start",
                   "--end", "--live", "--balance-pos", "--target-pos-ratio",
                   "--force-pos-ratio", "--db"):
        assert option in text


def test_wrapper_delegates_without_random_label_manipulation():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "generate_risk_data" in source
    assert "process_event" not in source
    assert "_pick_forced_" not in source
    assert "RISKY_USER_PREFIX" not in source


def test_wrapper_contains_no_ecommerce_tables():
    source = SCRIPT.read_text(encoding="utf-8")
    for old_table in ("user_info", "order_info", "order_detail", "postsale",
                      "receive_info", "logistics_complaint"):
        assert old_table not in source
