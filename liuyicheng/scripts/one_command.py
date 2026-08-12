"""银行风控项目的一条龙教学命令。

默认仅启动服务；显式传 --prepare 才执行数据生成与模型训练，
显式再传 --reset 才删除并重建目标数据库。
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(script: str, *args: str) -> None:
    command = [sys.executable, "-u", str(ROOT / "scripts" / script), *args]
    print("\n$", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="银行智能风控系统：准备数据、训练并启动")
    parser.add_argument("--prepare", action="store_true", help="执行初始化、造数和训练")
    parser.add_argument("--reset", action="store_true", help="配合 --prepare 删除并重建 bank_risk")
    parser.add_argument("--skip-train", action="store_true")
    parser.add_argument("--skip-backfill", action="store_true", help="训练后不回填ML评分")
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--days", type=int, default=7, help="评估与案件分布天数")
    parser.add_argument("--samples", type=int, default=1000, help="生成数和训练读取数")
    parser.add_argument("--business-count", type=int, default=300, help="额外生成的银行交易流水数")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.reset and not args.prepare:
        parser.error("--reset 必须与 --prepare 一起使用")
    if not 1 <= args.days <= 365:
        parser.error("--days 必须在 1~365 之间")
    if args.samples < 50:
        parser.error("--samples 必须 >= 50")
    if args.business_count < 100:
        parser.error("--business-count 必须 >= 100")
    if args.prepare:
        init_args = ["--reset", "--yes"] if args.reset else ["--keep-data"]
        run("init_db.py", *init_args)
        run("gen_business_data.py", "--count", str(args.business_count), "--seed", str(args.seed))
        run(
            "gen_train_dataset.py", "--repeats", "12", "--seed", str(args.seed),
            "--samples", str(args.samples), "--days", str(args.days),
        )
        if not args.skip_train:
            run("train_xgb_model.py", "--samples", str(args.samples))
            if not args.skip_backfill:
                run("backfill_ml_score.py")
    if not args.no_start:
        run("main.py")


if __name__ == "__main__":
    main()
