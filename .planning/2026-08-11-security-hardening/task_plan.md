# Task Plan: AI_Risk_Medical 安全合规加固 + 工程细节修复

## Goal

在 AI_Risk_Medical 上完成"安全合规最小闭环（P0）→ 脱敏审计与会话（P1）→ 工程基建（P2）"三阶段改造，每阶段独立验证（pytest + 启动自检）并提交，产出可审计、可部署的医疗风控原型。

## Current Phase

已结束 (P2 于 2026-08-12 由用户取消, 改为完善现有逻辑)

## Phases

### Phase 1: P0 安全合规最小闭环

- [x] 1.1 密钥卫生：`.dockerignore` 排除 `.env`/`.env.*`；`config.py`/`init_db.py`/`docker-compose.yml` 移除默认口令 `123321`，改为必填 env
- [x] 1.2 最小鉴权：登录接口 + HMAC Token + `require_admin` 依赖；覆盖规则/黑名单/案件审核/Agent 对话等管理接口；前端 fetch 统一带 Token + 登录页
- [x] 1.3 Agent 收敛：`manage_blacklist` 只保留 check/list（去掉 add/remove）；`AgentChatRequest.message` 加长度上限
- [x] 1.4 调度器去重：scheduler 加 MySQL 命名锁，gunicorn 4 worker 下只跑一个实例
- [x] 1.5 P0 验证：全量 pytest 429 通过 + 真实应用冒烟（401/登录/me）+ `.dockerignore` 静态检查
- **Status:** complete

### Phase 2: P1 脱敏、审计、会话

- [x] 2.1 日志脱敏：`_safe_call` 参数掩码 + uvicorn access log 查询串过滤（`app/masking.py` 统一 helper）
- [x] 2.2 LLM 上下文脱敏：`query_business_data` 返回前过滤姓名/诊断/收件人（`LLM_DATA_MASK` 开关）
- [x] 2.3 访问审计：Agent 查业务数据写新表 `risk_data_access_log`（operator=ai_agent + query_type + 目标 user_id）
- [x] 2.4 会话外置 + TTL：Agent session 迁 MySQL `agent_session` 表，`AGENT_SESSION_TTL_HOURS` 自动清理
- [x] 2.5 P1 验证：脱敏单测 + 审计留痕断言 + 会话持久化/TTL 测试 + 全量 447 passed
- **Status:** complete

### Phase 3: P2 工程基建

> 2026-08-12: 用户决定不做本阶段 (Alembic/CI/画像表医疗化/遗留清理/覆盖率).
> 改为完善现有逻辑: 清理死代码、修正训练脚本汇总、电商残留命名医疗化 (见 progress.md).

- [ ] 3.1 Alembic 迁移工具初始化（baseline 迁移替换 create_all）
- [ ] 3.2 CI/CD：GitHub Actions（pytest + 覆盖率 + 镜像构建检查）
- [ ] 3.3 安全测试用例：401 用例、`.dockerignore` 断言、脱敏单测
- [ ] 3.4 画像表医疗化：`risk_user_profile` 改医疗维度 + `_update_user_profile` 取真实医疗特征
- [ ] 3.5 清理遗留：`train_demo_model.py`/`gen_10w_data.py`/`gen_risk_data.py` 标记废弃；项目名/标题改医疗版
- [ ] 3.6 覆盖率门槛：pytest-cov 配置 + 阈值
- **Status:** cancelled

## Key Questions

1. 鉴权方案：HMAC Token（无状态）vs 密码 session？→ 倾向 HMAC Token + Bearer 头（避免 CSRF，前端 fetch 统一带）
2. Agent 写工具去留：直接砍 add/remove，还是加人工确认流？→ 教学项目先砍写能力，保留 check/list
3. Session 存储：MySQL 表（无新依赖）vs Redis（需引入服务）→ 倾向 MySQL 表 + TTL

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| 鉴权用 HMAC Token + require_admin 依赖注入 | 无状态、前端 fetch 易带 Bearer 头、天然免 CSRF；不引入 OAuth 重量级 |
| Agent 黑名单写操作先砍掉 | 无鉴权 + LLM 可写库是最大风险面；教学先保证只读 |
| Session 迁 MySQL 表 + TTL 清理 | 项目无 Redis；多 worker 共享需外置存储，MySQL 已有现成依赖 |
| 调度器用 MySQL 命名锁去重 | 无新依赖；`GET_LOCK` 在 4 worker 下保证单实例执行 |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| SQLAlchemy bind parameter '14'（SQL 里 JSON `"qty":14` 冒号后无空格被当绑定参数） | 1 | 统一写成 `"qty": 14`（冒号后带空格）；已记 README FAQ |
| gen_risk_data_with_dates.py 重复 except 死代码 | 1 | 早前替换引入的冗余；功能无损，P2 清理时一并处理 |
| gunicorn 4 worker 下 scheduler 每进程都启动 | 未修 | P0 1.4 用 MySQL 命名锁修复 |
| Agent session 存进程内 dict：多 worker 不共享 + 无 TTL 泄漏 | 未修 | P1 2.4 迁 MySQL 表 |

## Notes

- 每阶段完成更新 status：pending → in_progress → complete
- 每个任务一个 commit；P0 完成先收口（全量测试 + 启动自检）再进 P1
- 改动超过 5 个文件时，动手前先更新本计划文件（WF1）
- 涉及删库/破坏性操作必须先说明并确认
