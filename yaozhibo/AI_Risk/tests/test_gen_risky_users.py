"""旧高风险用户入口必须转发到教育A～F数据生成器。"""
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gen_risky_users.py"


def test_help_exposes_count_reset_and_seed():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0
    for option in ("--count", "--reset", "--seed"):
        assert option in result.stdout


def test_script_delegates_to_education_generator():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "generate_business_data" in source
    assert "postsale" not in source.lower()
