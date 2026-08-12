"""
物流行业风控系统 - 一键数据库初始化脚本 (异步)
按顺序执行:
  建库 → 物流业务表 → 风控表 → 物流规则 → 业务数据 → RISK 用户 → 风控评估演示数据

总表数: 6 物流业务表 + 9 风控表 = 15 张 (2026-08-12 物流域)
"""

import argparse
import asyncio
import os
import subprocess
import sys

import aiomysql

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(BASE_DIR, "sql")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")

# SQL 脚本执行顺序 (物流域)
SQL_FILES = [
    ("init_logistics_tables.sql", "创建物流业务表 (6 张)"),
    ("init_risk_tables.sql", "创建风控表 (9 张)"),
    ("init_logistics_rules.sql", "导入物流行业规则 (L_R001-L_R030)"),
]

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 3306
DEFAULT_USER = "root"
DEFAULT_PASSWORD = "123456"
DEFAULT_DB = "ecs"


async def get_connection(host, port, user, password, db=None):
    """获取 MySQL 异步连接"""
    return await aiomysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db,
        charset="utf8mb4",
        autocommit=True,
    )


async def create_database(conn, db_name, drop_first=False):
    """创建数据库"""
    async with conn.cursor() as cur:
        if drop_first:
            print(f"  删除数据库 {db_name} ...")
            await cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
        await cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
        )
    print(f"  数据库 {db_name} 已就绪")


async def execute_sql_file(conn, filepath, description):
    """执行单个 SQL 脚本文件 (异步)"""
    filename = os.path.basename(filepath)
    print(f"\n[{filename}] {description}")

    with open(filepath, "r", encoding="utf-8") as f:
        sql_content = f.read()

    statements = split_sql_statements(sql_content)
    total = len(statements)
    success = 0
    errors = 0

    async with conn.cursor() as cur:
        for stmt in statements:
            try:
                await cur.execute(stmt)
                success += 1
            except aiomysql.Error as e:
                code = e.args[0]
                # 1051 = Unknown table 'X' (DROP TABLE IF EXISTS 的正常提示)
                # 1062 = Duplicate entry (数据已存在, 重复跑 init_db.py 时正常)
                if code in (1051, 1062):
                    success += 1
                else:
                    errors += 1
                    print(f"  警告 [{code}]: {e.args[1][:120]}")

    status = "完成" if errors == 0 else f"完成 (成功 {success}, 失败 {errors})"
    print(f"  共 {total} 条语句, {status}")
    return errors


def split_sql_statements(sql_text):
    """将 SQL 文本拆分为独立语句，处理字符串中的分号"""
    statements = []
    current = []
    in_single_quote = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    chars = sql_text

    while i < len(chars):
        c = chars[i]

        if not in_single_quote and not in_block_comment and c == '-' and i + 1 < len(chars) and chars[i + 1] == '-':
            in_line_comment = True
            i += 2
            continue
        if in_line_comment:
            if c == '\n':
                in_line_comment = False
            i += 1
            continue

        if not in_single_quote and not in_line_comment and c == '/' and i + 1 < len(chars) and chars[i + 1] == '*':
            in_block_comment = True
            i += 2
            continue
        if in_block_comment:
            if c == '*' and i + 1 < len(chars) and chars[i + 1] == '/':
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if c == "'" and not in_block_comment and not in_line_comment:
            if in_single_quote:
                if i + 1 < len(chars) and chars[i + 1] == "'":
                    current.append(c)
                    current.append(chars[i + 1])
                    i += 2
                    continue
                in_single_quote = False
            else:
                in_single_quote = True
            current.append(c)
            i += 1
            continue

        if c == '\\' and in_single_quote and i + 1 < len(chars):
            current.append(c)
            current.append(chars[i + 1])
            i += 2
            continue

        if c == ';' and not in_single_quote:
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(c)
        i += 1

    last = ''.join(current).strip()
    if last:
        statements.append(last)

    return statements


def run_script(script_name: str, *args: str) -> None:
    """运行项目内脚本 (阻塞等待完成)."""
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script_name), *args]
    print(f"\n[{script_name}] {' '.join(args) if args else ''}".strip())
    result = subprocess.run(cmd, cwd=BASE_DIR)
    if result.returncode != 0:
        raise RuntimeError(f"[{script_name}] 执行失败, returncode={result.returncode}")


