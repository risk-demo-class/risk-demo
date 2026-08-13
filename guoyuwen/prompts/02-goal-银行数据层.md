# Goal 2：银行数据层与校验层

仅在 Goal 1 验收、提交并推送后使用。推荐在同一工作区新建对话并复制下面整个代码块；若留在原对话，先执行 `/goal clear`。

```text
/goal 完成银行风控重构的“任务 2：数据层”，持续推进直到 8 张银行业务表、DDL、初始化数据、可重复造数、事件配置、业务校验和数据库初始化全部通过验证，并提交推送到已创建的私有 GitHub 仓库；不得提前进入特征、规则或模型训练阶段。

开始前必须读取：
- `PROMPTS_README.md`
- `1-业务说明.md`
- `docs/refactor-contract.md`
- `docs/frontend-design-brief.md`
- `docs/baseline-test-report.md`
- `docs/goal-progress.md`
- 任务书：D:\Program Files\temp_data\尚硅谷大模型项目之风控系统\AI_Risk_行业风控实战任务书.md

前置检查：
- 确认当前工作区是 Goal 1 建立的独立 Git 仓库，分支为 `main`，`origin` 指向新建仓库且仓库可见性为 private。
- 确认 Goal 1 的提交已推送，工作区没有来源不明的改动。如有用户改动，保留并避开；不能安全区分时先报告。
- 遵守当前 AGENTS.md。不要自动调用或检查 Superpowers 插件技能，除非用户在当前消息显式使用完整 `$superpowers:<skill-name>`。

不变量与授权：
- 可以在当前项目内实现数据层、配置、校验、相应测试和必要文档，运行专用教学数据库的初始化与非破坏性验证，并提交推送到既有私有仓库。
- 只允许使用 `bank_risk` 和 `bank_risk_test`。不得连接、删除或重置名称不匹配的数据库；任何 `--reset/--drop` 必须显式指向这两个专用库并只使用虚构数据。
- 不修改 9 张核心风控表的表名、字段和语义，不改变 `process_event` 4 步及 `run_risk_check` 7 步流程。
- 外部 `RiskCheckRequest` 仍以 `event_type/source_id/user_id/event_data` 为四字段契约；现有可选 `order_id/receive_id` 可以保留作内部兼容，但不得成为银行调用方必填字段。
- 不使用真实身份证、银行卡、手机号、IP、姓名或客户数据。测试数据必须明显虚构，敏感标识使用假值、掩码或不可逆摘要。

目标数据模型：

实现并关联以下 8 张银行业务表；字段至少覆盖任务书要求，附合理的主键、非空、唯一约束、外键或逻辑关联、时间字段和后续特征查询所需索引。不要为了“通用化”增加未使用的抽象。

1. `UserInfo`：`user_id, name, id_card_hash, credit_score, register_at, kyc_level`。
2. `BankCard`：`card_id, user_id, card_no_hash, bank_code, card_type, credit_limit`，每用户可有多卡。
3. `Transaction`：`txn_id, from_card, to_card, amount, channel, device_id, ip, geo`，并包含事件时间。
4. `LoanApplication`：`loan_id, user_id, amount, term_months, purpose, monthly_income, debt_ratio`，并包含申请机构和申请时间，以支持多头借贷规则。
5. `LoginLog`：`login_id, user_id, device_id, ip, geo, success, login_at`。
6. `DeviceFingerprint`：`device_id, user_id, fingerprint_hash, first_seen, last_seen, os, browser`。
7. `IpGeoLocation`：`ip, country, province, city, isp, is_proxy, is_tor`。
8. `BlacklistExtra`：`entry_id, type, value, reason, expire_at`，作为银行外部/扩展名单数据源。

`BlacklistExtra` 不得取代或改表核心 `risk_blacklist`。在 `docs/refactor-contract.md` 中写清单一执行路径：扩展名单如何规范化或同步为核心 `risk_blacklist` 的银行类型；实时前置拦截仍通过现有核心黑名单服务完成，避免两个互相矛盾的执行真相。

事件与校验契约：

- `登录`：`source_id = LoginLog.login_id`，校验记录存在且属于 `user_id`。
- `转账`：`source_id = Transaction.txn_id`，校验交易存在，付款卡属于 `user_id`，且收付款卡关系有效。
- `贷款申请`：`source_id = LoanApplication.loan_id`，校验申请存在且属于 `user_id`。
- `绑卡`：`source_id = BankCard.card_id`，校验卡存在且属于 `user_id`。
- 错误事件类型与 source_id 组合返回明确 4xx；他人的卡、交易、贷款或登录记录不得借用，保留水平越权防护。

完成以下交付物：

1. ORM 与导出
- 将 `app/models_business.py` 从电商模型替换为上述 8 张银行表。
- 同步 `app/models.py` 或项目实际使用的模型导出入口；删除的电商模型引用必须只在受影响文件中处理，不顺带重构无关代码。
- ORM 模型与 DDL 的表名、字段、类型、默认值、可空性和索引保持一致。

2. SQL
- 重写 `sql/init_business_tables.sql`，只创建银行业务表；保持 `sql/init_risk_tables.sql` 的 9 张核心表契约不变。
- 重写 `sql/init_business_data.sql`，至少提供 100 条有业务意义的银行数据，并覆盖四类事件、正常样本和预设高风险样本。这里的 100 条不能只靠字典/地区参考行凑数；四类 source 业务记录合计至少 100 条。
- 调整 `sql/init_all.sql` 和 `scripts/init_db.py` 的说明、顺序、表数、数据库名与幂等行为。

3. 可重复造数
- 新增 `scripts/gen_business_data.py`，默认生成至少 100 条四类 source 业务记录。
- 最小必要参数为 `--count` 和 `--seed`；相同 seed 的数据分布应可复现。
- 采用幂等插入、唯一运行前缀或明确限定范围的清理，重复运行不得因主键冲突而半途失败，也不得默认清空整个数据库。
- 生成数据需包含正常与高风险模式：异地大额、凌晨密集、新设备大额、多卡归集、多头借贷、设备多人共用、代理/Tor、黑卡候选。
- 输出各表和各事件数量汇总，便于验收。

4. 配置、Schema 和校验
- 在 `app/config.py` 配置四类银行事件的风险阈值、银行规则分类和黑名单类型。
- 黑名单类型至少支持：`用户`、`设备指纹`、`IP`、`银行卡号`、`身份证号`；保持核心表结构不变。
- 更新 `app/schemas.py` 中事件和规则分类的 Literal/枚举、示例和说明，移除对调用方有误导的电商术语。
- 更新 `app/service/validator.py` 的事件派发表和归属校验，保留通用 `ensure_exists` 思路，避免为每张表复制相同 SQL。
- 此阶段只做保证导入/编译所需的最小引用适配；不要开始改写 feature、规则数据、event pipeline 或 XGBoost。
- 后端字段、枚举和 API 响应应与 `docs/frontend-design-brief.md` 的真实页面数据需求对齐，但本阶段不修改模板、CSS 或 JavaScript，不提前实现前端。

5. 测试与文档
- 新增或改写聚焦测试，至少覆盖：8 张表及关键索引、ORM/DDL 一致性、四类合法事件、四类 source 错配、水平越权、黑名单类型、造数可复现、100 条数量门槛、核心 9 表未变化。
- 不要通过删除断言、无条件 skip 或把真实校验替换成 mock 常量来让测试变绿。
- 更新 `docs/goal-progress.md`，记录 schema 决策、数据分布、验证命令和 Goal 3 前置条件。

验证要求：
- 运行格式/导入/相关 pytest。
- 对 `bank_risk_test` 完成一次从空库初始化，反射或查询确认 8 张银行业务表 + 9 张核心风控表存在。
- 执行 `scripts/gen_business_data.py --count 100 --seed 20260811`，确认成功、数量达标并覆盖四类事件。
- 重复执行同一命令，证明选定的重复运行策略有效。
- 查询确认核心 9 表结构与 Goal 1 契约一致。
- 运行项目完整测试，区分本阶段引入的失败和已记录的基线失败；修复本阶段回归。

Git 与停止条件：
- 提交信息聚焦于银行数据层；推送到 Goal 1 创建的 private `origin/main`。
- 推送前再次确认没有 `.env`、凭据、真实 PII、数据库转储或大体积临时文件；推送后回读私有可见性。
- 只有当 8 张表、100 条四事件数据、初始化、校验、相关测试、完整测试报告和私有仓库推送都有证据时才标记完成。
- 不实现 25 维特征、不写银行规则、不训练模型、不生成演示截图；这些属于 Goal 3。

最终报告列出：变更文件、8 张表及行数、四事件 source 映射、测试命令和结果、核心表不变证据、提交 ID、推送结果、Goal 3 尚待事项。无法运行某项验证时说明准确原因和复现命令，不得笼统宣称完成。
```
