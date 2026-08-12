# 物流风控 Docker 部署

`docker-compose.yml` 启动 MySQL 8、FastAPI 和 Nginx。首次创建 volume 时，
MySQL 会依次执行 5 张物流业务表、确定性演示数据、9 张核心风控表和 10 条规则。
`init-logistics-risk.sh` 只在导入流中忽略核心 DDL 的历史 `USE ecs` 行，不修改核心文件。

```bash
cd docker
docker compose up -d --build
docker compose ps
curl http://localhost:8000/docs
```

默认数据库为 `logistics_risk`。如需修改密码或端口，在 `docker/` 下创建 `.env`：

```dotenv
MYSQL_ROOT_PASSWORD=change-me
MYSQL_DATABASE=logistics_risk
MYSQL_PORT=3306
APP_PORT=8000
HTTP_PORT=80
LLM_API_KEY=
```

生成特征快照和训练模型：

```bash
docker compose exec app python scripts/gen_train_dataset.py --reset
docker compose exec app python scripts/train_xgb_model.py
```

重置数据库需要删除 MySQL volume，会永久删除该演示库数据：

```bash
docker compose down -v
docker compose up -d
```
