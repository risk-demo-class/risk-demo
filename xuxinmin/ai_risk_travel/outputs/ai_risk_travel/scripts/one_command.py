"""
旅游风控系统 - 一条龙命令
从零开始, 一键完成初始化 → 造数据 → 训练 → 启动.

【工作流 6 步】
  1. 重置数据库 (init_db.py --reset --yes, 含 11 条行业规则 + 黑名单种子)
  2. 造行业业务数据 (gen_business_data.py, 40 用户含 7 个 RISK 高风险用户)
  3. 造评估/训练数据 (gen_risk_data.py --balance-pos --target-pos-ratio 0.30)
  4. 训练 XGBoost 模型 (train_xgb_model.py)
  5. 造按日期分布的评估数据 (gen_risk_data_with_dates.py, 仪表盘趋势)
  6. 造今日业务数据 (gen_risk_data_with_dates.py --live, 演示页面立刻有数据)

【用法】
  python scripts/one_command.py                # 跑全部 6 步
  python scripts/one_command.py --skip-init     # 跳过 1+2 (DB + 业务数据已就绪)
  python scripts/one_command.py --skip-train   # 跳过 3+4 (评估数据 + 模型已就绪)
  python scripts/one_command.py --only-start   # 只跑第 6 步 (造今日业务数据)
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
    """步骤 1: 重置数据库 (--reset --yes 自动确认)."""
    _run_subprocess(
        "1/6 重置数据库 (init_db.py --reset --yes)",
        [sys.executable, os.path.join(SCRIPTS, "init_db.py"), "--reset", "--yes"],
    )


def step_2_business_data() -> None:
    """步骤 2: 造行业业务数据 (含 7 个 RISK 高风险用户)."""
    _run_subprocess(
        "2/6 造行业业务数据 (gen_business_data.py --count 40)",
        [sys.executable, os.path.join(SCRIPTS, "gen_business_data.py"), "--count", "40"],
    )


def step_3_train_dataset() -> None:
    """步骤 3: 造评估/训练数据 (正例比例拉到 30%)."""
    _run_subprocess(
        "3/6 造评估/训练数据 (gen_risk_data.py --count 150 --balance-pos --target-pos-ratio 0.30)",
        [sys.executable, os.path.join(SCRIPTS, "gen_risk_data.py"),
         "--count", "150", "--balance-pos", "--target-pos-ratio", "0.30"],
    )


def step_4_train_xgboost() -> None:
    """步骤 4: 训练 XGBoost 模型 (val_auc / val_f1 / best_iter)."""
    _run_subprocess(
        "4/6 训练 XGBoost 模型 (train_xgb_model.py)",
        [sys.executable, os.path.join(SCRIPTS, "train_xgb_model.py")],
    )


def step_5_dated_data() -> None:
    """步骤 5: 造按日期分布的评估数据 (仪表盘趋势)."""
    _run_subprocess(
        "5/6 造按日期分布评估数据 (gen_risk_data_with_dates.py --days 7 --per-day 20)",
        [sys.executable, os.path.join(SCRIPTS, "gen_risk_data_with_dates.py"),
         "--days", "7", "--per-day", "20"],
    )


def step_6_business_today() -> None:
    """步骤 6: 造今日业务数据 (演示页面立刻有数据)."""
    _run_subprocess(
        "6/6 造今日业务数据 (gen_risk_data_with_dates.py --days 1 --per-day 50 --live)",
        [sys.executable, os.path.join(SCRIPTS, "gen_risk_data_with_dates.py"),
         "--days", "1", "--per-day", "50", "--live"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="旅游风控系统 - 一条龙命令 (6 步: 重置 → 业务数据 → 评估数据 → 训练 → 趋势 → 今日)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/one_command.py                # 跑完全部 6 步
  python scripts/one_command.py --skip-init     # 跳过 1+2 (DB + 业务数据已就绪)
  python scripts/one_command.py --skip-train   # 跳过 3+4 (评估数据 + 模型已就绪)
  python scripts/one_command.py --only-start   # 只跑步骤 6 (造今日业务数据)
        """,
    )
    parser.add_argument("--skip-init", action="store_true",
                        help="跳过步骤 1+2 (DB + 业务数据已就绪)")
    parser.add_argument("--skip-train", action="store_true",
                        help="跳过步骤 3+4 (评估数据 + 模型已就绪)")
    parser.add_argument("--only-start", action="store_true",
                        help="只跑步骤 6 (造今日业务数据, 不重置/训练)")
    args = parser.parse_args()

    print("=" * 70)
    print("旅游风控系统 - 一条龙命令 (6 步全流程)")
    print("=" * 70)
    print(f"工作目录: {ROOT}")
    print(f"Python:    {sys.executable}")
    print()

    try:
        if args.only_start:
            step_6_business_today()
        else:
            if not args.skip_init:
                step_1_reset_db()
                step_2_business_data()
            else:
                print("[跳过] 1+2: DB 和业务数据已就绪")

            if not args.skip_train:
                step_3_train_dataset()
                step_4_train_xgboost()
            else:
                print("[跳过] 3+4: 评估数据 + 模型已就绪")

            step_5_dated_data()
            step_6_business_today()

    except RuntimeError as e:
        print(f"\n[FAIL] 步骤失败, 中断: {e}")
        print("=" * 70)
        print("排查建议:")
        print("  1. 检查 MySQL 是否启动 (默认 localhost:3306)")
        print("  2. 检查 .env 配置 (DB_HOST/DB_USER/DB_PASSWORD/DB_NAME)")
        print("  3. 分步跑 (--skip-init / --skip-train 跳过已完成的)")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("一条龙完成!")
    print("=" * 70)
    print("下一步:")
    print("  python run_app.py                          # 启动 Web 服务")
    print("  浏览器访问 http://localhost:8000            # 仪表盘/案件/评估/规则/黑名单/风险检查")
    print()
    print("造数据脚本:")
    print("  python scripts/gen_business_data.py --count 40")
    print("  python scripts/gen_risk_data.py --count 200 --balance-pos --target-pos-ratio 0.30")
    print("  python scripts/gen_risk_data_with_dates.py --days 1 --per-day 100 --live")
    print("=" * 70)


if __name__ == "__main__":
    main()
