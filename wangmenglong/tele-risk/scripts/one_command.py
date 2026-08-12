"""
电信风控系统 - 一条龙命令

从零开始, 一键完成建库 → 造数 → 训练 → 造评估数据, 最后启动 Web 服务.

【工作流 5 步】
  1. 建库建表 (init_db.py --yes, 24 张表 + 15 条规则)
  2. 造业务数据 (gen_telecom_data.py, 299 张号卡: 60 风险 + 239 正常)
  3. 训练 XGBoost (train_xgb_model.py, 30 维特征)
  4. 批量风控检查 (batch_risk_check.py, 299 次评估)
  5. 启动 Web 服务 (run_app.py, 端口 8001)

【用法】
  python scripts/one_command.py              # 跑全部 5 步, 最后启服务
  python scripts/one_command.py --skip-init   # 跳过 1+2 (DB + 数据已就绪)
  python scripts/one_command.py --skip-train   # 跳过 3 (模型已就绪)
  python scripts/one_command.py --skip-batch   # 跳过 4 (已有评估数据)
  python scripts/one_command.py --skip-server  # 不启服务 (跑完前 4 步)
"""
import argparse
import os
import subprocess
import sys
import time

# UTF-8 stdout (Windows GBK 兼容)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
VENV_PYTHON = os.path.join(ROOT, ".venv", "Scripts", "python.exe")


def _run(label: str, cmd: list[str], timeout: int = 300) -> int:
    print(f"\n{'=' * 70}")
    print(f"[{label}] {' '.join(cmd)}")
    print(f"{'=' * 70}")
    result = subprocess.run(cmd, cwd=ROOT, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"[{label}] 失败, returncode={result.returncode}")
    print(f"[{label}] OK")
    return result.returncode


def step_1_init_db() -> None:
    _run("1/5 建库建表 (init_db.py --yes)", [VENV_PYTHON, os.path.join(SCRIPTS, "init_db.py"), "--yes"], timeout=30)


def step_2_gen_data() -> None:
    _run("2/5 造业务数据 (gen_telecom_data.py)", [VENV_PYTHON, os.path.join(SCRIPTS, "gen_telecom_data.py")], timeout=60)


def step_3_train() -> None:
    _run("3/5 训练 XGBoost (train_xgb_model.py)", [VENV_PYTHON, os.path.join(SCRIPTS, "train_xgb_model.py")], timeout=120)


def step_4_batch_check() -> None:
    _run("4/5 批量风控检查 (batch_risk_check.py, 299 张号卡)", [VENV_PYTHON, os.path.join(SCRIPTS, "batch_risk_check.py")], timeout=300)


def step_5_start_server() -> None:
    print(f"\n{'=' * 70}")
    print("5/5 启动 Web 服务 (run_app.py, 端口 8001)")
    print(f"{'=' * 70}")
    print("服务已启动, 访问 http://localhost:8001")
    print("按 Ctrl+C 停止")
    time.sleep(2)
    os.execv(sys.executable, [sys.executable, os.path.join(ROOT, "run_app.py")])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="电信风控系统 - 一条龙命令 (5 步: 建库→造数→训练→评估→启服务)",
    )
    parser.add_argument("--skip-init", action="store_true", help="跳过 1+2 (DB + 数据已就绪)")
    parser.add_argument("--skip-train", action="store_true", help="跳过 3 (模型已就绪)")
    parser.add_argument("--skip-batch", action="store_true", help="跳过 4 (已有评估数据)")
    parser.add_argument("--skip-server", action="store_true", help="不启服务 (跑完前 4 步)")
    args = parser.parse_args()

    print("=" * 70)
    print("电信风控系统 - 一条龙命令 (5 步全流程)")
    print("=" * 70)
    print(f"工作目录: {ROOT}")
    print(f"Python:    {VENV_PYTHON}")
    print()

    try:
        if not args.skip_init:
            step_1_init_db()
            step_2_gen_data()
        else:
            print("[跳过] 1+2: 建库建表 + 造数据已就绪")

        if not args.skip_train:
            step_3_train()
        else:
            print("[跳过] 3: XGBoost 模型已就绪")

        if not args.skip_batch:
            step_4_batch_check()
        else:
            print("[跳过] 4: 批量风控检查已就绪")

        if not args.skip_server:
            step_5_start_server()
        else:
            print("[跳过] 5: 不启动 Web 服务")

    except RuntimeError as e:
        print(f"\n[FAIL] 步骤失败, 中断: {e}")
        print("=" * 70)
        print("排查建议:")
        print("  1. 检查 MySQL 是否启动 (默认 localhost:3306, root/123321)")
        print("  2. 分步跑 (--skip-init / --skip-train 跳过已完成的)")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("一条龙完成!")
    print("=" * 70)
    print("下一步:")
    print("  python run_app.py                              # 启动 Web 服务")
    print("  浏览器访问 http://localhost:8001               # 仪表盘/风控检查/规则/案件/评估/黑名单")
    print()
    print("快速验证:")
    print("  python scripts/smoke_test.py                   # 50 条请求冒烟测试")
    print("  python scripts/batch_risk_check.py             # 再次跑全量风控检查")
    print("=" * 70)


if __name__ == "__main__":
    main()