import re
from pathlib import Path

from app.database import Base
import app.models  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]


def _ddl_tables(path: Path) -> dict[str, set[str]]:
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(r"CREATE TABLE IF NOT EXISTS `([^`]+)`\s*\(", text))
    tables: dict[str, set[str]] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end():end]
        columns = set(re.findall(r"^\s{4}`([^`]+)`\s+", block, flags=re.MULTILINE))
        tables[match.group(1)] = columns
    return tables


def test_orm_and_sql_table_and_column_names_match():
    ddl = {}
    ddl.update(_ddl_tables(ROOT / "sql" / "init_risk_tables.sql"))
    ddl.update(_ddl_tables(ROOT / "sql" / "init_business_tables.sql"))
    assert set(ddl) == set(Base.metadata.tables)
    for table_name, table in Base.metadata.tables.items():
        assert set(table.columns.keys()) == ddl[table_name], table_name


def test_business_ddl_uses_decimal_for_money():
    text = (ROOT / "sql" / "init_business_tables.sql").read_text(encoding="utf-8")
    for column in ("total_amount", "unit_price", "insurance_amount", "self_pay_amount"):
        assert re.search(rf"`{column}`\s+DECIMAL\(", text)
