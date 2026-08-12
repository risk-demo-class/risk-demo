"""教育业务 ORM 与手写 MySQL DDL 的离线同步测试。

不连接数据库，只比较表、字段、主键、索引、唯一约束、外键和检查约束。
真实 MySQL 验证仍可在后续使用 ``init_db.py --schema-only`` 完成。
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.models_business import BUSINESS_MODELS
from scripts.init_db import connection_scoped_statements


ROOT = Path(__file__).resolve().parents[1]
DDL_PATH = ROOT / "sql" / "init_business_tables.sql"

TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`(?P<name>\w+)`\s*"
    r"\((?P<body>.*?)\)\s*ENGINE=",
    re.IGNORECASE | re.DOTALL,
)


def _backtick_names(fragment: str) -> tuple[str, ...]:
    return tuple(re.findall(r"`([^`]+)`", fragment))


def _parse_ddl() -> dict[str, dict[str, object]]:
    text = DDL_PATH.read_text(encoding="utf-8")
    result: dict[str, dict[str, object]] = {}

    for match in TABLE_RE.finditer(text):
        body = match.group("body")
        columns = []
        definitions: dict[str, str] = {}
        primary_key: tuple[str, ...] = ()
        indexes: dict[str, tuple[str, ...]] = {}
        unique_sets: set[tuple[str, ...]] = set()
        foreign_keys: set[tuple[str, str, str | None]] = set()
        checks: set[str] = set()

        for raw_line in body.splitlines():
            line = raw_line.strip().rstrip(",")
            if not line:
                continue

            column_match = re.match(r"`(?P<name>\w+)`\s+", line)
            if column_match:
                column_name = column_match.group("name")
                columns.append(column_name)
                definitions[column_name] = line[column_match.end():]
                continue

            pk_match = re.match(r"PRIMARY KEY\s*\((?P<cols>[^)]+)\)", line, re.I)
            if pk_match:
                primary_key = _backtick_names(pk_match.group("cols"))
                continue

            unique_match = re.match(
                r"UNIQUE KEY\s+`(?P<name>[^`]+)`\s*\((?P<cols>[^)]+)\)", line, re.I
            )
            if unique_match:
                unique_sets.add(_backtick_names(unique_match.group("cols")))
                continue

            index_match = re.match(
                r"KEY\s+`(?P<name>[^`]+)`\s*\((?P<cols>[^)]+)\)", line, re.I
            )
            if index_match:
                indexes[index_match.group("name")] = _backtick_names(index_match.group("cols"))
                continue

            fk_match = re.search(
                r"FOREIGN KEY\s*\(`(?P<local>\w+)`\)\s+"
                r"REFERENCES\s+`(?P<table>\w+)`\s*\(`(?P<remote>\w+)`\)"
                r"(?:\s+ON DELETE\s+(?P<ondelete>\w+))?",
                line,
                re.I,
            )
            if fk_match:
                foreign_keys.add(
                    (
                        fk_match.group("local"),
                        f"{fk_match.group('table')}.{fk_match.group('remote')}",
                        fk_match.group("ondelete").upper() if fk_match.group("ondelete") else None,
                    )
                )

            check_match = re.search(r"CONSTRAINT\s+`(?P<name>[^`]+)`\s+CHECK", line, re.I)
            if check_match:
                checks.add(check_match.group("name"))

        result[match.group("name")] = {
            "columns": tuple(columns),
            "definitions": definitions,
            "primary_key": primary_key,
            "indexes": indexes,
            "unique_sets": unique_sets,
            "foreign_keys": foreign_keys,
            "checks": checks,
        }

    return result


def _orm_type_signature(column) -> str:
    column_type = column.type
    if isinstance(column_type, Enum):
        values = ",".join(repr(value) for value in column_type.enums)
        return f"enum({values})"
    if isinstance(column_type, Text):
        return "text"
    if isinstance(column_type, String):
        return f"varchar({column_type.length})"
    if isinstance(column_type, Numeric):
        return f"decimal({column_type.precision},{column_type.scale})"
    if isinstance(column_type, Boolean):
        return "boolean"
    if isinstance(column_type, DateTime):
        return "datetime"
    if isinstance(column_type, Integer):
        return "int"
    raise AssertionError(f"未配置类型签名: {column_type!r}")


def _ddl_type_signature(definition: str) -> str:
    normalized = re.sub(r"\s+", " ", definition.strip()).lower()
    normalized = re.sub(r",\s+", ",", normalized)
    for pattern in (
        r"enum\([^)]*\)",
        r"varchar\(\d+\)",
        r"(?:decimal|numeric)\(\d+,\d+\)",
        r"tinyint\(1\)",
        r"(?:int|integer)\b",
        r"datetime\b",
        r"text\b",
    ):
        match = re.match(pattern, normalized)
        if not match:
            continue
        value = match.group(0)
        if value.startswith(("decimal", "numeric")):
            return "decimal" + value[value.index("("):]
        if value == "tinyint(1)":
            return "boolean"
        if value == "integer":
            return "int"
        return value
    raise AssertionError(f"无法解析 DDL 字段类型: {definition}")


def test_business_ddl_matches_orm_structure():
    ddl = _parse_ddl()
    orm = {model.__tablename__: model.__table__ for model in BUSINESS_MODELS}

    assert set(ddl) == set(orm)
    assert len(ddl) == 7

    for table_name, table in orm.items():
        parsed = ddl[table_name]
        assert parsed["columns"] == tuple(column.name for column in table.columns)
        assert parsed["primary_key"] == tuple(table.primary_key.columns.keys())

        definitions = parsed["definitions"]
        for column in table.columns:
            definition = definitions[column.name]
            assert _ddl_type_signature(definition) == _orm_type_signature(column)
            assert ("NOT NULL" in definition.upper()) is (not column.nullable)
            assert ("AUTO_INCREMENT" in definition.upper()) is bool(
                column.autoincrement is True
            )

        orm_indexes = {
            index.name: tuple(column.name for column in index.columns)
            for index in table.indexes
            if not index.unique
        }
        assert parsed["indexes"] == orm_indexes

        orm_unique_sets = {
            tuple(constraint.columns.keys())
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert parsed["unique_sets"] == orm_unique_sets

        orm_foreign_keys = {
            (
                element.parent.name,
                element.target_fullname,
                constraint.ondelete.upper() if constraint.ondelete else None,
            )
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
            for element in constraint.elements
        }
        assert parsed["foreign_keys"] == orm_foreign_keys

        orm_checks = {
            constraint.name
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert parsed["checks"] == orm_checks


def test_business_models_compile_for_mysql_8():
    for model in BUSINESS_MODELS:
        compiled = str(CreateTable(model.__table__).compile(dialect=mysql.dialect()))
        assert f"CREATE TABLE {model.__tablename__}" in compiled


def test_init_db_ignores_hard_coded_use_statement():
    statements = connection_scoped_statements(
        "USE ecs; CREATE TABLE IF NOT EXISTS `demo` (`id` int NOT NULL);"
    )
    assert len(statements) == 1
    assert statements[0].startswith("CREATE TABLE")
