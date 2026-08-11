# Findings & Decisions — 安全合规审查

## Requirements

- 用户关注：安全合规 + 工程细节（真实性数据暂无应用场景，不在本次范围）
- 输出：可落地的分阶段改造计划，每块独立验证与提交
- 约束：医疗风控教学项目；不引入重依赖；保留演示可用性

## Research Findings（审查证据，2026-08-11）

### 安全/合规

- **全接口无鉴权**：所有 router 只有 `Depends(get_db_async)`；`scripts/main.py` 无认证中间件。规则增删改、黑名单增删、案件审核、`/api/profile/{user_id}` 全部裸奔；`risk_action_log` 有审计表但无用户身份。
- **Agent 有写权限**：`app/agent/tools.py` 的 `manage_blacklist` 支持 add/remove，LLM 直接落库，无确认环节。
- **`.dockerignore` 漏 `.env`**：只有 7 行（.venv/__pycache__/logs 等），Dockerfile `COPY . .` 会把含 DB_PASSWORD/LLM_API_KEY 的 `.env` 打进镜像。
- **默认口令硬编码**：`app/config.py` DB_PASSWORD="123321"、`scripts/init_db.py` DEFAULT_PASSWORD="123321"、`docker-compose.yml` MYSQL_ROOT_PASSWORD 默认 123321；应用直连 root。
- **医疗数据无脱敏 + LLM 数据出境**：`query_business_data` 返回诊断/处方/金额等明细并作为上下文发给外部 LLM（阿里云百炼）；无字段级脱敏、无访问审计。
- **敏感字段进日志**：`_safe_call` 把工具入参（user_id、黑名单 value）整段打进日志；uvicorn access log 带查询参数。
- 无 HTTPS（nginx 443 配置整段注释）、无限流、`AgentChatRequest.message` 无长度上限。
- 良好面：`.env` 从未进 git 历史（git ls-files 只有 docker/.env.example）；规则分数-等级校验、黑名单软删+唯一约束、Agent 超时 504 兜底、异常 error_id 包装、启动 6 步预检。

### 工程细节

- **多 worker bug**：scheduler 在 lifespan 启动，gunicorn 4 worker 各自执行 → 告警检查重复 4 次，`risk_alert` 无唯一约束会重复插入。
- **Agent session 进程内 dict**（`app/agent/chat.py`）：4 worker 不共享、无 TTL → 会话乱跳 + 内存泄漏。
- **画像表/接口仍是电商字段**：`risk_user_profile`/`UserProfileResponse` 用 total_orders/refunds/address_count；`decision.py::_update_user_profile` 从 `user_total_orders` 等不存在特征取值 → 全是 0，功能失效。
- **迁移残留**：`pyproject.toml` 项目名 ai-risk/描述电商；`scripts/main.py` title 电商；`train_demo_model.py`（电商 mock 规则）、`gen_10w_data.py`、`gen_risk_data.py` 遗留。
- **无 Alembic**（alembic.ini 不存在），建表靠 create_all + 手写 SQL。
- **无 CI/CD**（无 .github/workflows）、无覆盖率配置、无 lint 配置；412 测试以单测+mock 为主，仅 3 个文件碰 DB，无安全测试。
- 依赖精确锁定（requirements.txt 好）；镜像 tag 浮点（python:3.11-slim/mysql:8.0），无 pip-audit/trivy。
- 性能：特征计算每评估 20+ 条 SQL，无缓存/预聚合。
- 可观测性：日志 dictConfig + RotatingFile（好）；无 metrics/trace、无请求 ID 贯穿。

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| P0 范围=密钥卫生/鉴权/Agent 收敛/调度器去重 | 上线必堵的洞优先，改动小收益大 |
| 鉴权=HMAC Token + Bearer | 免 CSRF、无状态、前端易适配 |
| Agent 写操作先砍 | 消除 LLM 直接写库风险面 |
| Session=MySQL 表 + TTL | 不引入 Redis |
| 调度器=MySQL GET_LOCK | 4 worker 单实例执行，零新依赖 |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| SQL 里 JSON `"qty":14` 被 SQLAlchemy 当绑定参数 | 冒号后加空格；已写 README FAQ |
| gen_risk_data_with_dates.py 重复 except 死代码 | 功能无损；P2 清理 |
| 训练数据脚本 process_event 重复调用 | 已修（上轮提交 d6f048d） |

## Resources

- 项目根：`D:\尚硅谷\尚硅谷\项目\电商风控\尚硅谷大模型项目之风控系统\3.代码\AI_Risk_Medical`
- 关键文件：`app/routers/*`、`app/agent/tools.py`、`app/agent/chat.py`、`app/scheduler.py`、`app/config.py`、`scripts/init_db.py`、`docker/docker-compose.yml`、`.dockerignore`
