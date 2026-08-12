from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, inspect, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from app import models  # noqa: E402,F401 - register all ORM tables
from app.database import Base  # noqa: E402


SAFE_DATABASE_NAME = re.compile(r"^[A-Za-z0-9_]+$")

BUSINESS_CORE_TABLES = (
    "user_info",
    "passenger_info",
    "payment_account",
    "order_info",
    "order_passenger",
)

BOOKING_PRODUCT_TABLES = (
    "visa_application",
    "booking_hotel",
    "booking_flight",
    "booking_tour",
)

RISK_CONTROL_TABLES = (
    "blacklist_extra",
    "risk_rule",
    "risk_assessment",
    "risk_hit",
    "review_case",
    "audit_log",
)

AUTH_RBAC_TABLES = (
    "staff_user",
    "role",
    "permission",
    "staff_user_role",
    "role_permission",
)

GROUP_TABLES = {
    "business": BUSINESS_CORE_TABLES,
    # These two groups include their foreign-key dependencies so each script can
    # be executed directly against an empty database.
    "bookings": BUSINESS_CORE_TABLES + BOOKING_PRODUCT_TABLES,
    "risk": BUSINESS_CORE_TABLES + RISK_CONTROL_TABLES,
    "auth": AUTH_RBAC_TABLES,
    "all": (
        BUSINESS_CORE_TABLES
        + BOOKING_PRODUCT_TABLES
        + RISK_CONTROL_TABLES
        + AUTH_RBAC_TABLES
    ),
}


def _database_url(database: str | None) -> URL:
    return URL.create(
        drivername="mysql+pymysql",
        username=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=database,
        query={"charset": "utf8mb4"},
    )


def ensure_database(database: str) -> None:
    if not SAFE_DATABASE_NAME.fullmatch(database):
        raise ValueError("数据库名只能包含英文字母、数字和下划线")

    server_engine = create_engine(_database_url(None), pool_pre_ping=True)
    try:
        with server_engine.begin() as connection:
            connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )
            )
    finally:
        server_engine.dispose()


def create_table_group(group: str, database: str | None = None) -> None:
    if group not in GROUP_TABLES:
        raise ValueError(f"未知表分类：{group}")

    database_name = database or os.getenv("MYSQL_DATABASE", "risk_proj")
    ensure_database(database_name)

    engine = create_engine(
        _database_url(database_name),
        pool_pre_ping=True,
        pool_recycle=1800,
    )
    try:
        before = set(inspect(engine).get_table_names())
        table_names = GROUP_TABLES[group]
        tables = [Base.metadata.tables[name] for name in table_names]
        Base.metadata.create_all(bind=engine, tables=tables, checkfirst=True)
        after = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    created = sorted(after - before)
    print(f"数据库 `{database_name}` 已就绪。")
    print(f"本分类包含 {len(table_names)} 张表，本次新建 {len(created)} 张表。")
    if created:
        print("新建表：" + ", ".join(created))
    else:
        print("所有对应表均已存在，未重复创建。")


def run(group: str, description: str) -> None:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--database",
        default=None,
        help="目标数据库名；不填写时读取 .env 的 MYSQL_DATABASE",
    )
    args = parser.parse_args()
    create_table_group(group, args.database)
