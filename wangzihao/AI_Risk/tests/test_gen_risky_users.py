"""Manufacturing business-data generator contract."""

from pathlib import Path
import subprocess
import sys

from scripts.gen_risky_users import MANUFACTURING_MODES, _mode_counts


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "gen_risky_users.py"


def test_cli_exposes_manufacturing_count_database_and_scoped_reset():
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, timeout=15)
    help_text = result.stdout.decode("utf-8", errors="replace")
    for option in ("--dealers", "--count", "--db", "--reset"):
        assert option in help_text


def test_six_manufacturing_modes_and_default_distribution():
    assert MANUFACTURING_MODES == (
        "normal_long", "normal_new", "risk_new_large",
        "risk_warranty", "risk_cross_region", "blacklisted",
    )
    assert _mode_counts(180) == {
        "normal_long": 60,
        "normal_new": 20,
        "risk_new_large": 40,
        "risk_warranty": 40,
        "risk_cross_region": 15,
        "blacklisted": 5,
    }


def test_generator_rejects_too_small_population():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--count", "0", "--db", "unused"],
        capture_output=True, timeout=15,
    )
    assert result.returncode != 0


def test_generator_uses_only_six_business_tables():
    source = SCRIPT.read_text(encoding="utf-8")
    for table in ("dealer", "device", "purchase_order", "warranty_claim",
                  "cross_region_report", "blacklist_extra"):
        assert table in source
    for old_table in ("user_info", "order_info", "order_detail", "postsale", "receive_info"):
        assert old_table not in source
