# Goal 进度记录

> 用途：记录各 Goal 的决定与验收证据，供最终 `agent_design.md` 汇总。更新日期：2026-08-12。

## 1. Goal 1 主要决定

- 选择银行方向，业务边界固定为信用卡、贷款、转账、登录；风控事件固定为 `登录/转账/贷款申请/绑卡`。
- 外部风险检查保持 `event_type/source_id/user_id/event_data` 四字段；`order_id/receive_id` 仅作内部兼容。
- 9 张核心风控表、`process_event` 四步和 `run_risk_check` 七步均冻结。
- 25 维模型输入继续保持 14 个 `user_*`、8 个 `order_*`、3 个 `addr_*`；银行语义按前缀族重新解释，任何重命名必须原子同步计算、模型、训练、前端和测试。
- 规则数据归 `sql/init_risk_data.sql`；`app/engine/rule.py` 保持通用解析与匹配职责。
- 开发/测试数据库名固定为 `bank_risk`/`bank_risk_test`。
- 前端采用“专业银行风险运营工作台”，不仿制真实银行品牌；基线没有模型指标页，因此不新增该页面承诺。
- 所有演示数据只能是虚构、掩码或哈希值；Goal 1 不改数据层、规则、特征、pipeline 或前端实现。

## 2. 验证证据

| 检查点 | 证据 |
|---|---|
| 源基线 | `384abb3d3f2f0f221ab98571ee19b0061a68c465`；导入前后均仅有未跟踪 `1-业务说明.md` |
| 导入边界 | 只导入源 `HEAD` 已跟踪内容；源 `.git`、未跟踪草稿和本地环境未复制 |
| 独立 Git | `main` 根提交 `e6592344e45d630bf6c9e94ea6cb46c8e270f078`，提交信息明确为电商重构基线 |
| 提示词保留 | `PROMPTS_README.md` 与 `prompts/` 已纳入目标仓库 |
| 测试收集 | 38 个文件，`pytest` 收集 451 项 |
| 完整测试 | `383 passed / 1 failed / 2 skipped / 65 errors`；失败原因见 `docs/baseline-test-report.md` |
| 可行子集 | `348 passed / 2 skipped / 4 deselected` |
| 业务调研 | 关键结论使用全国人大、中国人民银行、国家金融监督管理总局官方资料并标注访问日期 |
| 前端盘点 | 确认 7 个现有模板页、相关 API、公共 JS 与无独立模型指标页 |
| 私有仓库 | `https://github.com/LLLLWANGll/ai-risk-bank`；`gh repo view` 回读 `visibility=PRIVATE`、`isPrivate=true`、默认分支 `main` |
| 远端一致性 | 首次推送时本地 `HEAD` 与 `origin/main` 均为 `f4cbb8f1dbd803842f7f1e82f345702609331d26` |

## 3. Goal 1 交付状态

- [x] 根目录 `1-业务说明.md`
- [x] `docs/refactor-contract.md`
- [x] `docs/frontend-design-brief.md`
- [x] `docs/baseline-test-report.md`
- [x] 本文件
- [x] 独立本地 Git 基线
- [x] Goal 1 文档提交
- [x] 外部写入前秘密/PII 扫描：高置信度秘密、私钥、身份证、数据库转储均为 0；手机号候选均来自明确标注的 Faker/测试数据基线
- [x] 确认 GitHub 账户 `LLLLWANGll`，且同名仓库在创建前由连接器 404 与 `gh repo view` 不存在结果双重确认
- [x] 创建并回读验证 private 的 `ai-risk-bank`
- [x] 推送 `main`；最终提交后再次核对目标工作区与远端一致性

## 4. Goal 2 前置条件

进入 Goal 2 前必须同时满足：

1. 本文所列 Goal 1 交付项已提交并推送到经回读确认的私有仓库。
2. `docs/refactor-contract.md` 作为变更审查清单，任何提交不得破坏冻结项。
3. 以 `1-业务说明.md` 的四类事件和 `source_id` 映射设计业务表与造数脚本。
4. 先定义虚构数据字典、主外键和索引，再同步 SQLAlchemy、DDL、种子数据、validator 与测试。
5. MySQL 使用隔离的 `bank_risk_test`，凭据只放未跟踪 `.env`；不得对现有库执行破坏性初始化。
6. 修复或规避基线测试的旧绝对路径后，保留“改造前/改造后”可比测试证据。

Goal 2 的完成标准是银行业务表、至少 100 条可重复虚构数据、初始化流程和业务校验跑通；不得提前改动特征、规则、训练和完整前端，这些属于 Goal 3。

