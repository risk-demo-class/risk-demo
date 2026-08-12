# 任务 2：数据层交付说明

## 目录与职责

| 交付物 | 状态 | 说明 |
|---|---|---|
| `app/models_business.py` | 已完成 | 21 张制造业业务表 SQLAlchemy 模型，与业务 DDL 对齐。 |
| `sql/init_business_tables.sql` | 已完成 | 业务表 DDL：主数据、采购、仓储、生产、质量、交付、维修和业务事件。 |
| `sql/init_business_data.sql` | 已完成 | 业务主数据与 120 条核心业务链路数据。 |
| `scripts/gen_business_data.py` | 已完成 | 可重复生成 120 条 Python 业务事件，且可单独校验数据。 |
| `app/service/validator.py` | 已完成 | 事件类型 → 校验函数派发表。 |
| `app/config.py` | 已完成 | 黑名单类型集合与制造业业务事件枚举。 |

## 初始化顺序

`scripts/init_db.py` 按以下顺序执行：

1. `sql/init_database.sql`：重建开发演示库 `manufacturing_risk`。
2. `sql/init_business_tables.sql`：创建 21 张业务表。
3. `sql/init_business_data.sql`：写入主数据和 120 条核心业务数据。
4. `sql/init_risk_tables.sql`：创建风险规则、风险事件表。
5. `sql/init_risk_data.sql`：写入风险规则和风险事件。
6. 调用 `scripts/gen_business_data.py --validate-only`：校验关键表数量和关联完整性。

## 常用命令

```powershell
uv run python scripts\init_db.py
uv run python scripts\gen_business_data.py
uv run python scripts\gen_business_data.py --validate-only
```

> `gen_business_data.py` 每次会清理并重建 `PYBE` 前缀业务事件，因此可重复执行，不会产生重复数据。
