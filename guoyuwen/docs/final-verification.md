# 银行风控项目最终验证报告（Goal 4）

> 验证日期：2026-08-12。本报告记录 Goal 4 全部交付物的最终验证证据：环境、数据库、四事件、规则/黑名单、模型、测试、浏览器、Docker/启动复现与已知限制。项目仅用于教学演示，所有数据均为虚构。

## 1. 日期、环境与版本

| 项 | 值 |
|---|---|
| 日期 | 2026-08-12 |
| 操作系统 | Windows 11 Home（China） |
| Python | 3.12.8（项目 `.venv`） |
| 关键依赖 | fastapi 0.115.6 / sqlalchemy 2.0.36 / xgboost 2.0.3 / pytest 8.3.4（`pip check` → No broken requirements found） |
| MySQL | Docker 容器 `ai-risk-goal3-mysql`（mysql:8.0），映射 `127.0.0.1:33307`，库 `bank_risk_test` |
| 应用服务 | `http://127.0.0.1:8000`（uvicorn `main:app --app-dir scripts`），HTTP 200 |
| Git HEAD | 以实际 `git log` 为准（本报告撰写时为 `2861680`；后续提交仅回填本报告证据，不含功能变更） |
| 私有仓库 | `https://github.com/LLLLWANGll/ai-risk-bank`（PRIVATE，默认分支 main） |

## 2. 数据库表数与关键行数

从空库按首次启动路径重建后反射 `bank_risk_test`：

| 类别 | 表 | 行数 |
|---|---|---|
| 业务 | `user_info` / `bank_card` / `bank_transaction` / `loan_application` / `login_log` / `device_fingerprint` / `ip_geo_location` / `blacklist_extra` | 510 / 625 / 625 / 625 / 625 / 515 / 25 / 8 |
| 核心 | `risk_rule` / `risk_blacklist` / `risk_event` / `risk_feature` / `risk_assessment` / `risk_case` / `risk_user_profile` / `risk_action_log` / `risk_alert` | 7 / 1 / 2012 / 50300 / 2012 / 449 / 508 / 244 / 0 |

- 表总数 17（8 业务 + 9 核心），与冻结契约一致。
- `risk_feature = 2012 × 25`，证明每次评估都落完整 25 维快照。
- 行数含训练数据（2000 条评估）与演示/测试样例；`risk_alert=0` 为预期（当前无触发条件）。

## 3. 四事件结果（API smoke，7 个样例）

`POST /api/risk/check`（`http://127.0.0.1:8000`），全部返回 200：

| 事件 | source_id | user_id | 决策 | 分数 | 等级 | 规则命中 | 备注 |
|---|---|---|---|---|---|---|---|
| 登录 | `DEMO_LOGIN_006` | `DEMO_USR_006` | 通过 | 0 | 低 | 0 | 25 维特征，ml≈0.003 |
| 转账 | `DEMO_TXN_001` | `DEMO_USR_002` | 拒绝 | 98 | 极高 | R001+R003+R007+R006 | ml≈0.987 |
| 转账 | `DEMO_TXN_003` | `DEMO_USR_002` | 拒绝 | 98 | 极高 | R004+R002+R007+R006 | ml≈0.996 |
| 转账 | `DEMO_TXN_008` | `DEMO_USR_010` | 拒绝 | 98 | 极高 | R001+R003+R007 | ml≈0.996 |
| 贷款申请 | `DEMO_LOAN_003` | `DEMO_USR_010` | 拒绝 | 85 | 极高 | R005 | ml≈0.996 |
| 绑卡 | `DEMO_CARD_003` | `DEMO_USR_003` | 通过 | 0 | 低 | 0 | 25 维特征，ml≈0.002 |
| 转账 | `DEMO_TXN_017` | `DEMO_USR_009` | 拒绝 | 100 | 极高 | 0 | `blocked_by=银行卡号`，黑名单短路，0 特征，未调用模型 |

四类事件全链路成立；黑卡样例 `rule_count=0` 且 `blocked_by` 明确区分黑名单拒绝与规则/模型拒绝。

## 4. 规则与黑名单样例

- 7 条数据库规则（`sql/init_risk_data.sql`）：`BANK_R001` 异地大额转账 / `BANK_R002` 凌晨密集操作 / `BANK_R003` 新设备大额 / `BANK_R004` 多卡归集 / `BANK_R005` 信贷申请突击 / `BANK_R006` 设备多人共用 / `BANK_R007` 代理/Tor IP。
- 黑名单前置控制：核心 `risk_blacklist` 存 `银行卡号` 黑卡（`SHA2('DEMO_CARD_NO_020',256)`，虚构值），命中直接拒绝，`rule_count=0`。
- 规则管理页可视化条件构建器、JSON 编辑、启停、分页均经浏览器操作验证。

