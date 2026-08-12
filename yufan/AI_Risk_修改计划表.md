# AI_Risk 行业风控项目修改计划表

> 适用对象：第一次改完整 Python 项目的学习者  
> 工作目录：`C:\Users\Yf\Desktop\MyProject`  
> 老师基线：`C:\Users\Public\Nwt\cache\recv\吴玉祥\尚硅谷大模型项目之风控系统\3.代码\AI_Risk`  
> 任务依据：`AI_Risk_行业风控实战任务书.md`  
> 当前状态：已选择 **C 教育风控**，阶段 0—5 已完成；530 行教育业务正常与风险数据已生成并通过 MySQL 验证。

## 一、先做行业选择

在开始复制和改代码前，必须先确定一个行业。不同选择会直接改变业务表、事件类型、特征、规则和演示数据。

| 选择 | 难度 | 展示效果 | 是否适合小白 | 建议 |
|---|---:|---:|---:|---|
| C 教育风控 | 中 | 高 | 是 | **默认推荐**。任务书已给 6 张表和 8 条规则，容易讲清楚 |
| E 物流风控 | 低 | 中 | 是 | 代码容易，但表结构和规则需要自己补全 |
| H 共享经济 | 低 | 中 | 是 | 工作量小，但业务亮点略少 |
| A 旅游风控 | 中 | 高 | 较适合 | 表较多，适合时间充足时做 |
| B 银行 / F 医疗 | 高 | 高 | 否 | 涉及复杂业务和合规，不建议第一次独立完成 |
| D 制造 / G 电信 | 中 | 中 | 一般 | 需要额外行业知识 |

**已确定选择“C 教育风控”。** 后续按教育行业的业务实体、字段、事件、特征和规则实施。

## 二、修改边界（最重要）

| 分类 | 文件或模块 | 处理方式 | 注意事项 |
|---|---|---|---|
| 禁止修改 | `app/models_risk.py`、`sql/init_risk_tables.sql` | 原样复用 | 9 张风控核心表的表名、字段、关系不能改 |
| 禁止修改 | `app/engine/decision.py` | 原样复用 | `run_risk_check` 的 7 步流程不能改 |
| 禁止修改 | `app/engine/ml_model.py` | 原样复用 | 模型加载、预测、融合框架不改 |
| 禁止修改 | `app/schemas.py` 中请求/响应的 4 字段契约 | 保留结构 | `event_type, source_id, user_id, event_data` 必须保留；只替换行业枚举和描述 |
| 局部修改 | `app/engine/feature.py` | 重写行业特征函数 | 保留函数入口和返回 `dict[str, float]` 的形式 |
| 局部修改 | `app/engine/rule.py` | 通用匹配算法原样复用 | 行业规则优先放到 `sql/init_risk_data.sql`，不要把规则硬编码进算法 |
| 局部修改 | `app/service/event.py` | 只改业务补全和黑名单分支 | `process_event` 4 步总流程与调用顺序不变 |
| 必须重写 | `app/models_business.py` | 改成所选行业业务模型 | 不保留电商订单、物流、售后等无关实体 |
| 必须重写 | `sql/init_business_tables.sql` | 与 ORM 模型一一对应 | 表名、字段类型、外键、索引必须同步 |
| 必须重写 | `sql/init_business_data.sql` | 生成行业样例数据 | 至少 100 条有效业务数据，并包含正常和高风险样本 |
| 必须重写 | `scripts/gen_business_data.py` | 新增可重复造数脚本 | 固定随机种子；可重复执行；避免主键冲突 |
| 必须修改 | `app/service/validator.py` | 改事件到业务实体的派发表 | 每种事件都能用 `source_id` 查到正确业务表 |
| 必须修改 | `app/schemas.py` | 替换事件类型、规则分类 | 基线中“下单/支付/售后/物流投诉”等是硬编码的 |
| 必须修改 | 黑名单相关 schema、路由、前端 | 换成行业类型 | 例如教育：学号、身份证、设备指纹、直播账号 |
| 部分修改 | `templates/`、`static/app.js` | 替换电商文案和输入字段 | 至少保证风险检查页、规则页、案件页演示一致 |
| 必须重写 | `README.md`、`1-业务说明.md`、`agent_design.md` | 写自己的行业说明 | 不能继续显示“电商风控系统” |

