"""按顺序执行制造业风控数据库初始化。"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = PROJECT_ROOT / "sql"
SQL_FILES = (
    "init_database.sql",
    "init_business_tables.sql",
    "init_business_data.sql",
    "init_risk_tables.sql",
    "init_risk_data.sql",
)


def find_mysql() -> str:
    candidates = [shutil.which("mysql"), r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise FileNotFoundError("未找到 mysql 客户端，请将 mysql.exe 加入 PATH 后重试。")


def execute_file(mysql: str, filename: str, args: argparse.Namespace) -> None:
    path = SQL_DIR / filename
    command = [mysql, f"--host={args.host}", f"--port={args.port}", f"--user={args.user}", f"--password={args.password}"]
    print(f"[SQL] {filename}")
    with path.open("rb") as sql_input:
        result = subprocess.run(command, stdin=sql_input, check=False)
    if result.returncode:
        raise RuntimeError(f"执行失败：{filename}")


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化 manufacturing_risk：数据库、业务表/数据、风控表/数据")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="123456")
    parser.add_argument("--skip-validation", action="store_true", help="跳过初始化后的业务数据校验")
    args = parser.parse_args()
    mysql = find_mysql()
    print(f"初始化目标：{args.user}@{args.host}:{args.port}/manufacturing_risk")
    for filename in SQL_FILES:
        execute_file(mysql, filename, args)
    if not args.skip_validation:
        command = [sys.executable, str(PROJECT_ROOT / "scripts" / "gen_business_data.py"), "--validate-only"]
        print("[CHECK] 业务数据校验")
        subprocess.run(command, check=True)
    print("初始化完成：业务表、业务数据、风控表、风险规则和风险事件均已写入。")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"初始化失败：{error}", file=sys.stderr)
        raise SystemExit(1) from error
