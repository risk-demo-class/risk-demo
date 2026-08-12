# SQL 说明

`init_tables.sql` 由 SQLAlchemy ORM 自动导出，包含 8 张银行业务表和 9 张风控核心表。

重新导出：

```powershell
uv run python scripts/export_mysql_ddl.py --output sql/init_tables.sql
```

日常初始化推荐使用：

```powershell
uv run python scripts/init_db.py
```

修改表结构时必须同时检查 ORM、Pydantic Schema、初始化 SQL 和测试。

