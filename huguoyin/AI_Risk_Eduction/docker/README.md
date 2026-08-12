# Docker 部署

该 Compose 栈包含 MySQL 8、FastAPI/Gunicorn 和 Nginx。MySQL 数据与应用日志使用命名卷持久化，数据库不会暴露到宿主机。

## 启动

在项目根目录执行：

```powershell
Copy-Item docker\.env.example docker\.env
# 编辑 docker\.env，至少修改 MYSQL_ROOT_PASSWORD；需要 AI Agent 时填写 LLM_API_KEY
docker compose -f docker\docker-compose.yml up -d --build
docker compose -f docker\docker-compose.yml ps
```

Linux/macOS 可将第一条替换为：

```bash
cp docker/.env.example docker/.env
```

打开 `http://localhost:8080`，API 文档为 `http://localhost:8080/docs`，健康检查为 `http://localhost:8080/healthz`。可通过 `HTTP_PORT` 修改宿主机端口。

首次创建数据卷时，MySQL 会自动按顺序执行 4 个初始化脚本，不需要再运行 `scripts/init_db.py`。初始化脚本只在空数据卷上执行。

## 运维命令

```powershell
# 查看状态和日志
docker compose -f docker\docker-compose.yml ps
docker compose -f docker\docker-compose.yml logs -f app

# 更新代码后重新构建
docker compose -f docker\docker-compose.yml up -d --build

# 停止（保留数据库）
docker compose -f docker\docker-compose.yml down

# 老数据卷执行增量迁移
docker compose -f docker\docker-compose.yml exec app python scripts/migrate_2026_08_07.py
```

仅在明确需要清空全部数据库数据时，才使用 `docker compose -f docker/docker-compose.yml down -v`。

应用固定为一个 Gunicorn worker，因为 FastAPI lifespan 内含进程内调度器；增加 worker 会让调度任务重复执行。若要横向扩容，应先把调度器拆为独立服务。
