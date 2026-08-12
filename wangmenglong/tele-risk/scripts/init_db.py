"""
电信风控系统 - 建库建表脚本
==========================
在 ai_risk 的 docker MySQL 中创建 telecom 库 + 13 张业务表.
幂等: 可重复跑 (DROP IF EXISTS + CREATE).

用法:
  python scripts/init_db.py            # 建库 + 建表
  python scripts/init_db.py --yes      # 跳过确认

连接: 默认 localhost:3306 root/123321 (复用 ai_risk 的 docker MySQL).
      可用环境变量覆盖: DB_HOST / DB_PORT / DB_USER / DB_PASSWORD.
"""
import os
import sys

import pymysql

# 让脚本独立可跑 (不依赖 app.config, 避免触发 pydantic-settings 依赖)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123321")

# SQL 文件路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_FILES = [
    os.path.join(_PROJECT_ROOT, "sql", "init_telecom_tables.sql"),
    os.path.join(_PROJECT_ROOT, "sql", "init_risk_tables.sql"),
]


def _split_statements(sql_text: str) -> list[str]:
    """把 SQL 文件切成可执行语句.

    规则:
      - 按 ';\n' 切 (DDL 体内不含分号+换行, 安全)
      - 丢掉 -- 开头的注释行
      - 丢掉空白语句
    """
    statements = []
    for raw in sql_text.split(";\n"):
        lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            statements.append(stmt)
    return statements


def main(yes: bool = False) -> None:
    print("=" * 60)
    print("电信风控系统 - 建库建表")
    print(f"  MySQL: {DB_USER}@{DB_HOST}:{DB_PORT}")
    for f in SQL_FILES:
        print(f"  SQL:   {f}")
    print("=" * 60)

    if not yes:
        try:
            input(f"即将 DROP + CREATE telecom 库 (业务表+风控表), 回车继续 (Ctrl+C 取消)... ")
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            sys.exit(0)

    # 1. 连 MySQL (不指定库, 因为要 CREATE DATABASE)
    try:
        conn = pymysql.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
            charset="utf8mb4", autocommit=True,
        )
    except Exception as e:
        print(f"[FAIL] MySQL 连不上: {e}")
        print("       检查 ai_risk 的 docker MySQL 是否在跑 (docker ps | findstr risk-mysql)")
        sys.exit(1)

    executed = 0
    with conn.cursor() as cur:
        for sql_file in SQL_FILES:
            if not os.path.exists(sql_file):
                print(f"[WARN] SQL 文件不存在: {sql_file}")
                continue
            with open(sql_file, "r", encoding="utf-8") as f:
                sql_text = f.read()
            statements = _split_statements(sql_text)
            print(f"\n  处理 {os.path.basename(sql_file)}: {len(statements)} 条语句")
            for stmt in statements:
                head = stmt.lstrip().upper()
                if head.startswith("SELECT"):
                    continue
                try:
                    cur.execute(stmt)
                    executed += 1
                except Exception as e:
                    print(f"[WARN] 语句执行失败: {e}")
                    print(f"       语句前 80 字: {stmt[:80]}...")

        # 2. 校验: 列出 telecom 库的所有表
        cur.execute(
            "SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA='telecom' ORDER BY TABLE_NAME"
        )
        tables = cur.fetchall()
    conn.close()

    print(f"\n[OK] 执行完成 ({executed} 条 DDL)")
    print(f"[OK] telecom 库现有 {len(tables)} 张表:")
    for name, rows in tables:
        print(f"       - {name:<32} (rows≈{rows})")
    print("=" * 60)
    print("[OK] 建库建表完成. 下一步: python scripts/gen_telecom_data.py")


if __name__ == "__main__":
    _yes = "--yes" in sys.argv or "-y" in sys.argv
    main(yes=_yes)