## 5. Goal 2 schema 与校验决策

- 业务层固定为 `user_info`、`bank_card`、`bank_transaction`、`loan_application`、
  `login_log`、`device_fingerprint`、`ip_geo_location`、`blacklist_extra` 8 张表。
- 身份证号和银行卡号只保存不可逆摘要；示例姓名、机构、地理位置和 IP 均为明显
  虚构或文档保留地址，不包含真实客户数据。
- `DeviceFingerprint` 使用 `(device_id, user_id)` 复合主键，既表达设备归属，又允许
  “同设备多人共用”风险样本；交易卡、用户、设备与 IP 通过外键或明确逻辑关联。
- 四事件来源固定为：`登录 → LoginLog.login_id`、`转账 → Transaction.txn_id`、
  `贷款申请 → LoanApplication.loan_id`、`绑卡 → BankCard.card_id`。
- 校验层复用通用 `ensure_exists`，再执行用户归属与转账收付款关系检查：错误事件/来源
  组合返回明确 400，借用他人记录返回 403。
- `blacklist_extra` 仅作扩展名单来源；实时拦截仍只通过核心 `risk_blacklist` 服务，
  规范化与同步规则见 `docs/refactor-contract.md`。
- 初始化脚本默认幂等，不删除数据库；只有显式 `--reset --yes` 且库名严格为
  `bank_risk` 或 `bank_risk_test` 时才允许重建。保留数据模式检测到核心规则后会跳过
  Goal 3 前的兼容规则种子，避免清空规则或 `risk_action_log` 历史。

## 6. Goal 2 数据分布与数据库证据

在独立临时 MySQL 8 实例的空 `bank_risk_test` 上完成初始化，没有连接或修改系统现有
数据库。静态种子与 `--count 100 --seed 20260811` 生成批次共同形成以下验收行数：

| 业务表 | 行数 |
|---|---:|
| `user_info` | 30 |
| `bank_card` | 50 |
| `bank_transaction` | 50 |
| `loan_application` | 50 |
| `login_log` | 50 |
| `device_fingerprint` | 35 |
| `ip_geo_location` | 18 |
| `blacklist_extra` | 8 |

四类 source 业务记录合计 200 条，其中静态 SQL 100 条、生成批次 100 条；生成批次固定
为登录、转账、贷款申请、绑卡各 25 条。相同命令重复执行后，生成前缀下四类记录仍各
25 条，证明幂等 upsert 不冲突、不清库。造数摘要同时确认覆盖异地大额、凌晨密集、
新设备大额、多卡归集、多头借贷、设备多人共用、代理/Tor 和黑卡候选。

反射结果为 17 张表：上述 8 张业务表加 9 张核心风控表。核心表字段数分别为
`risk_rule=14`、`risk_event=6`、`risk_feature=7`、`risk_assessment=11`、
`risk_case=13`、`risk_blacklist=7`、`risk_user_profile=13`、
`risk_action_log=10`、`risk_alert=12`，与 Goal 1 冻结契约一致。

## 7. Goal 2 验证记录

| 验证 | 命令 | 结果 |
|---|---|---|
| 空库初始化 | `python scripts/init_db.py --db bank_risk_test --reset --yes` | 8 张业务表、9 张核心表及两组种子数据全部成功 |
| 固定种子造数 | `python scripts/gen_business_data.py --count 100 --seed 20260811` | 四事件各 25 条，风险模式与逐表汇总完整输出 |
| 幂等复跑 | 连续第二次执行同一造数命令 | 成功；生成批次主键和数量不变 |
| ORM/DDL 实库反射 | `pytest -q tests/test_ddl_sync.py` | `18 passed` |
| Goal 2 聚焦回归 | `pytest -q tests/test_bank_data_layer.py tests/test_gen_business_data.py tests/test_validator_no_redundant_call.py tests/test_risk_decision.py` | `79 passed` |
| 完整测试 | `pytest -q` | `514 passed, 1 skipped`；跳过项为 Goal 3 才生成的真实 XGBoost 模型 |
| 静态检查 | `ruff check --select E9,F821 <Goal 2 Python 文件>` | 通过，无语法错误或未定义引用 |

## 8. Goal 3 前置条件

Goal 3 必须在本次提交推送并回读私有仓库后开始，并继续遵守以下边界：

1. 以已冻结的 8 张银行业务表重写 25 维特征来源，保持 14 个 `user_*`、8 个
   `order_*`、3 个 `addr_*` 的数量、顺序和模型 ABI；删除 `goal3_pending.py` 临时边界。
