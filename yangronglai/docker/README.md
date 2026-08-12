# Docker 启动

1. 在项目根目录复制 `.env.example` 为 `.env`。
2. 在 `.env` 中设置 `DB_PASSWORD`、`MYSQL_ROOT_PASSWORD`、`NEO4J_PASSWORD`。
3. 执行：

```powershell
docker compose --env-file ..\.env -f docker-compose.yml up -d --build
```

从 `docker/` 目录执行。访问入口：

- `http://localhost/`：项目页面
- `http://localhost/docs`：Swagger
- `http://localhost:7474`：Neo4j Browser

应用容器会在 MySQL 和 Neo4j 健康后幂等创建数据层表，并加载镜像内的 5 个模型。规则、模型、图谱和 Agent 均启用；首次 Neo4j 数据同步需显式调用 `POST /api/graph/sync`。