async def main():
    parser = argparse.ArgumentParser(
        description="物流行业风控系统 - 一键数据库初始化 (异步). 默认 --reset 重建整个数据库.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法:
  python scripts/init_db.py                       # 默认: --reset (删库重建, 适合教学/演示)
  python scripts/init_db.py --keep-data          # 保留: 只补表结构 (业务数据不重置)
  python scripts/init_db.py --reset --yes        # 重置 + 自动确认 (CI/脚本用)
  python scripts/init_db.py --db ecs_test        # 初始化测试库
        """,
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="MySQL 主机")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MySQL 端口")
    parser.add_argument("--user", default=DEFAULT_USER, help="MySQL 用户名")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="MySQL 密码")
    parser.add_argument("--db", default=DEFAULT_DB, help="数据库名称")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--reset", dest="reset", action="store_true", default=True,
        help="默认行为: 先 DROP DATABASE 再 CREATE (重置整个库, 删所有数据)",
    )
    group.add_argument(
        "--keep-data", dest="reset", action="store_false",
        help="保留数据, 只补表结构 (不删库, CREATE TABLE IF NOT EXISTS)",
    )
    parser.add_argument(
        "--drop", action="store_true", default=False,
        help="(已废弃, 用 --reset) 先删除再重建数据库",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="跳过重置确认 (CI/脚本场景)",
    )
    args = parser.parse_args()

    if args.drop:
        args.reset = True

    print("=" * 60)
    print("物流行业风控系统 - 数据库初始化 (异步)")
    print(f"目标: {args.user}@{args.host}:{args.port}/{args.db}")
    print(f"模式: {'[RESET] 先删后建' if args.reset else '[KEEP-DATA] 保留数据, 只补表'}")
    print("=" * 60)

    if args.reset and not args.yes:
        print(f"\n[WARNING] --reset 模式会删除数据库 {args.db} 的所有表和数据!")
        try:
            confirm = input("确认继续? (yes/no): ").strip().lower()
        except EOFError:
            confirm = "no"
        if confirm != "yes":
            print("已取消 (输入 yes 才会执行).")
            sys.exit(0)
        print(f"  确认: yes, 开始重置 {args.db}")

    # 步骤 1: 创建数据库
    print("\n[步骤 1/6] 创建数据库")
    try:
        conn = await get_connection(args.host, args.port, args.user, args.password)
        try:
            await create_database(conn, args.db, drop_first=args.reset)
        finally:
            await conn.ensure_closed()
    except aiomysql.Error as e:
        print(f"  错误: 无法连接 MySQL - {e}")
        sys.exit(1)

    # 步骤 2-4: 按顺序执行 SQL
    conn = await get_connection(args.host, args.port, args.user, args.password, db=args.db)
    total_errors = 0
    try:
        for idx, (filename, desc) in enumerate(SQL_FILES, start=2):
            filepath = os.path.join(SQL_DIR, filename)
            if not os.path.exists(filepath):
                print(f"\n[步骤 {idx}/6] 跳过: {filename} 不存在")
                continue
            print(f"\n[步骤 {idx}/6]", end="")
            errors = await execute_sql_file(conn, filepath, desc)
            total_errors += errors
    finally:
        await conn.ensure_closed()

    if total_errors > 0:
        print(f"\n初始化 SQL 有 {total_errors} 个错误, 停止后续造数.")
        sys.exit(1)

    # 步骤 5: 业务数据 + RISK 用户
    print("\n[步骤 5/6] 生成业务测试数据 + RISK 高风险用户")
    run_script("gen_logistics_data.py")
    run_script("gen_risky_users.py", "--count", "10")

    # 步骤 6: 风控评估演示数据 (跨 7 天 + 今日 live)
    print("\n[步骤 6/6] 生成风控评估演示数据 (评估/案件/画像)")
    run_script("gen_risk_data_with_dates.py", "--days", "7", "--per-day", "12")
    run_script("gen_risk_data_with_dates.py", "--days", "1", "--per-day", "30",
               "--live", "--balance-pos", "--force-pos-ratio", "0.4")

    print("\n" + "=" * 60)
    print("初始化完成!")
    print("  物流业务表: user_info / address / shipment / shipment_item / shipment_complaint")
    print("  风控规则:   L_R001-L_R030")
    print("  演示数据:   评估 / 案件 / 用户画像 已生成")
    print("  下一步:     python run_app.py  →  http://localhost:8000")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
