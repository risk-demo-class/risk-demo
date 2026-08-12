"""
旅游行业风控系统 - 一条龙命令

工作流:
1. 重新生成旅游业务初始化数据 SQL
2. 初始化 MySQL 数据库
3. 调用风控引擎生成评估数据
4. 训练 XGBoost 模型
"""
import argparse
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")


def run_step(label: str, cmd: list[str]) -> None:
    print(f"\n{'=' * 70}")
    print(f"[{label}] {' '.join(cmd)}")
    print(f"{'=' * 70}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"{label} 失败: returncode={result.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="旅游行业风控系统一条龙初始化与训练")
    parser.add_argument("--skip-init", action="store_true", help="跳过数据库初始化")
    parser.add_argument("--skip-train", action="store_true", help="跳过 XGBoost 训练")
    parser.add_argument("--risk-count", type=int, default=300, help="生成风控评估条数")
    parser.add_argument("--min-rows", type=int, default=120, help="每张业务表最少原始数据条数")
    args = parser.parse_args()

    print("=" * 70)
    print("旅游行业风控系统 - 一条龙命令")
    print("=" * 70)
    print(f"工作目录: {ROOT}")
    print(f"Python: {sys.executable}")

    try:
        run_step("1/4 生成业务初始化数据", [
            sys.executable, os.path.join(SCRIPTS, "gen_business_data.py"),
            "--min-rows", str(args.min_rows),
        ])
        if not args.skip_init:
            run_step("2/4 初始化数据库", [
                sys.executable, os.path.join(SCRIPTS, "init_db.py"), "--reset", "--yes",
            ])
        else:
            print("[跳过] 2/4 初始化数据库")

        run_step("3/4 生成风控评估数据", [
            sys.executable, os.path.join(SCRIPTS, "gen_risk_data.py"),
            "--count", str(args.risk_count), "--mode", "mixed", "--reset-risk-data",
        ])

        if not args.skip_train:
            run_step("4/4 训练 XGBoost 模型", [
                sys.executable, os.path.join(SCRIPTS, "train_xgb_model.py"),
            ])
        else:
            print("[跳过] 4/4 训练 XGBoost 模型")
    except RuntimeError as exc:
        print(f"\n[FAIL] {exc}")
        sys.exit(1)

    print("\n完成。启动服务: python run_app.py")


if __name__ == "__main__":
    main()
