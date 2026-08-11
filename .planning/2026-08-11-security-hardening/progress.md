# Progress Log — 安全合规加固

## Session: 2026-08-11

### 附加任务: 生成人工审核事件 (审核工作台测试数据)

- **Status:** complete
- Actions taken:
  - 发现库里 0 个人工审核决策/0 个待审核案件 (双轨融合把高风险都推成拒绝)
  - 新增 `scripts/gen_review_cases.py`: 生成时 XGB_ENABLED=false (纯规则), 跑 RISK 用户
    4 类事件直到攒够目标个人工审核决策 (run_risk_check 自动建待审核案件)
  - 运行: 81 条事件 → 通过 17 / 标记 8 / 人工审核 40 / 拒绝 16, 40 个待审核案件
  - 验证: `GET /api/cases?active_only=true` total=40; 案件覆盖机构/医保/挂号等分类
- Files created/modified:
  - `scripts/gen_review_cases.py`（新建）

### 附加任务: 方案 B — 人工审核规则 ML 豁免

- **Status:** complete
- Actions taken:
  - 用户疑问: 生成的待审核案件 ML 分全 0 (生成时 XGB 关闭的占位值) → 选择方案 B
  - config 新增 `RISK_REVIEW_ML_EXEMPT=True`: 命中 action=人工审核 规则时 ML 只展示、不参与融合
  - decision.py `_calculate_decision` 按该开关跳过 ML 融合 (veto 不受影响)
  - 更新旧测试 (低 ML + 人工审核规则不再被降成标记) + 新增 3 个豁免专项测试
  - gen_review_cases.py 移除强制 XGB_ENABLED=false (方案 B 后不再需要)
  - 真实冒烟: RX_RISK028_012 在线检查 → 决策=人工审核, ML=0.9873 参考分
  - 已有待审核案件 ML 回填: 39 条全部有真实分 (分布 0.01~0.99, 平均 0.55)
  - 全量 pytest 450 passed
- Files created/modified:
  - `app/config.py`、`app/engine/decision.py`、`tests/test_risk_decision.py`
  - `scripts/gen_review_cases.py`、`README.md`

### Phase 1: P0 安全合规最小闭环

- **Status:** complete
- **Started:** 2026-08-11（用户批准执行）
- Actions taken:
  - 1.1 密钥卫生：`.dockerignore` 排除 .env/密钥/开发目录；config.py/init_db.py/compose 移除默认口令；init_db 读 .env；compose 必填校验（commit 1d6bfb9）
  - 1.3 Agent 收敛：manage_blacklist 只读（check/list），add/remove 返回安全限制；chat message ≤2000（commit fe4db5c）
  - 1.4 调度器去重：MySQL GET_LOCK 命名锁，4 worker 单实例（commit 5324f74）
  - 1.2 最小鉴权：app/auth.py HMAC Token + require_admin；登录路由；规则/黑名单/案件/Agent/告警接口保护；前端全局 fetch 包装 + 登录页 /login；本地 .env 补 ADMIN_*（commit 8281ea5）
  - 1.5 验证：全量 pytest 429 passed；真实 app 冒烟（/login 200、无 Token 401、登录后 me 200）；.dockerignore 静态检查
- Files created/modified:
  - `.planning/2026-08-11-security-hardening/*`（提交）
  - `app/auth.py`、`app/routers/auth.py`（新建）
  - `templates/login.html`（新建）
  - `app/routers/{rule,blacklist,case,agent,alert}.py`、`app/api.py`、`scripts/main.py`、`static/app.js`、`templates/base.html`（鉴权）
  - `.dockerignore`、`app/config.py`、`scripts/init_db.py`、`docker/*`（密钥卫生）

### Phase 2: P1 脱敏、审计、会话

- **Status:** complete
- **Started:** 2026-08-11（P0 收口后继续）
- Actions taken:
  - 2.1 日志脱敏：新建 `app/masking.py`（mask_value/mask_kwargs/mask_business_row/MaskQueryStringFilter）；`_safe_call` 参数掩码；uvicorn.access 查询串过滤
  - 2.2 LLM 上下文脱敏：`_query_business_data_impl` 返回前按 `LLM_DATA_MASK=True` 过滤姓名/诊断/收件人/卡号
  - 2.3 访问审计：新增 `risk_data_access_log` 表（ORM + create_all 补建），Agent 每次业务查询写审计行
  - 2.4 会话外置：新增 `agent_session` 表，chat.py 从内存 dict 迁 MySQL（message_to_dict/messages_from_dict），`_cleanup_expired_sessions` TTL 清理，`clear_session` 异步化；SYSTEM_PROMPT 改医疗版 + 黑名单只读
  - 2.5 验证：18 个新测试（masking 10 + agent_security 5 + session 3）；全量 pytest 447 passed；真实 app 冒烟通过
