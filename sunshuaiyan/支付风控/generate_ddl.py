"""Generate deterministic MySQL 8 DDL from models.py."""

from pathlib import Path

from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from models import Base


def main() -> None:
    dialect = mysql.dialect()
    chunks = [
        "-- Generated from models.py; do not edit by hand.",
        "-- Target: MySQL 8.0+",
        "SET NAMES utf8mb4;",
        "CREATE DATABASE IF NOT EXISTS `pingpong` "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;",
        "USE `pingpong`;",
        "SET FOREIGN_KEY_CHECKS = 0;",
    ]

    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect)).strip()
        ddl += " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;"
        chunks.append(ddl)
        for index in sorted(table.indexes, key=lambda item: item.name or ""):
            chunks.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")

    chunks.append("SET FOREIGN_KEY_CHECKS = 1;")
    output = Path(__file__).with_name("schema.sql")
    output.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
    print(f"generated {output} with {len(Base.metadata.tables)} tables")


if __name__ == "__main__":
    main()