## 三、8 学时执行计划

| 阶段 | 用时 | 要做什么 | 涉及文件 | 完成标志 | 状态 |
|---|---:|---|---|---|---|
| 0. 选行业与建备份 | 0.3h | 确定行业；保留当前 Git；列出禁止修改文件 | 本计划、Git | 行业写入 README 草稿；工作区可回退 | ✅ 已完成 |
| 1. 复用干净基线 | 0.4h | 把老师工程的源码、SQL、模板、测试和配置复制到 `MyProject` | `app/`、`scripts/`、`sql/`、`templates/`、`static/`、`tests/`、`docker/`、根目录文件 | 能看到完整项目结构 | ✅ 已完成 |
| 1.1 排除垃圾和秘密 | 0.1h | 不复制运行环境、缓存、日志和老师密钥 | `.venv/`、`uv/`、`.idea/`、`__pycache__/`、`.pytest_cache/`、`logs/`、`.env` | Git 中没有缓存、日志和真实密钥 | ✅ 已完成 |
| 2. 业务理解 | 1.2h | 写欺诈场景、关键字段、事件类型、术语表 | `1-业务说明.md` | 欺诈场景 ≥3；字段 ≥10；事件 ≥3；术语 ≥5 | ✅ 已完成 |
| 3. 设计业务数据模型 | 0.8h | 画业务实体关系；确定主键、外键、索引 | `app/models_business.py`、设计说明 | ORM 至少包含任务书要求的 N 张业务表 | ✅ 已完成 |
| 4. 同步 DDL | 0.5h | 把 ORM 转成 MySQL DDL；更新初始化顺序 | `sql/init_business_tables.sql`、`sql/init_all.sql`、`scripts/init_db.py` | ORM 与 DDL 表名/字段/类型一致 | ✅ 已完成 |
| 5. 生成业务数据 | 0.7h | 编写可重复造数；准备正常与风险样本 | `scripts/gen_business_data.py`、`sql/init_business_data.sql` | 数据 ≥100 条；至少有 3 类可命中规则的风险样本 | ✅ 已完成 |
| 6. 适配事件与校验 | 0.6h | 改事件枚举、来源校验、归属校验、请求补全 | `app/schemas.py`、`app/service/validator.py`、`app/service/event.py` | 每种 `event_type + source_id` 能正确校验；4 步流程未变 | ✅ 已完成 |
| 7. 适配黑名单 | 0.3h | 定义行业黑名单类型及检查字段 | schema、路由、service、SQL、前端 | 至少 3 类行业黑名单；命中后直接拒绝 | ✅ 已完成 |
| 8. 重写三大特征族 | 0.9h | 重写用户、业务单据、关联对象特征 | `app/engine/feature.py` | 三个 `compute_*_features` 可运行，所有值为数值 | ✅ 已完成 |
| 9. 编写行业规则 | 0.5h | 设计 8 条规则，写入初始化 SQL | `sql/init_risk_data.sql` | 规则 ≥5；建议 8；至少 3 条能命中风险样本 | ✅ 已完成 |
| 10. 训练 XGBoost | 0.6h | 生成训练集、训练、记录指标 | `scripts/gen_train_dataset.py`、`scripts/train_xgb_model.py` | 生成新模型；`val_auc ≥ 0.7`；输出 `val_f1` | ✅ 已完成 |
| 11. 前端与文案 | 0.5h | 替换电商事件、字段、示例和页面标题 | `templates/risk_check.html`、`templates/rules.html`、`templates/base.html`、`static/app.js` | 页面只展示所选行业的词汇和事件 | ✅ 已完成 |
| 12. 回归测试与演示 | 0.7h | 跑测试、风险检查、案件、历史记录；修复问题 | `tests/`、应用页面 | 主链路通过；1 个高风险用户被识别；准备 5–8 张截图 | ☐ 未开始 |
| 13. 提交文档 | 0.4h | 完善 README、LLM 协作复盘、演示提纲 | `README.md`、`agent_design.md`、截图目录 | 文档齐全；能按 5–8 分钟顺序讲完 | ☐ 未开始 |

