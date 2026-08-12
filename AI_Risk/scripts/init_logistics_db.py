"""
物流行业风控系统 - 数据库初始化脚本
1. 执行 init_logistics_tables.sql (物流业务表)
2. 执行 init_risk_tables.sql (风控表 - 复用)
3. 执行 init_logistics_rules.sql (物流行业规则 L_R001-L_R030)
4. 执行 gen_logistics_data.py (物流业务数据)
5. 执行 gen_risky_users.py (RISK 高风险用户)
6. 执行 gen_risk_data_with_dates.py (风控评估数据, 让仪表盘/案件/评估页有数据)
"""
import asyncio
import os
import subprocess
import sys

import aiomysql
from app.config import settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(BASE_DIR, "sql")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")


async def execute_sql_file(conn, filename):
    filepath = os.path.join(SQL_DIR, filename)
    print(f"正在执行 {filename}...")
    with open(filepath, "r", encoding="utf-8") as f:
        sql = f.read()

    async with conn.cursor() as cur:
        # 简单分割 SQL (不处理字符串内分号, 仅供初始化用)
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                await cur.execute(stmt)


def run_script(script_name: str, *args: str) -> None:
    """运行项目内脚本 (阻塞等待完成)."""
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script_name), *args]
    print(f"\n正在执行: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=BASE_DIR, check=True)


async def main():
    print("=" * 60)
    print("物流行业风控系统 - 数据库初始化")
    print("=" * 60)

    # 1. 创建数据库
    conn = await aiomysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
    )
    async with conn.cursor() as cur:
        await cur.execute(f"DROP DATABASE IF EXISTS `{settings.DB_NAME}`")
        await cur.execute(f"CREATE DATABASE `{settings.DB_NAME}` CHARACTER SET utf8mb4")
    await conn.ensure_closed()

    # 2. 建表 + 规则
    conn = await aiomysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_NAME,
        charset="utf8mb4",
        autocommit=True,
    )

    try:
        await execute_sql_file(conn, "init_logistics_tables.sql")
        await execute_sql_file(conn, "init_risk_tables.sql")
        await execute_sql_file(conn, "init_logistics_rules.sql")
        print("  已加载物流行业规则 (L_R001-L_R030)")
    finally:
        await conn.ensure_closed()

    # 3. 业务数据
    run_script("gen_logistics_data.py")

    # 4. RISK 高风险用户 (供 --balance-pos 造正例)
    run_script("gen_risky_users.py", "--count", "10")

    # 5. 风控评估数据 (跨 7 天 + 今日 live, 让仪表盘趋势/今日都有数据)
    run_script("gen_risk_data_with_dates.py", "--days", "7", "--per-day", "12")
    run_script("gen_risk_data_with_dates.py", "--days", "1", "--per-day", "30",
               "--live", "--balance-pos", "--force-pos-ratio", "0.4")

    print("\n" + "=" * 60)
    print("物流行业数据库初始化完成!")
    print("  业务表: user_info / address / shipment / shipment_item / shipment_complaint")
    print("  规则:   L_R001-L_R030 (物流域)")
    print("  评估/案件/画像: 已生成演示数据")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
