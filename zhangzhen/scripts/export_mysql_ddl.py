"""从 SQLAlchemy metadata 导出 MySQL 8 DDL。

该脚本让 ``sql/init_tables.sql`` 与 ORM 共用同一来源，避免手工维护两套字段。
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models import Base  # noqa: E402


def render_mysql_ddl(database_name: str = "bank_risk") -> str:
    dialect = mysql.dialect()
    statements = [
        "-- 由 scripts/export_mysql_ddl.py 从 SQLAlchemy ORM 自动生成",
        "-- 8 张银行业务表 + 9 张风控核心表",
        "SET NAMES utf8mb4;",
        f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
        "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;",
        f"USE `{database_name}`;",
    ]

    for table in Base.metadata.sorted_tables:
        create_table = str(
            CreateTable(table, if_not_exists=True).compile(
                dialect=dialect,
                compile_kwargs={"literal_binds": True},
            )
        ).strip()
        statements.append(create_table + ";")
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            create_index = str(CreateIndex(index).compile(dialect=dialect)).strip()
            statements.append(create_index + ";")

    return "\n\n".join(statements) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出银行风控 MySQL DDL")
    parser.add_argument("--database", default="bank_risk", help="数据库名")
    parser.add_argument("--output", type=Path, help="输出文件；省略时打印到终端")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ddl = render_mysql_ddl(args.database)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(ddl, encoding="utf-8")
        print(f"已导出 {len(Base.metadata.tables)} 张表：{args.output}")
    else:
        print(ddl, end="")


if __name__ == "__main__":
    main()