- Files created/modified:
  - `app/masking.py`、`tests/test_masking.py`、`tests/test_agent_security.py`（新建）
  - `app/models_risk.py`（新增 RiskDataAccessLog/AgentSession）、`app/models.py`、`app/database.py`、`scripts/init_db.py`（表数 17→19）
  - `app/agent/tools.py`、`app/agent/chat.py`、`app/routers/agent.py`、`app/logging_config.py`、`app/config.py`
  - `tests/test_agent_session.py`（重写）、`tests/test_agent_session_lock.py`（删除）
  - `README.md`、`sql/init_all.sql`（表数/测试数 447）

### Phase 0: 审查（已完成，非执行阶段）

- **Status:** complete
- **Started:** 2026-08-11 19:00（约）
- Actions taken:
  - 全量扫描鉴权：确认所有 router 无认证、无中间件
  - 确认 `.dockerignore` 漏 `.env`、三处默认口令、Agent 可写黑名单
  - 确认多 worker 调度器重复、session 进程内 dict、画像表电商字段残留
  - 确认 git 历史无 `.env`/密钥泄漏
  - 与用户确认聚焦安全合规 + 工程细节（真实数据暂不涉及）
- Files created/modified:
  - `.planning/2026-08-11-security-hardening/task_plan.md`（新建）
  - `.planning/2026-08-11-security-hardening/findings.md`（新建）
  - `.planning/2026-08-11-security-hardening/progress.md`（新建）

## Test Results

| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| 全量 pytest（上轮基线） | `pytest tests/ -k "not scheduler"` | 412 passed | 412 passed, 1 skipped, 1 deselected | ✓ |
| 规则命中率（上轮） | 30 天 × 200 条评估 | 19 规则全命中 | 19/19 命中，0.6%~19.7% | ✓ |
| 全量 pytest（P0 后） | `pytest tests/ -k "not scheduler"` | 429 passed | 429 passed, 1 skipped, 1 deselected | ✓ |
| 真实应用冒烟 | TestClient 全 app | 登录流正常 | /login 200；无 Token 写接口 401；登录后 me 200 | ✓ |
| 全量 pytest（P1 后） | `pytest tests/ -k "not scheduler"` | 447 passed | 447 passed, 1 skipped, 1 deselected | ✓ |
| P1 真实冒烟 | TestClient 全 app | 新表/chat 模块/鉴权正常 | /login 200；login 200；带 Token agent chat 200 | ✓ |

## Error Log

| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-08-11（上轮） | SQL 里 JSON `"qty":14` → bind parameter '14' | 1 | 冒号后加空格 `"qty": 14` |
| 2026-08-11（上轮） | aiomysql 关闭连接报 "Event loop is closed" | 1 | 仅退出噪音，功能正常；可忽略 |
| 2026-08-11（P0） | app.js fetch 包装在 Node 单测环境崩（window.fetch undefined） | 1 | 加 `typeof window !== 'undefined' && window.fetch` 防御 |
| 2026-08-11（P0） | get_dependant 返回的依赖可调用对象在 `d.call` 而非 `d.dependency` | 1 | 测试 helper 同时检查 `.call`/`.dependency` |
| 2026-08-11（P1） | 会话测试: 全局 async_engine 连接池跨 pytest 事件循环复用崩溃 | 1 | 每测试独立 engine/session, 用完 dispose |
| 2026-08-11（P1） | async generator fixture 被 pytest-asyncio 原样返回 | 2 | 弃用 fixture, 测试内 `_new_session()` 建独立 engine |
| 2026-08-11（P1） | 旧 test_agent_session_lock.py 断言内存锁, 已过时 | 1 | 删除, 架构断言并入 test_agent_session.py |

## 5-Question Reboot Check

| Question | Answer |
|----------|--------|
| Where am I? | Phase 1 (P0 安全合规最小闭环)，尚未开始执行 |
| Where am I going? | P0 → P1 脱敏审计会话 → P2 工程基建 |
| What's the goal? | 安全合规加固 + 工程细节修复，逐阶段验证提交 |
| What have I learned? | 见 findings.md（无鉴权/密钥入镜像/多 worker bug 等） |
| What have I done? | 审查完成，计划落盘（本文件） |
