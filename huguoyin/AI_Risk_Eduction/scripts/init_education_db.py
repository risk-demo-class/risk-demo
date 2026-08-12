"""
教育行业风控系统 - 数据库初始化脚本

只初始化教育业务表 + 通用风控核心表, 不导入电商业务表/电商业务数据。

用法:
  python scripts/init_education_db.py --yes
  python scripts/init_education_db.py --keep-data
  python scripts/init_education_db.py --db ecs_edu --yes
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(BASE_DIR, "sql")

SQL_FILES = [
    ("init_education_business_tables.sql", "创建 15 张教育业务表"),
    ("init_risk_tables.sql", "创建 9 张风控核心表"),
    ("migration_education_rule_flex.sql", "兼容教育行业规则分类/事件类型"),
    ("init_education_risk_rules.sql", "导入 8 条指定教育行业风控规则"),
]

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 3306
DEFAULT_USER = "root"
DEFAULT_PASSWORD = "000000"
DEFAULT_DB = "ecs_edu"


async def main() -> int:
    parser = argparse.ArgumentParser(description="教育行业风控系统 - 一键数据库初始化")
    parser.add_argument("--host", default=DEFAULT_HOST, help="MySQL 主机")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MySQL 端口")
    parser.add_argument("--user", default=DEFAULT_USER, help="MySQL 用户名")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="MySQL 密码")
    parser.add_argument("--db", default=DEFAULT_DB, help="数据库名称")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--reset", dest="reset", action="store_true", default=True, help="先删库再重建")
    group.add_argument("--keep-data", dest="reset", action="store_false", help="保留数据, 只补表结构/规则")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过重置确认")
    args = parser.parse_args()

    try:
        import aiomysql
        from scripts.init_db import create_database, execute_sql_file, get_connection
    except ModuleNotFoundError as e:
        print(f"缺少依赖: {e.name}")
        print("请先激活项目环境, 或安装依赖: pip install -r requirements.txt")
        return 1

    print("=" * 60)
    print("教育行业风控系统 - 数据库初始化")
    print(f"目标: {args.user}@{args.host}:{args.port}/{args.db}")
    print(f"模式: {'[RESET] 先删后建' if args.reset else '[KEEP-DATA] 保留数据, 只补表'}")
    print("=" * 60)

    if args.reset and not args.yes:
        print(f"\n[WARNING] --reset 会删除数据库 {args.db} 的所有表和数据!")
        try:
            confirm = input("确认继续? (yes/no): ").strip().lower()
        except EOFError:
            confirm = "no"
        if confirm != "yes":
            print("已取消。")
            return 0

    try:
        conn = await get_connection(args.host, args.port, args.user, args.password)
        try:
            await create_database(conn, args.db, drop_first=args.reset)
        finally:
            await conn.ensure_closed()
    except aiomysql.Error as e:
        print(f"错误: 无法连接 MySQL - {e}")
        return 1

    total_errors = 0
    conn = await get_connection(args.host, args.port, args.user, args.password, db=args.db)
    try:
        for filename, desc in SQL_FILES:
            filepath = os.path.join(SQL_DIR, filename)
            total_errors += await execute_sql_file(conn, filepath, desc)
    finally:
        await conn.ensure_closed()

    print("\n" + "=" * 60)
    if total_errors == 0:
        print("初始化完成: 教育业务表 + 风控核心表已就绪")
        print("下一步: python scripts/gen_education_business_data.py --clear --count 120")
    else:
        print(f"初始化完成, 但有 {total_errors} 个错误, 请检查上方输出")
    print("=" * 60)
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
