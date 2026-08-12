"""
华信银行·信贷风控系统 - 一条龙命令 (P4-L4 2026-08-08)
从零开始, 一键完成所有准备 + 训练, 最后启动 Web 服务.

【工作流 6 步】
  1. 重置数据库 (init_db.py --reset --yes, 含 30 条规则 R101-R604)
  2. 造 5000 客户 / 3 万贷款申请业务数据 (gen_10w_data.py, 80/15/5 风险分层, 含逾期/投诉)
  3. 造 3000 条 PD 强标注训练数据 (gen_train_dataset.py --reset, 标签=客户逾期事实)
  4. 训练 XGBoost PD 违约概率模型 (train_xgb_model.py)
  5. 回填 ml_score 字段 (backfill_ml_score.py, 用训好的模型推理)
  6. 打印启动指引 (run_app.py 一键启动, 不自动拉起服务)

【用法】
  python scripts/one_command.py                # 跑全部 6 步
  python scripts/one_command.py --skip-init     # 跳过 1+2, 假设 DB 和业务数据已就绪
  python scripts/one_command.py --skip-train    # 跳过 3+4+5, 假设训练数据 + 模型已就绪
  python scripts/one_command.py --only-start    # 只打印启动指引
"""
import argparse
import asyncio
import os
import subprocess
import sys

# UTF-8 stdout (Windows GBK 兼容)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 项目根目录 (one_command.py 所在目录的父目录)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")


def _run_subprocess(label: str, cmd: list[str], cwd: str = None,
                    env: dict = None) -> int:
    """跑一个子进程, 实时打印 stdout/stderr, 失败抛 RuntimeError.

    Args:
        label: 步骤名 (打印用)
        cmd: 命令 list (跟 subprocess.run 一致)
        cwd: 工作目录
        env: 额外环境变量 (合并到 os.environ)

    Returns:
        returncode
    """
    print(f"\n{'=' * 70}")
    print(f"[{label}] {' '.join(cmd)}")
    print(f"{'=' * 70}")
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    result = subprocess.run(cmd, cwd=cwd or ROOT, env=full_env)
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


def step_2_biz_data() -> None:
    """步骤 2: 造 5000 客户 / 3 万贷款申请业务数据 (80/15/5 风险分层)."""
    # 中文路径下 import app 需要 PYTHONPATH=项目根目录
    _run_subprocess(
        "2/6 造业务数据 (gen_10w_data.py: 5000 客户/3 万申请)",
        [sys.executable, os.path.join(SCRIPTS, "gen_10w_data.py")],
        env={"PYTHONPATH": ROOT},
    )


def step_3_train_dataset() -> None:
    """步骤 3: 造 3000 条 PD 强标注训练数据 (60 逾期 + 60 正常客户 × 25, ml_score=NULL)."""
    _run_subprocess(
        "3/6 造 3000 条 PD 训练数据 (gen_train_dataset.py --reset)",
        [sys.executable, os.path.join(SCRIPTS, "gen_train_dataset.py"), "--reset"],
    )


def step_4_train_xgboost() -> None:
    """步骤 4: 训练 XGBoost 模型 (val_auc / val_f1 / best_iter)."""
    _run_subprocess(
        "4/6 训练 XGBoost 模型 (train_xgb_model.py)",
        [sys.executable, os.path.join(SCRIPTS, "train_xgb_model.py")],
    )


def step_5_backfill_ml_score() -> None:
    """步骤 5: 用训好的 XGBoost 推理回填 risk_assessment.ml_score."""
    _run_subprocess(
        "5/6 回填 ml_score 字段 (backfill_ml_score.py)",
        [sys.executable, os.path.join(SCRIPTS, "backfill_ml_score.py")],
    )


def step_6_start_hint() -> None:
    """步骤 6: 打印启动指引 (不自动拉起服务, 避免端口/环境差异)."""
    print("\n" + "=" * 70)
    print("[6/6] 启动指引 (请手动执行)")
    print("=" * 70)
    print("  python run_app.py                          # 一键启动 (6 步自检 + 输入确认)")
    print("  DB_PORT=3307 .venv/bin/python scripts/main.py   # 直接启动 (docker 3307 场景, 开发用)")
    print("  浏览器访问 http://localhost:8000            # 仪表盘/案件/评估/规则/黑名单/风险检查")
    print("  Swagger 文档: http://localhost:8000/docs")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="华信银行·信贷风控系统 - 一条龙命令 (6 步: 重置 → 业务数据 → PD 训练数据 → 训练 → 回填 → 启动指引)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/one_command.py                # 跑完全部 6 步
  python scripts/one_command.py --skip-init     # 跳过 1+2 (DB + 业务数据已就绪)
  python scripts/one_command.py --skip-train   # 跳过 3+4+5 (训练数据 + 模型已就绪)
  python scripts/one_command.py --only-start   # 只打印启动指引
        """,
    )
    parser.add_argument("--skip-init", action="store_true",
                        help="跳过步骤 1+2 (DB + 业务数据已就绪)")
    parser.add_argument("--skip-train", action="store_true",
                        help="跳过步骤 3+4+5 (训练数据 + 模型已就绪)")
    parser.add_argument("--only-start", action="store_true",
                        help="只打印启动指引, 不重置/训练")
    args = parser.parse_args()

    print("=" * 70)
    print("华信银行·信贷风控系统 - 一条龙命令 (6 步全流程)")
    print("=" * 70)
    print(f"工作目录: {ROOT}")
    print(f"Python:    {sys.executable}")
    print()

    try:
        if args.only_start:
            # 只打印启动指引
            step_6_start_hint()
        else:
            # 步骤 1+2: 重置 DB + 业务数据
            if not args.skip_init:
                step_1_reset_db()
                step_2_biz_data()
            else:
                print("[跳过] 1+2: DB 和业务数据已就绪")

            # 步骤 3+4+5: 训练数据 + 训练 + 回填
            if not args.skip_train:
                step_3_train_dataset()
                step_4_train_xgboost()
                step_5_backfill_ml_score()
            else:
                print("[跳过] 3+4+5: 训练数据 + 模型已就绪")

            # 步骤 6: 启动指引
            step_6_start_hint()

    except RuntimeError as e:
        print(f"\n[FAIL] 步骤失败, 中断: {e}")
        print("=" * 70)
        print("排查建议:")
        print("  1. 检查 MySQL: docker exec -it risk-mysql mysql -uroot -p123321")
        print("     (或 .env 里 DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME 指向的实例)")
        print("  2. gen_10w_data.py 需在项目根目录跑 (PYTHONPATH 已自动注入)")
        print("  3. 分步跑 (--skip-init / --skip-train 跳过已完成的)")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("一条龙完成!")
    print("=" * 70)
    print("下一步:")
    print("  按上面的启动指引执行 run_app.py 即可启动 Web 服务")
    print("  浏览器访问 http://localhost:8000            # 仪表盘/案件/评估/规则/黑名单/风险检查")
    print()
    print("造数据脚本 (可选):")
    print("  python scripts/gen_10w_data.py              # 5000 客户 / 3 万贷款申请 (默认)")
    print("  python scripts/gen_10w_data.py --users 10000 --loans 60000 --batch 5000")
    print("=" * 70)


if __name__ == "__main__":
    main()
