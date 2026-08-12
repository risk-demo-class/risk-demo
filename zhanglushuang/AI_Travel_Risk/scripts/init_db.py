"""
数据库初始化脚本.

按顺序执行:
1. db/init.sql          -> 建表
2. sql/init_risk_data.sql -> 初始化规则
"""

import argparse
import logging
import sys
from pathlib import Path

import pymysql
from pymysql.constants import CLIENT

from app.config import settings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_sql(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        logger.exception("读取 SQL 失败: %s", path)
        raise


def _connect(autocommit: bool = True) -> pymysql.connections.Connection:
    try:
        return pymysql.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER or "root",
            password=settings.DB_PASSWORD or "",
            charset=settings.DB_CHARSET,
            autocommit=autocommit,
            client_flag=CLIENT.MULTI_STATEMENTS,
        )
    except Exception:
        logger.exception("连接 MySQL 失败: host=%s port=%s", settings.DB_HOST, settings.DB_PORT)
        raise


def init_db() -> None:
    """初始化数据库与表."""
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
            )
            cur.execute(f"USE `{settings.DB_NAME}`")

        scripts = [
            (PROJECT_ROOT / "db" / "init.sql", "建表脚本"),
            (PROJECT_ROOT / "sql" / "init_risk_data.sql", "规则初始化"),
        ]
        for sql_file, label in scripts:
            if not sql_file.exists():
                logger.warning("SQL 文件不存在, 跳过: %s", sql_file)
                continue
            sql_text = _read_sql(sql_file)
            with conn.cursor() as cur:
                cur.execute(sql_text)
            logger.info("%s 执行完成: %s", label, sql_file.name)

        conn.close()
        logger.info("数据库初始化完成: db=%s", settings.DB_NAME)
    except Exception:
        logger.exception("数据库初始化失败")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="旅游风控数据库初始化")
    parser.add_argument("--yes", action="store_true", help="跳过确认")
    args = parser.parse_args()
    if not args.yes:
        answer = input(f"确认初始化数据库 {settings.DB_NAME}? [y/N]: ")
        if answer.lower() != "y":
            logger.info("已取消")
            return
    init_db()


if __name__ == "__main__":
    main()