## 5. 模型指标

`scripts/train_xgb_model.py` → `docs/model-metrics.json`（seed=20260812）：

| 指标 | 值 | 门禁 |
|---|---:|---:|
| 验证集 AUC | 1.0000 | ≥ 0.70 ✓ |
| 验证集 F1 | 1.0000 | ≥ 0.50 ✓ |
| 验证集 Precision / Recall | 1.0000 / 1.0000 | 记录项 |
| 验证集混淆矩阵 `[[TN,FP],[FN,TP]]` | `[[304,0],[0,85]]` | 记录项 |
| 训练集 / 验证集正例比 | 22.19% / 21.85% | 记录项 |
| 最佳迭代 | 50 | 记录项 |
| 特征完整率 | 100% | 记录项 |
| 用户重叠数（训练/验证） | 0 | 防泄漏 ✓ |

**重要说明**：AUC/F1=1.0 是教学虚构数据的干净合成结果（标签由规则产生、规则信号同时是输入），不表示真实泛化能力；已做泄漏复核（特征不含决策/规则/标签、用户无交集、固定 0.5 阈值），详见 `docs/model-evaluation.md`。

## 6. 测试证据

在专用 `bank_risk_test` 上运行：

| 套件 | 命令 | 结果 |
|---|---|---|
| 全量（排除 DDL 与 goal3 集成门控） | `pytest -q --basetemp=...` | **503 passed, 0 failed**, 27 skipped |
| DDL 实库验收 | `DDL_CHECK_ENABLED=1 pytest tests/test_ddl_sync.py` | **18 passed** |
| Goal3 集成（显式门控） | `GOAL3_DB_TEST=1 pytest tests/test_goal3_bank_integration.py` | **9 passed** |
| **并集合计** | | **530 passed, 0 failed** |

- 27 个默认跳过项均为显式门控：18 项 DDL（需 `DDL_CHECK_ENABLED=1`）、9 项 Goal3 集成（需 `GOAL3_DB_TEST=1`），开启后全部通过。
- 本 Goal 改动后无回归；`test_run_preflight.py` 因 `run_app.py` 不再硬编码 `localhost:3306/ecs` 而更新断言，仍 16 passed。

## 7. 前端设计简报符合性与双视口浏览器检查

对照 `docs/frontend-design-brief.md` 与 `docs/frontend-design.md`：

- 六页信息架构（总览/风险检查/规则/黑名单/案件/评估）与辅助 AI 助手入口一致；未新增基线没有的模型指标页。
- 设计 token、状态语义（绿黄橙红仅表风险）、统一阈值 30/60/85、API 绑定均一致。与简报的差异（操作蓝 `#18518A`、无黑名单拦截/事件分布指标卡）已在 `docs/frontend-design.md` 第 5 节记录真实理由。
- 本 Goal 的 UI 打磨：新增 `static/favicon.svg`（消除浏览器控制台 `/favicon.ico` 404）、`.btn` 触控目标提到 44px（对齐简报）、移除 `app.js` 调试 `console.log`。

浏览器实测（系统 Chrome + Playwright，真实提交表单）：

| 检查项 | 1440×900 | 390×844 |
|---|---|---|
| 六页横向溢出 | 全 0 | 全 0 |
| 控制台 error / pageerror | 0 / 0 | 0 / 0 |
| 风险检查（登录通过/转账拒绝/黑卡短路） | 决策正确渲染 | 决策正确渲染 |
| 移动抽屉导航（开合/焦点/Escape） | — | 通过 |
| 规则构建器（modal/JSON/查看 JSON） | 通过、无报错 | — |

8 张截图 `docs/screenshots/01-08.png` 已按最终 UI 重截，README 与演示脚本引用相对路径均存在。

## 8. Docker / 配置 / 启动复现

首次启动路径已在专用 `bank_risk_test` 完整执行（从空库）：

