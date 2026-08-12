"""在线教育风控一条龙：初始化 -> 生成训练事件 -> 训练XGBoost -> 回填ML评分。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(label: str, *args: str) -> None:
    cmd = [sys.executable, *args]
    print("=" * 70)
    print(f"[{label}] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode:
        raise SystemExit(f"{label}失败，returncode={result.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="教育风控一条龙命令")
    parser.add_argument("--skip-init", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--events", type=int, default=500)
    args = parser.parse_args()

    if not args.skip_init:
        _run("初始化数据库", str(SCRIPTS / "init_db.py"), "--reset", "--yes")
    _run("生成教育业务并跑风控", str(SCRIPTS / "gen_train_dataset.py"), "--events", str(args.events), "--reset")
    if not args.skip_train:
        _run("训练XGBoost", str(SCRIPTS / "train_xgb_model.py"))
        _run("回填ML评分", str(SCRIPTS / "backfill_ml_score.py"))
    print("教育风控一条龙完成")


if __name__ == "__main__":
    main()