2. 将 `sql/init_risk_data.sql` 的兼容电商规则替换为银行规则，并同步训练数据、模型、
   API 展示和测试；本 Goal 未提前修改规则语义或训练模型。
3. 在数据和规则契约稳定后再改造 Agent 查询、模板、CSS 与 JavaScript；不得把教学
   阈值或模型结果描述为真实银行授信、反洗钱报告或账户处置结论。

## 9. Goal 3 实现决策

- 事件适配：四类银行事件全部走同一个 `process_event`；黑名单前置检查用户/设备
  指纹/IP/银行卡号/身份证号五类，命中即短路并返回 `blocked_by`，与“规则/模型
  拒绝”明确区分（黑卡样例 `rule_count=0`）。
- 25 维特征：14 个 `user_*` + 8 个 `order_*` + 3 个 `addr_*`，按银行语义重写查询
  来源；`FEATURE_COLUMNS` 与训练/推理脚本、`static/app.js` 的 `FEATURE_LABELS`、
  规则条件、测试同步，顺序完全一致。
- 8 个控制场景：7 个落 `risk_rule`（异地大额 R001、凌晨密集 R002、新设备大额 R003、
  多卡归集 R004、信贷突击 R005、设备多人 R006、代理/Tor R007）；黑卡场景保留为
  核心 `risk_blacklist` 前置控制（银行卡号哈希），故文档中该场景 `rule_count=0`。
- 造数与训练：脚本完成银行化，标签仍由规则/决策结果产生（通过/标记→0，
  人工审核/拒绝→1）；用 `GroupShuffleSplit(user_id)` 切分防止用户级泄漏；
  固定 seed `20260812`。
- 前端：全新“专业银行风险运营工作台”，深蓝/蓝灰 token，绿黄橙红只表风险状态；
  覆盖总览/风险检查/规则/黑名单/案件/评估六页，AI 助手保留为辅助入口。
- 数据边界：全程使用专用 Docker MySQL `ai-risk-goal3-mysql`
  （127.0.0.1:33307，`bank_risk_test`），不接触任何真实数据。

## 10. Goal 3 验证记录

| 验证 | 命令/方式 | 结果 |
|---|---|---|
| Goal 3 聚焦测试 | `pytest tests/test_goal3_bank_integration.py tests/test_goal3_bank_pipeline.py tests/test_goal3_frontend_routes.py` | 20 passed |
| 完整测试套件 | `pytest -q --basetemp=<临时目录>`（绕过沙箱临时目录权限） | 502 passed, 18 skipped（18 项均为 DDL 实库验收门控） |
| DDL 实库验收 | `pytest tests/test_ddl_sync.py`（`DDL_CHECK_ENABLED=1`） | 18 passed |
| 合计 | 并集 | 520 passed, 0 failed |
| 四事件 API smoke | `POST /api/risk/check` 共 7 个样例 | 见下表 |
| 模型指标 | `scripts/train_xgb_model.py` → `docs/model-metrics.json` | `val_auc=1.0` / `val_f1=1.0`（门禁 0.70/0.50） |
| 数据库快照 | `bank_risk_test` 反射 | 17 表；`risk_event` 2036、`risk_feature` 50900（2036×25）、`risk_rule` 7、`risk_blacklist` 1 |
| 浏览器验收 | 系统 Chrome + Playwright，1440×900 与 390×844 | 六页均无横向溢出；抽屉导航开合/跳转正常；三种风险检查结果正确渲染；服务端无 error/500/404 |

四事件 smoke 样例（最终决策 / 分数 / 等级 / 规则命中）：

| 样例 | 决策 | 分数 | 等级 | 规则 |
|---|---|---|---|---|
| 登录 `DEMO_LOGIN_006` | 通过 | 0 | 低 | 0 |
| 转账 `DEMO_TXN_001` | 拒绝 | 98 | 极高 | 异地大额 R001 + 新设备大额 R003 + 代理/Tor R007 + 设备多人 R006 |
| 转账 `DEMO_TXN_003` | 拒绝 | 98 | 极高 | 多卡归集 R004 + 凌晨密集 R002 + R007 + R006 |
| 转账 `DEMO_TXN_008` | 拒绝 | 98 | 极高 | R001 + 新设备大额 R003 + R007 |
| 贷款申请 `DEMO_LOAN_003` | 拒绝 | 85 | 极高 | 信贷申请突击 R005 |
| 绑卡 `DEMO_CARD_003` | 通过 | 0 | 低 | 0 |
| 转账 `DEMO_TXN_017` | 拒绝 | 100 | 极高 | `blocked_by=银行卡号`，`rule_count=0` |

## 11. Goal 3 交付状态

