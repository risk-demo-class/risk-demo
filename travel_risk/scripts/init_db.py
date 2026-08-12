"""
旅游风控系统 - 一键数据库初始化脚本
按顺序执行: 创建数据库 → 18 张业务表 → 业务测试数据 → 9 张风控表 → 30 条预置规则

用法:
  python scripts/init_db.py            # 建库建表 (幂等)
  python scripts/init_db.py --drop     # 先删库再建 (危险, 清空所有数据)
  python scripts/init_db.py --yes      # 跳过确认
"""
import argparse
import os
import sys

import pymysql

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(BASE_DIR, "sql")

SQL_FILES = [
    ("init_business_tables.sql", "创建 18 张旅游业务表"),
    ("init_business_data.sql", "导入业务测试数据"),
    ("init_risk_tables.sql", "创建 9 张风控表"),
    ("init_risk_data.sql", "导入 30 条预置风控规则 (R001-R030)"),
]


def get_config() -> dict:
    """从 .env 或环境变量读取数据库配置."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(BASE_DIR, ".env"))
    except ImportError:
        pass
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", "123321"),
        "db": os.getenv("DB_NAME", "travel_risk"),
    }


def connect_server(cfg: dict):
    """连接 MySQL 服务器 (不指定库)."""
    return pymysql.connect(
        host=cfg["host"], port=cfg["port"], user=cfg["user"],
        password=cfg["password"], charset="utf8mb4", autocommit=True,
    )


def connect_database(cfg: dict):
    """连接指定数据库 (执行建表/数据 SQL 用)."""
    return pymysql.connect(
        host=cfg["host"], port=cfg["port"], user=cfg["user"],
        password=cfg["password"], database=cfg["db"],
        charset="utf8mb4", autocommit=True,
    )


def create_database(conn, db_name: str, drop_first: bool = False):
    """创建数据库 (utf8mb4)."""
    with conn.cursor() as cur:
        if drop_first:
            print(f"  [WARN] 删除数据库 {db_name} ...")
            cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        )
    print(f"  数据库 {db_name} 已就绪")


def split_sql_statements(sql_text: str) -> list[str]:
    """将 SQL 文本拆分为独立语句, 处理字符串中的分号."""
    statements = []
    current = []
    in_single_quote = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    chars = sql_text
    while i < len(chars):
        c = chars[i]
        if not in_single_quote and not in_block_comment and c == "-" and i + 1 < len(chars) and chars[i + 1] == "-":
            in_line_comment = True
            i += 2
            continue
        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue
        if not in_single_quote and not in_line_comment and c == "/" and i + 1 < len(chars) and chars[i + 1] == "*":
            in_block_comment = True
            i += 2
            continue
        if in_block_comment:
            if c == "*" and i + 1 < len(chars) and chars[i + 1] == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if c == "'":
            in_single_quote = not in_single_quote
            current.append(c)
            i += 1
            continue
        if c == ";" and not in_single_quote:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        current.append(c)
        i += 1
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


def execute_sql_file(conn, filepath: str, description: str) -> int:
    """执行单个 SQL 脚本文件, 返回错误数."""
    filename = os.path.basename(filepath)
    print(f"\n[{filename}] {description}")
    with open(filepath, "r", encoding="utf-8") as f:
        sql_content = f.read()
    statements = split_sql_statements(sql_content)
    errors = 0
    with conn.cursor() as cur:
        for stmt in statements:
            try:
                cur.execute(stmt)
            except pymysql.MySQLError as e:
                code = e.args[0] if e.args else 0
                # 1051 = Unknown table (DROP IF EXISTS 正常) / 1062 = Duplicate entry (幂等)
                if code in (1051, 1062):
                    continue
                errors += 1
                print(f"  警告 [{code}]: {str(e)[:150]}")
    status = "完成" if errors == 0 else f"完成 (失败 {errors})"
    print(f"  共 {len(statements)} 条语句, {status}")
    return errors


def main():
    parser = argparse.ArgumentParser(description="旅游风控系统数据库初始化")
    parser.add_argument("--drop", action="store_true", help="先删库再建 (危险)")
    parser.add_argument("--yes", action="store_true", help="跳过确认")
    args = parser.parse_args()

    cfg = get_config()
    print("=" * 60)
    print(f"旅游风控系统 - 数据库初始化")
    print(f"  {cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['db']}")
    print("=" * 60)

    if args.drop and not args.yes:
        ans = input(f"确认删除数据库 {cfg['db']} 并重建? (yes/NO): ").strip().lower()
        if ans != "yes":
            print("已取消")
            return

    conn = connect_server(cfg)
    try:
        create_database(conn, cfg["db"], drop_first=args.drop)
    finally:
        conn.close()

    conn = connect_database(cfg)
    try:
        total_errors = 0
        for filename, desc in SQL_FILES:
            total_errors += execute_sql_file(conn, os.path.join(SQL_DIR, filename), desc)
        print("\n" + "=" * 60)
        if total_errors == 0:
            print("数据库初始化完成 ✔")
        else:
            print(f"数据库初始化完成, 但有 {total_errors} 条语句失败, 请检查上方警告")
        print("=" * 60)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