> 合计约 8.5 小时。实际执行时可把“前端美化”压缩 0.5 小时，优先保证数据库、pipeline、规则、模型和验收证据。

## 四、默认推荐方案：教育风控文件映射

| 业务对象 | 建议表名 | 主键 | 关键字段 | 对应事件 |
|---|---|---|---|---|
| 用户 | `user_info` | `user_id` | 姓名、角色、学号、实名状态、注册时间、设备指纹 | 通用 |
| 课程 | `course` | `course_id` | 名称、分类、价格、教师、总学时 | 课程报名 |
| 报名订单 | `order_info` | `order_id` | 用户、课程、金额、学习目标、预计完成天数、创建时间 | 课程报名 |
| 学习进度 | `learning_progress` | `progress_id` | 用户、课程、学习分钟数、完成率、最后活跃时间 | 学习行为 |
| 退费申请 | `refund_request` | `refund_id` | 订单、原因、退费前学时、退费金额、申请时间 | 退费申请 |
| 直播打赏 | `live_reward` | `reward_id` | 用户、直播场次、金额、设备、打赏时间 | 直播打赏 |

建议事件类型：`课程报名`、`退费申请`、`直播打赏`、`学习行为`。任务书只要求 ≥3 种，多保留 1 种有利于展示。

建议黑名单类型：`用户`、`学号`、`身份证`、`设备指纹`、`直播账号`。

建议三大特征族映射：

| 任务书抽象 | 教育行业含义 | 特征例子 |
|---|---|---|
| 用户特征 | 学员/家长/老师账户历史 | 账号年龄、90 天退费次数、累计退费金额、关联课程数、关联设备账号数 |
| 订单特征 | 报名/退费/打赏单据 | 单笔金额、1 小时累计金额、是否夜间、学习时长、退费比例 |
| 地址特征 | 行业关联对象特征 | 将“地址”语义替换为“设备/身份关联”：设备关联用户数、是否新设备、实名是否一致 |

## 五、关键文件修改顺序

不要同时乱改多个模块，按下面顺序可以减少报错范围：

1. `1-业务说明.md`
2. `app/models_business.py`
3. `app/models.py`（检查是否正确导出新的业务模型）
4. `sql/init_business_tables.sql`
5. `scripts/init_db.py` 与 `sql/init_all.sql`
6. `scripts/gen_business_data.py` 与 `sql/init_business_data.sql`
7. `app/schemas.py`
8. `app/service/validator.py`
9. `app/service/event.py`
10. `app/engine/feature.py`
11. `sql/init_risk_data.sql`
12. 训练数据脚本与 `scripts/train_xgb_model.py`
13. `templates/`、`static/app.js`
14. `tests/`、`README.md`、`agent_design.md`

## 六、每阶段验收命令清单

以下命令是后续实施时的目标命令，数据库账号和 `.env` 配好后再运行。

| 检查目的 | 命令 | 通过标准 |
|---|---|---|
| Python 语法 | `python -m compileall app scripts` | 无 SyntaxError |
| 初始化数据库 | `python scripts/init_db.py --drop` | 完整执行，无缺表/外键错误 |
| 生成业务数据 | `python scripts/gen_business_data.py` | 成功写入 ≥100 条数据 |
| 单元测试 | `pytest tests/ -v` | 行业适配后的测试全部通过 |
| 生成训练集 | `python scripts/gen_train_dataset.py --reset` | 正负样本均存在，特征无空列 |
| 训练模型 | `python scripts/train_xgb_model.py` | `val_auc ≥ 0.7`，同时输出 `val_f1` |
| 启动应用 | `python run_app.py` | 浏览器可访问 `http://localhost:8000` |
| 风控主链路 | 页面或 `/api/risk/check` | 正常样本通过，高风险样本标记/审核/拒绝 |
| 数据历史 | 风险评估、案件管理页面 | 能看到刚才产生的评估和案件 |

## 七、最终提交物检查表

