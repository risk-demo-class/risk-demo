"""银行风控教学数据库初始化：8 张业务表 + 9 张核心风控表。"""

import argparse
import asyncio
import os
import sys

import aiomysql

# 允许从任意当前目录运行本脚本。
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.config import settings  # noqa: E402

SQL_DIR = os.path.join(BASE_DIR, "sql")

# SQL 脚本执行顺序
SQL_FILES = [
    ("init_business_tables.sql", "创建 8 张银行业务表"),
    ("init_risk_tables.sql", "创建 9 张核心风控表"),
    ("init_business_data.sql", "导入 109 条四事件银行 source 数据"),
    ("init_risk_data.sql", "导入 11 条银行规则与教学黑卡"),
]

# 默认连接配置 (与 .env 一致)
DEFAULT_HOST = settings.DB_HOST
DEFAULT_PORT = settings.DB_PORT
DEFAULT_USER = settings.DB_USER
DEFAULT_PASSWORD = settings.DB_PASSWORD
DEFAULT_DB = settings.DB_NAME
ALLOWED_DATABASES = {"bank_risk", "bank_risk_test"}


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
    if db_name not in ALLOWED_DATABASES:
        raise ValueError(
            f"数据库只允许为 {sorted(ALLOWED_DATABASES)}，实际为 {db_name}"
        )
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

    # 按分号拆分语句，过滤空语句和注释
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
                    success += 1  # 视为幂等成功, 不计入错误
                else:
                    errors += 1
                    print(f"  警告 [{code}]: {e.args[1][:120]}")

    status = "完成" if errors == 0 else f"完成 (成功 {success}, 失败 {errors})"
    print(f"  共 {total} 条语句, {status}")
    return errors


async def has_existing_risk_rules(conn) -> bool:
    """默认保留数据模式下，避免规则种子覆盖已有规则和审计历史。"""
    async with conn.cursor() as cur:
        await cur.execute("SELECT 1 FROM `risk_rule` LIMIT 1")
        return await cur.fetchone() is not None


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

        # 处理行注释
        if (
            not in_single_quote
            and not in_block_comment
            and c == "-"
            and i + 1 < len(chars)
            and chars[i + 1] == "-"
        ):
            in_line_comment = True
            i += 2
            continue
        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue

        # 处理块注释
        if (
            not in_single_quote
            and not in_line_comment
            and c == "/"
            and i + 1 < len(chars)
            and chars[i + 1] == "*"
        ):
            in_block_comment = True
            i += 2
            continue
        if in_block_comment:
            if c == "*" and i + 1 < len(chars) and chars[i + 1] == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        # 处理单引号字符串
        if c == "'" and not in_block_comment and not in_line_comment:
            if in_single_quote:
                # 检查转义的单引号 ''
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

        # 处理反斜杠转义 (在字符串内)
        if c == "\\" and in_single_quote and i + 1 < len(chars):
            current.append(c)
            current.append(chars[i + 1])
            i += 2
            continue

        # 分号 = 语句结束
        if c == ";" and not in_single_quote:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(c)
        i += 1

    # 处理最后一条不以分号结尾的语句
    last = "".join(current).strip()
    if last:
        statements.append(last)

    return statements


async def main():
    parser = argparse.ArgumentParser(
        description="银行风控教学数据库初始化（默认幂等保留数据）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法:
  python scripts/init_db.py                              # 幂等初始化 bank_risk
  python scripts/init_db.py --db bank_risk_test          # 幂等初始化测试库
  python scripts/init_db.py --db bank_risk_test --reset  # 显式确认后重建测试库
  python scripts/init_db.py --db bank_risk_test --reset --yes
        """,
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="MySQL 主机")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MySQL 端口")
    parser.add_argument("--user", default=DEFAULT_USER, help="MySQL 用户名")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="MySQL 密码")
    parser.add_argument("--db", default=DEFAULT_DB, help="数据库名称")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--reset",
        dest="reset",
        action="store_true",
        default=False,
        help="显式重建专用教学库；仅允许 bank_risk/bank_risk_test",
    )
    group.add_argument(
        "--keep-data",
        dest="reset",
        action="store_false",
        help="保留兼容参数；默认即为幂等保留数据",
    )
    # 兼容老参数 --drop (deprecated, 走同样 reset 路径)
    parser.add_argument(
        "--drop",
        action="store_true",
        default=False,
        help="(已废弃, 用 --reset) 先删除再重建数据库",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="跳过重置确认 (CI/脚本场景)",
    )
    args = parser.parse_args()

    if args.drop:
        args.reset = True

    if args.db not in ALLOWED_DATABASES:
        parser.error(f"--db 只允许: {', '.join(sorted(ALLOWED_DATABASES))}")

    print("=" * 60)
    print("银行风控教学系统 - 数据库初始化（异步）")
    print(f"目标: {args.user}@{args.host}:{args.port}/{args.db}")
    print(
        f"模式: {'[RESET] 先删后建' if args.reset else '[KEEP-DATA] 保留数据, 只补表'}"
    )
    print("=" * 60)

    # 危险操作确认 (除非 --yes)
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
    print("\n[步骤 1/5] 创建数据库")
    try:
        conn = await get_connection(args.host, args.port, args.user, args.password)
        try:
            await create_database(conn, args.db, drop_first=args.reset)
        finally:
            await conn.ensure_closed()
    except aiomysql.Error as e:
        print(f"  错误: 无法连接 MySQL - {e}")
        sys.exit(1)

    # 步骤 2-5: 按顺序执行 SQL 脚本
    conn = await get_connection(
        args.host, args.port, args.user, args.password, db=args.db
    )
    total_errors = 0

    try:
        for idx, (filename, desc) in enumerate(SQL_FILES, start=2):
            filepath = os.path.join(SQL_DIR, filename)
            if not os.path.exists(filepath):
                print(f"\n[步骤 {idx}/5] 跳过: {filename} 不存在")
                continue
            if (
                filename == "init_risk_data.sql"
                and not args.reset
                and await has_existing_risk_rules(conn)
            ):
                print(
                    f"\n[步骤 {idx}/5] 跳过: 核心规则已有数据，"
                    "保留规则及 risk_action_log 历史"
                )
                continue
            print(f"\n[步骤 {idx}/5]", end="")
            errors = await execute_sql_file(conn, filepath, desc)
            total_errors += errors
    finally:
        await conn.ensure_closed()

    # 汇总
    print("\n" + "=" * 60)
    if total_errors == 0:
        print("初始化完成! 所有脚本执行成功。")
        if args.reset:
            print("数据库已重置: 17 张表重建 + 109 条四事件 source 数据已就绪")
    else:
        print(f"初始化完成，但有 {total_errors} 个错误，请检查上方输出。")
    print("=" * 60)

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
