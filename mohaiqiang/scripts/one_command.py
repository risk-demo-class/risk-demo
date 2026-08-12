"""
物流风控系统 - 一条龙命令
从零开始, 一键完成数据库/业务数据/评估数据/模型训练, 最后提示启动服务.

【工作流 6 步】
  1. 重置数据库 (init_db.py --reset --yes, 含 24 条物流规则)
  2. 造物流业务数据 (gen_logistics_data.py --count 120, 至少 100 条运单)
  3. 造物流风控评估数据 (gen_logistics_risk_data.py --count 200 --clean-ml)
  4. 训练 XGBoost 模型 (train_xgb_model.py)
  5. 回填 ml_score 字段 (backfill_ml_score.py)
  6. 补充近期评估数据 (gen_logistics_risk_data.py --count 80)

【用法】
  python scripts/one_command.py                # 跑全部 6 步
  python scripts/one_command.py --skip-init     # 跳过 1+2 (DB + 业务数据已就绪)
  python scripts/one_command.py --skip-train    # 跳过 3+4+5 (评估数据 + 模型已就绪)
  python scripts/one_command.py --only-start    # 只跑第 6 步
"""
import argparse
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")


def _run_subprocess(label: str, cmd: list[str], cwd: str = None) -> int:
    print(f"\n{'=' * 70}")
    print(f"[{label}] {' '.join(cmd)}")
    print(f"{'=' * 70}")
    result = subprocess.run(cmd, cwd=cwd or ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"[{label}] 失败, returncode={result.returncode}")
    print(f"[{label}] OK")
    return result.returncode


def step_1_reset_db() -> None:
    _run_subprocess(
        "1/6 重置数据库 (init_db.py --reset --yes)",
        [sys.executable, os.path.join(SCRIPTS, "init_db.py"), "--reset", "--yes"],
    )


def step_2_business_data() -> None:
    _run_subprocess(
        "2/6 造物流业务数据 (gen_logistics_data.py --count 120)",
        [sys.executable, os.path.join(SCRIPTS, "gen_logistics_data.py"), "--count", "120"],
    )


def step_3_risk_data() -> None:
    _run_subprocess(
        "3/6 造物流风控评估数据 (gen_logistics_risk_data.py --count 200 --clean-ml)",
        [sys.executable, os.path.join(SCRIPTS, "gen_logistics_risk_data.py"),
         "--count", "200", "--clean-ml"],
    )


def step_4_train_xgboost() -> None:
    _run_subprocess(
        "4/6 训练 XGBoost 模型 (train_xgb_model.py)",
        [sys.executable, os.path.join(SCRIPTS, "train_xgb_model.py")],
    )


def step_5_backfill_ml_score() -> None:
    _run_subprocess(
        "5/6 回填 ml_score 字段 (backfill_ml_score.py)",
        [sys.executable, os.path.join(SCRIPTS, "backfill_ml_score.py")],
    )


def step_6_fresh_assessments() -> None:
    _run_subprocess(
        "6/6 补充近期评估数据 (gen_logistics_risk_data.py --count 80)",
        [sys.executable, os.path.join(SCRIPTS, "gen_logistics_risk_data.py"),
         "--count", "80"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="物流风控系统 - 一条龙命令 (6 步: 重置 → 业务数据 → 评估 → 训练 → 回填 → 补充)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--skip-init", action="store_true", help="跳过步骤 1+2")
    parser.add_argument("--skip-train", action="store_true", help="跳过步骤 3+4+5")
    parser.add_argument("--only-start", action="store_true", help="只跑步骤 6")
    args = parser.parse_args()

    print("=" * 70)
    print("物流风控系统 - 一条龙命令 (6 步全流程)")
    print("=" * 70)
    print(f"工作目录: {ROOT}")
    print(f"Python:    {sys.executable}")

    try:
        if args.only_start:
            step_6_fresh_assessments()
        else:
            if not args.skip_init:
                step_1_reset_db()
                step_2_business_data()
            else:
                print("[跳过] 1+2: DB 和物流业务数据已就绪")
            if not args.skip_train:
                step_3_risk_data()
                step_4_train_xgboost()
                step_5_backfill_ml_score()
            else:
                print("[跳过] 3+4+5: 评估数据 + 模型已就绪")
            step_6_fresh_assessments()
    except RuntimeError as e:
        print(f"\n[FAIL] 步骤失败, 中断: {e}")
        print("排查建议: 检查 MySQL/`.env`, 或分步跑 (--skip-init / --skip-train)")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("一条龙完成!")
    print("下一步: python run_app.py")
    print("访问: http://localhost:8000")
    print("=" * 70)


if __name__ == "__main__":
    main()