| 类别 | 提交物 | 验收标准 | 状态 |
|---|---|---|---|
| 业务 | `1-业务说明.md` | 场景 ≥3、字段 ≥10、事件 ≥3、术语 ≥5 | ☐ |
| 数据层 | `app/models_business.py` | N 张行业业务表，与电商版显著不同 | ☐ |
| 数据层 | `sql/init_business_tables.sql` | DDL 与 ORM 一致 | ☐ |
| 数据层 | `sql/init_business_data.sql` | ≥100 条业务数据 | ☐ |
| 数据层 | `scripts/gen_business_data.py` | 可重复执行 | ☐ |
| 校验 | `app/service/validator.py` | 所有行业事件均有派发表项 | ☐ |
| 配置 | 事件类型与黑名单类型 | ≥3 类事件，行业黑名单类型正确 | ☐ |
| 特征 | `app/engine/feature.py` | 三大特征族已行业化 | ☐ |
| 规则 | 行业规则 | ≥5 条，至少 3 条命中样例 | ☐ |
| 模型 | `xgb_model.json` 和训练输出 | `val_auc ≥ 0.7`，记录 `val_f1` | ☐ |
| 演示 | 5–8 张截图 | 风险检查、案件管理、评估历史都包含 | ☐ |
| 文档 | `README.md` | 安装、初始化、造数、训练、启动、演示步骤齐全 | ☐ |
| 复盘 | `agent_design.md` | 写明如何用 LLM、采用/修改了哪些建议 | ☐ |
| 视频 | 5–8 分钟录屏 | 业务 1 分钟、演示 2 分钟、模型 1 分钟、规则 2 分钟、复盘 1 分钟 | ☐ |

## 八、风险与防踩坑

| 风险 | 典型现象 | 预防办法 |
|---|---|---|
| 直接覆盖老师项目或当前 Git 文件 | 无法回退 | 只复制到 `MyProject`，每完成一个阶段做一次小提交 |
| 把老师 `.env` 一起复制 | 泄露数据库或 LLM 密钥 | 只创建 `.env.example`，真实 `.env` 不进 Git |
| ORM 与 SQL 不一致 | 初始化成功但运行时报“字段不存在” | 每次改模型同步改 DDL，并加 DDL 同步测试 |
| 改坏核心流水线 | 风险检查在中途断掉 | 不改 `process_event` 4 步顺序，不改 `run_risk_check` 7 步 |
| 只改后端没改 schema | 新事件请求返回 422 | 同步修改 `RiskCheckRequest`、`RuleCreate`、`RuleUpdate` 的 Literal |
| 只改 schema 没改 validator | 请求能进来但 `source_id` 校验错误 | 每个事件在 `_EVENT_SOURCE_VALIDATORS` 配置正确模型和主键 |
| 特征名与规则/模型不一致 | 规则永远不命中或训练列错位 | 建立统一特征清单，SQL 规则只引用清单中的名字 |
| 风险样本过少 | AUC/F1 很差或无法训练 | 造数时明确构造至少 3 种风险模式，并保持正常/风险样本比例合理 |
| 沿用旧模型 | 页面能跑但预测含义还是电商 | 删除/替换旧模型前先确认目标路径，然后用行业数据重新训练 |
| 前端仍是电商文案 | 演示时暴露未完成 | 全局搜索“订单、支付、售后、物流、电商”并逐项确认 |

## 九、建议的阶段性 Git 提交

| 次序 | 建议提交说明 |
|---:|---|
| 1 | `chore: import clean AI_Risk baseline` |
| 2 | `docs: add industry business analysis` |
| 3 | `feat: add industry business models and seed data` |
| 4 | `feat: adapt event validation and blacklist types` |
| 5 | `feat: implement industry features and rules` |
| 6 | `feat: train industry risk model` |
| 7 | `feat: adapt demo pages and documentation` |
| 8 | `test: verify industry risk workflow` |

## 十、下一步

正式修改前，只需先确定行业。若没有特别偏好，按本计划选择 **C 教育风控**，然后从“复用干净基线”开始；不要先手动复制单个文件，否则容易漏掉依赖。
