"""串联第 4 阶段非破坏性流水线；不会自动删表或覆盖已有批量前缀。"""

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_step(title: str, arguments: list[str]) -> None:
    print(f"\n{'=' * 16} {title} {'=' * 16}")
    subprocess.run([sys.executable, *arguments], cwd=PROJECT_ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="银行批量数据→评估→训练→回填")
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--transactions", type=int, default=20_000)
    parser.add_argument("--candidates", type=int, default=2000)
    parser.add_argument("--risk-ratio", type=float, default=0.28)
    parser.add_argument("--prefix", default="BG")
    args = parser.parse_args()
    run_step(
        "1/5 生成银行业务数据",
        ["scripts/gen_bank_data.py", "--users", str(args.users),
         "--transactions", str(args.transactions), "--candidates", str(args.candidates),
         "--risk-ratio", str(args.risk_ratio), "--prefix", args.prefix],
    )
    run_step("2/5 检查八类风险人物", ["scripts/gen_risky_users.py"])
    run_step("3/5 真实跨日期评估", ["scripts/gen_risk_data_with_dates.py"])
    run_step("4/5 训练数据纯度校验", ["scripts/gen_train_dataset.py"])
    run_step("5/5 训练 XGBoost", ["scripts/train_xgb_model.py"])
    print("\n流水线完成。可选执行：uv run python scripts/backfill_ml_score.py")


if __name__ == "__main__":
    main()
