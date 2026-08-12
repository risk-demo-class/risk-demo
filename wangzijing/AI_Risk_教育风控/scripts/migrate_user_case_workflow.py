"""为已有 MySQL 数据库补齐用户管理和案件分配字段，可重复执行。"""
import asyncio
import argparse
import sys
from pathlib import Path

import aiomysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings


async def exists(cur, database: str, table: str, column: str) -> bool:
    await cur.execute(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s AND column_name=%s",
        (database, table, column),
    )
    return (await cur.fetchone())[0] > 0


async def index_exists(cur, database: str, table: str, index: str) -> bool:
    await cur.execute(
        "SELECT COUNT(*) FROM information_schema.statistics "
        "WHERE table_schema=%s AND table_name=%s AND index_name=%s",
        (database, table, index),
    )
    return (await cur.fetchone())[0] > 0


async def main():
    parser = argparse.ArgumentParser(description="升级用户与案件分配工作流字段")
    parser.add_argument("--db", default=settings.DB_NAME, help="目标 MySQL 数据库")
    args = parser.parse_args()
    database = args.db
    conn = await aiomysql.connect(
        host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER,
        password=settings.DB_PASSWORD, db=database, charset="utf8mb4", autocommit=True,
    )
    try:
        async with conn.cursor() as cur:
            for column, definition in [
                ("assignee_id", "BIGINT DEFAULT NULL COMMENT '当前审核员用户ID' AFTER risk_detail"),
                ("assign_time", "DATETIME DEFAULT NULL COMMENT '最近分派时间' AFTER assignee_id"),
            ]:
                if await exists(cur, database, "risk_case", column):
                    print(f"[SKIP] risk_case.{column}")
                else:
                    await cur.execute(f"ALTER TABLE risk_case ADD COLUMN {column} {definition}")
                    print(f"[ADD]  risk_case.{column}")
            if await index_exists(cur, database, "risk_case", "idx_risk_case_assignee_id"):
                print("[SKIP] idx_risk_case_assignee_id")
            else:
                await cur.execute("ALTER TABLE risk_case ADD INDEX idx_risk_case_assignee_id (assignee_id)")
                print("[ADD]  idx_risk_case_assignee_id")
            await cur.execute(
                "ALTER TABLE risk_action_log MODIFY COLUMN action_type "
                "ENUM('CREATE_RULE','UPDATE_RULE','TOGGLE_RULE','DELETE_RULE','REVIEW_CASE','AUTO_REJECT_CASE','AUTO_CLOSE_CASE','ADD_BLACKLIST','REMOVE_BLACKLIST','CREATE_USER','UPDATE_USER','TOGGLE_USER','RESET_PASSWORD','ASSIGN_CASE') NOT NULL COMMENT '操作类型'"
            )
            await cur.execute(
                "ALTER TABLE risk_action_log MODIFY COLUMN target_type "
                "ENUM('rule','case','blacklist','user') NOT NULL COMMENT '对象类型'"
            )
            print("[OK]   审计日志枚举已扩展")
    finally:
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
