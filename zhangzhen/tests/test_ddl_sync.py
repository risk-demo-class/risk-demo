from pathlib import Path
import re

from app.models import Base


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_generated_mysql_ddl_contains_every_orm_table() -> None:
    ddl = (PROJECT_ROOT / "sql" / "init_tables.sql").read_text(encoding="utf-8")

    for table_name in Base.metadata.tables:
        pattern = rf"CREATE TABLE IF NOT EXISTS `?{re.escape(table_name)}`?\s*\("
        assert re.search(pattern, ddl)

    assert ddl.count("CREATE TABLE IF NOT EXISTS") == 17
