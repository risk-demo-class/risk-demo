"""物流风控系统一条龙：初始化 → 生成快照 → 训练 → 启动。"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")


def _run(label: str, *args: str) -> None:
    cmd = [sys.executable, *args]
    print(f"\n[{label}] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode:
        raise RuntimeError(f"{label} 失败，returncode={result.returncode}")


def main():
    parser = argparse.ArgumentParser(description="物流风控一条龙初始化与训练")
    parser.add_argument("--skip-init", action="store_true")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--start", action="store_true", help="完成后启动 Web 服务")
    args = parser.parse_args()

    if not args.skip_init:
        _run("1/4 初始化 logistics_risk", os.path.join(SCRIPTS, "init_db.py"), "--reset", "--yes")
    _run("2/4 生成物流特征快照", os.path.join(SCRIPTS, "gen_train_dataset.py"), "--reset")
    if not args.skip_train:
        _run("3/4 训练物流 XGBoost", os.path.join(SCRIPTS, "train_xgb_model.py"))
    else:
        print("[跳过] 3/4 模型训练")
    if args.start:
        _run("4/4 启动服务", os.path.join(ROOT, "run_app.py"))
    else:
        print("[4/4] 完成。运行 python run_app.py 启动服务。")


if __name__ == "__main__":
    main()
