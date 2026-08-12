"""幂等初始化 8 条旅游 OTA 风控规则。"""
import asyncio
import sys
from pathlib import Path

import aiomysql

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from scripts.init_db import execute_sql_file  # noqa: E402


async def main() -> int:
    """连接配置数据库并执行旅游规则 SQL。"""
    sql_path = PROJECT_ROOT / "sql" / "init_tourism_rules.sql"
    connection = await aiomysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        db=settings.DB_NAME,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        errors = await execute_sql_file(connection, str(sql_path), "初始化 8 条旅游风控规则")
    finally:
        await connection.ensure_closed()
    if errors:
        print(f"旅游规则初始化失败: {errors} 条 SQL 执行异常")
        return 1
    print("旅游规则初始化完成: R001/R002/R005/R008/R012/R018/R025/R030")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
