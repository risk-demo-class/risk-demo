"""执行 SQL 迁移脚本 (UTF-8 安全, 避免 PowerShell 管道中文乱码).

用法: python scripts/apply_migration.py sql/migration_add_generic_event.sql
"""
import os
import sys

import pymysql

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    rel_path = sys.argv[1] if len(sys.argv) > 1 else "sql/migration_add_generic_event.sql"
    sql_path = rel_path if os.path.isabs(rel_path) else os.path.join(ROOT, rel_path)
    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "123321"),
        database=os.getenv("DB_NAME", "travel_risk"),
        charset="utf8mb4",
        autocommit=True,
        client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,
    )
    try:
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()
        cur = conn.cursor()
        cur.execute(sql)
        print(f"迁移执行成功: {rel_path}")
    except Exception as e:
        print(f"迁移失败: {type(e).__name__}: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
