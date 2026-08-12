# Docker 部署

## 首次启动 (数据库 + 应用)

```bash
cd docker
docker compose up -d --build
```

首次启动后初始化数据库:

```bash
docker compose exec app python scripts/init_db.py --yes
docker compose exec app python scripts/one_command.py --skip-init
```

访问: http://localhost:8000

## 说明

- `docker-compose.yml` 会启动 MySQL 8 (utf8mb4) + 应用 (gunicorn 2 workers)
- 应用启动时自动加载 XGBoost 模型 (`app/engine/xgb_model.json`), 没有则降级纯规则
- 生产环境: 修改 `docker-compose.yml` 里的数据库密码, 并通过 nginx 反向代理
