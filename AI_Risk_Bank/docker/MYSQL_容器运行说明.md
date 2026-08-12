# 银行版 MySQL 容器启动说明

在本目录执行：

```powershell
docker compose -f docker-compose.mysql.yml up -d
```

查看状态：

```powershell
docker compose -f docker-compose.mysql.yml ps
docker compose -f docker-compose.mysql.yml logs -f mysql
```

连接数据库：

```powershell
docker exec -it ai_risk_bank_mysql mysql -uroot -p123321 ecs
```

验证银行表和规则：

```sql
SHOW TABLES;
SELECT COUNT(*) FROM risk_rule;
SELECT * FROM bank_transaction;
```

首次启动时会自动依次执行 `init_business_tables.sql`、`init_business_data.sql`、`init_risk_tables.sql`、`init_risk_data.sql`。

重置数据库（会删除所有容器数据）：

```powershell
docker compose -f docker-compose.mysql.yml down -v
docker compose -f docker-compose.mysql.yml up -d
```
