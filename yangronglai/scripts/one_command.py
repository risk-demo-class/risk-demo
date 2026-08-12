"""Stage-aware one-command entry point.

Application startup creates missing tables, seeds mandatory rules and demo data,
then loads or automatically trains the five registered models.
"""

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    return subprocess.call([sys.executable, str(ROOT / "run_app.py"), *sys.argv[1:]], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
