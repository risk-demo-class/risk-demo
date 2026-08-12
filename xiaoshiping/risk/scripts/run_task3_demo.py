"""任务 3 端到端演示：初始化、训练、执行高风险检查。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / script)], check=True)


if __name__ == "__main__":
    run("init_db.py")
    run("gen_training_data.py")
    run("train_xgb_model.py")
    from app.service.event import run_risk_check

    for work_order_id in ("WO0016", "WO0019", "WO0023"):
        result = run_risk_check(work_order_id)
        print(work_order_id, result["decision"], result["final_score"], len(result["rule_hits"]))