| 步骤 | 命令 | 结果 |
|---|---|---|
| 依赖安装检查 | `pip check` | No broken requirements found |
| 数据库初始化 | `scripts/init_db.py --db bank_risk_test --reset --yes` | 17 表重建 + 100 条演示 source + 7 规则 + 黑卡 |
| 业务造数 | `scripts/gen_business_data.py --count 2400 --seed 20260812` | 2400 条（四事件各 600），风险模式齐全 |
| 训练数据生成 | `scripts/gen_train_dataset.py --count 2000 --seed 20260812 --clean` | 2000 条，正例 22.2% |
| XGBoost 训练 | `scripts/train_xgb_model.py` | AUC/F1=1.0，模型保存 `app/engine/xgb_model.json` |
| 服务启动 | uvicorn `main:app --app-dir scripts` | HTTP 200 |
| 四事件 smoke | `POST /api/risk/check` × 7 | 全部符合预期（见第 3 节） |
| 测试 | `pytest` 并集 | 530 passed, 0 failed |

配置与脚本修复：`run_app.py` 预检从硬编码 `ecs/localhost:3306` 改为读取 `app.config.settings`（现显示 `root@127.0.0.1:33307/bank_risk_test`，risk_rule=7）；`docker/README.md`、`uv/README.md`、`app/logging_config.py` 移除过时 `gen_10w_data/_run.py` 电商命令；根目录新增 `.env.example`（`docker/.env.example` 已在），真实 `.env` 经 `git check-ignore` 确认被忽略；`docker-compose.yml` 数据库名 `bank_risk`、健康检查 `/docs` 均与银行语义一致。

## 9. Git 卫生与提交

- `git status` 工作树仅含本 Goal 的文档、UI 与测试改动；新增文件 `.env.example`、`agent_design.md`、`docs/demo-script.md`、`docs/recording-checklist.md`、`static/favicon.svg`、`面试问题与参考回答.md`。
- Git 跟踪文件扫描无 `.env`、令牌、数据库转储、日志、缓存或无用训练中间文件；`app/engine/xgb_model.json` 为体积受控（约 54KB）随代码交付的教学验收模型。
- 最终提交 ID 与私有仓库推送回读见下节。

## 10. 提交与私有仓库回读

| 项 | 值 |
|---|---|
| Goal 4 功能交付 | `3f6f87a`（文档）/ `fb8a9f0`（UI/启动修复）/ `dcecdc1`（重训产物） |
| 报告证据回填 | `c5577c7`、`cbbb4f6`、`2861680`（仅回填本报告字段，无功能变更） |
| 推送结果 | `a0db4cd..2861680 main -> main`（回读时以实际 HEAD 为准） |
| 本地 HEAD / 远端 main | 推送后一致（回读值见 Git 状态） |
| 仓库可见性回读 | `gh repo view LLLLWANGll/ai-risk-bank` → `visibility=PRIVATE`、`isPrivate=true`、默认分支 `main` |
| 基线仓库 | 未修改旧基线仓库，未创建公开镜像，未将私有仓库改为 public |

## 11. 用户录屏前最短操作步骤

已具备直接录制条件。录屏由用户按 `docs/demo-script.md` 与 `docs/recording-checklist.md` 完成：

1. 确认 MySQL 容器在跑：`docker ps` 见 `ai-risk-goal3-mysql`。
2. 启动服务：`.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --app-dir scripts`。
3. 打开 `http://127.0.0.1:8000/`，按 `docs/demo-script.md` 逐分钟演示（样例速查表见脚本末尾）。
4. 演示样例已内置并验证（`DEMO_LOGIN_006` / `DEMO_TXN_001` / `DEMO_TXN_017` / `DEMO_LOAN_003` 等）。

## 12. 已知限制与生产化差距

1. **教学数据与指标**：AUC/F1=1.0 是规则即标签的干净合成结果，不代表真实泛化；无时间外推集、人工复核标签与外部数据。
2. **已知遗留问题（本 Goal 范围外，除非用户要求否则未修）**：黑名单/规则软删重建可能 409/500（唯一索引不含 `deleted_at`，规则列表不过滤软删）；黑名单前端类型筛选跨页错乱；`test_rule_level_event_config.py` 的 API 400 契约未真测；`test_cond_builder_grid_layout.py` 为 JS 复刻测试。
3. **生产化差距**：无实时特征平台、模型监控/漂移检测、审批治理、角色权限（`RISK_FEATURES_FULL_RETURN` 仅全局开关）、可解释性（无 SHAP 级解释）、灾备与监管报送；特征每次查询聚合、`blacklist_extra` 同步任务为契约预留未实现。
4. **AI 助手**：依赖 `LLM_API_KEY`，未配置时降级提示，不属于核心验收。
5. **视频录制状态**：已达到可直接录制状态，**视频由用户按脚本录制**，本项目未录制也不声称已录制。