- [x] 四事件全链路，每事件落 25 条 `risk_feature` 快照
- [x] 25 维特征与 `FEATURE_COLUMNS`/训练/前端标签/测试同步
- [x] 8 个控制场景（7 规则 + 黑卡前置）
- [x] 至少 3 条规则命中、1 黑名单拒绝、1 高风险识别、1 正常通过
- [x] XGBoost 双指标达标并完成高分复核（`docs/model-evaluation.md`）
- [x] 全新前端完成双视口浏览器验收（`docs/frontend-design.md` 第 6 节）
- [x] 8 张截图 `docs/screenshots/`（01–08）
- [x] 完整测试证据（520 passed, 0 failed）
- [x] 聚焦提交并推送 private `origin/main`，回读确认（提交 `efdfae5`，本地与远端一致）

## 12. Goal 4 前置条件

1. Goal 3 验收通过、提交并推送到私有仓库，工作区干净。
2. 浏览器验收期间对教学库新增的评估/案件行不影响交付，无需清理。
3. 前端最终打磨、README、演示材料、录屏脚本、`agent_design.md` 与面试问答均
   未开始，全部保留给 Goal 4。

## 13. Goal 4 实现决策

- 前端统一打磨：新增 `static/favicon.svg`（消除浏览器控制台 `/favicon.ico` 404）、
  `.btn` 触控目标提到 44px（对齐简报）、移除 `app.js` 调试 `console.log`；双视口
  实测六页均无横向溢出、无控制台 error/pageerror、抽屉导航与规则构建器交互正常。
- 启动脚本修复：`run_app.py` 预检从硬编码 `ecs/localhost:3306` 改为读取
  `app.config.settings`；`docker/README.md`、`uv/README.md`、`app/logging_config.py`
  移除过时 `_run.py`/`gen_10w_data` 电商启动命令；根目录新增 `.env.example`
  （`docker/.env.example` 已在），真实 `.env` 确认被忽略。
- README 重写为银行风控启动与展示文档（PowerShell 命令）；`agent_design.md` 记录
  LLM 与四份 `/goal` 协作过程；`docs/demo-script.md` 5–8 分钟脚本与
  `docs/recording-checklist.md` 录屏清单；根目录 `面试问题与参考回答.md`（33 题，
  均基于最终代码/测试/Git/评估文档）；`docs/final-verification.md` 最终验证。
- 首次启动路径完整实测（从空库）：init_db 重置 → gen_business 2400 → gen_train 2000
  → train_xgb → 服务 smoke → 全量测试。

## 14. Goal 4 验证记录

| 验证 | 命令/方式 | 结果 |
|---|---|---|
| 从零初始化 | `init_db.py --db bank_risk_test --reset --yes` | 17 表 + 100 演示 source + 7 规则 + 黑卡 |
| 业务造数 | `gen_business_data.py --count 2400 --seed 20260812` | 2400 条（四事件各 600） |
| 训练数据 | `gen_train_dataset.py --count 2000 --seed 20260812 --clean` | 2000 条，正例 22.2% |
| 模型训练 | `train_xgb_model.py` | val_auc=1.0 / val_f1=1.0，best_iter=50 |
| 四事件 smoke | `POST /api/risk/check` 7 样例 | 全部符合预期（黑卡 `blocked_by=银行卡号`，`rule_count=0`） |
| 全量测试并集 | `pytest` + `DDL_CHECK_ENABLED=1` + `GOAL3_DB_TEST=1` | 530 passed, 0 failed |
| 浏览器验收 | 系统 Chrome + Playwright，1440×900 / 390×844 | 六页无溢出、无控制台错误；交互正确 |
| 截图复核 | `docs/screenshots/` 8 张重截 | 与最终 UI 一致 |
| 配置卫生 | `git check-ignore .env`；跟踪文件扫描 | `.env` 忽略；无令牌/PII/转储/日志/缓存 |
| 最终报告 | `docs/final-verification.md` | 已生成，含提交与回读证据 |

## 15. Goal 4 交付状态

- [x] 最终银行化 UI 与文案统一打磨（双视口浏览器验收）
- [x] 根目录 `README.md` 重写为银行风控启动与展示文档
- [x] `agent_design.md`
- [x] `docs/demo-script.md` 与 `docs/recording-checklist.md`
- [x] 根目录 `面试问题与参考回答.md`
- [x] Docker/配置/启动复现与 `.env.example`
- [x] `docs/final-verification.md` 与全量测试
- [x] 聚焦提交推送 private `origin/main` 并回读
- [x] 视频录制状态：已达到可直接录制状态，**视频由用户按脚本录制**
