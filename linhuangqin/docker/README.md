# docker 目录 — 物流风控系统生产部署

## 文件清单

| 文件 | 作用 |
|---|---|
| `Dockerfile` | 多阶段构建镜像（Python 3.11 + FastAPI + XGBoost） |
| `docker-compose.yml` | 一键启动 MySQL + App + Nginx 三个容器 |
| `nginx.conf` | 反向代理 FastAPI + 静态文件 + SSE 支持 |
| `.env.example` | 环境变量模板（`DB_NAME=risk_logistics`） |
| `.dockerignore` | 排除 .venv / logs / .git / uv 等 |

## 快速启动

```bash
cd docker
cp .env.example .env
# 编辑 .env 填 LLM_API_KEY 等

docker compose up -d
# 3 个容器: mysql + app (FastAPI) + nginx

# 容器内自动执行:
#   - init_db (21 张表)
#   - gen_logistics_data.py (200 条)
#   - gen_risky_users.py (30 个)

# 手动训练模型:
docker compose exec app python scripts/train_xgb_model.py
```

## 架构

```
Nginx (80/443) → FastAPI (gunicorn 2 workers) → MySQL 8.0 (utf8mb4)
     ↓                                              ↓
  静态文件                                    risk_logistics 库
  SSE 流式                                    21 张表 (12 业务 + 9 风控)
```

## 关键配置

| 参数 | 默认值 | 说明 |
|---|---|---|
| `MYSQL_DATABASE` | `risk_logistics` | 物流风控专用库 |
| `CASE_TIMEOUT_HOURS` | 24 | 待审案件超 24h 自动关 |
| `ALERT_SCHEDULER_INTERVAL_MIN` | 15 | 告警检查间隔（0=关闭）|
| `XGB_ENABLED` | True | XGBoost 双轨融合开关 |