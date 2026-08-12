"""
旅游风控系统 - 一条龙命令 (从 0 到启动)
================
6 步:
  1. init_db.py --reset --yes          (DB + 种子数据 + 规则)
  2. gen_risky_users.py --count 30     (RISK 高风险演示用户)
  3. gen_train_dataset.py --reset      (1500 条严格标注训练数据)
  4. train_xgb_model.py                (训练 XGBoost)
  5. backfill_ml_score.py              (回填 ml_score)
  6. gen_risk_data_with_dates.py       (造今日业务数据, 仪表盘有内容)

用法:
  python scripts/one_command.py              # 跑全部 6 步
  python scripts/one_command.py --skip-init  # 跳过 1+2 (DB 已就绪)
  python scripts/one_command.py --skip-train # 跳过 3+4+5 (模型已训)
  python scripts/one_command.py --only-start # 只跑第 6 步
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable


def _run(step: int, cmd: list[str], desc: str) -> bool:
    print("\n" + "=" * 60)
    print(f"[步骤 {step}] {desc}")
    print(f"  命令: python {' '.join(cmd)}")
    print("=" * 60)
    result = subprocess.run([PYTHON, *cmd], cwd=ROOT)
    if result.returncode != 0:
        print(f"✗ 步骤 {step} 失败 (exit={result.returncode}), 流程中断")
        return False
    print(f"✓ 步骤 {step} 完成")
    return True


def main():
    parser = argparse.ArgumentParser(description="旅游风控系统一条龙命令")
    parser.add_argument("--skip-init", action="store_true", help="跳过 DB 初始化 + RISK 用户")
    parser.add_argument("--skip-train", action="store_true", help="跳过训练数据集 + 模型训练 + 回填")
    parser.add_argument("--only-start", action="store_true", help="只跑最后一步造数据")
    args = parser.parse_args()

    if args.only_start:
        steps = [(6, ["scripts/gen_risk_data_with_dates.py", "--days", "30", "--per-day", "20", "--clean"], "造近 30 天带日期评估数据")]
    elif args.skip_init and args.skip_train:
        steps = [(6, ["scripts/gen_risk_data_with_dates.py", "--days", "30", "--per-day", "20", "--clean"], "造近 30 天带日期评估数据")]
    else:
        steps = []
        if not args.skip_init:
            steps.append((1, ["scripts/init_db.py", "--drop", "--yes"], "初始化数据库 (删库重建)"))
            steps.append((2, ["scripts/gen_risky_users.py", "--count", "30"], "生成 30 个高风险演示用户"))
        if not args.skip_train:
            steps.append((3, ["scripts/gen_train_dataset.py", "--reset"], "生成严格标注训练数据集"))
            steps.append((4, ["scripts/train_xgb_model.py"], "训练 XGBoost 模型"))
            steps.append((5, ["scripts/backfill_ml_score.py"], "回填 ml_score"))
        steps.append((6, ["scripts/gen_risk_data_with_dates.py", "--days", "30", "--per-day", "20", "--clean"], "造近 30 天带日期评估数据"))

    print("旅游风控系统 - 一条龙命令")
    print(f"  项目根: {ROOT}")
    print(f"  Python: {PYTHON}")
    for step, cmd, desc in steps:
        if not _run(step, cmd, desc):
            sys.exit(1)

    print("\n" + "=" * 60)
    print("全部完成! 启动服务:")
    print("  python run_app.py")
    print("  浏览器打开 http://localhost:8000")
    print("=" * 60)


if __name__ == "__main__":
    main()
