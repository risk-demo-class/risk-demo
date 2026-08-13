# 银行风控重构契约

> 适用范围：Goal 1 形成边界，供 Goal 2–4 执行。Goal 1 不修改数据层、规则、特征、pipeline 或前端实现。

## 一、保持不变

1. **核心风控表契约**：`risk_rule`、`risk_event`、`risk_feature`、`risk_assessment`、`risk_case`、`risk_blacklist`、`risk_user_profile`、`risk_action_log`、`risk_alert` 的表名与既有字段契约保持不变；业务表不得反向要求修改这 9 张表。
2. **`process_event` 四步顺序**：
   1. 业务实体校验；
   2. 补全内部兼容字段；
   3. 黑名单前置检查；
   4. 调用决策引擎。
3. **`run_risk_check` 七步顺序**：
   1. 准备上下文；
   2. 创建事件记录；
   3. 计算特征；
   4. 保存特征快照；
   5. 加载并匹配规则；
   6. 计算决策；
   7. 原子落库并响应。
4. **外部请求契约**：对外只要求 `event_type/source_id/user_id/event_data`。`order_id/receive_id` 可在内部继续承接基线兼容逻辑，但不得成为银行 API 新增必填参数。
5. **固定枚举与数据库名**：事件固定为 `登录`、`转账`、`贷款申请`、`绑卡`；开发库为 `bank_risk`，测试库为 `bank_risk_test`。
6. **25 维输入形状**：保持 14 个 `user_*`、8 个 `order_*`、3 个 `addr_*`，总数、顺序和前缀族不变，避免训练与推理列错位。

## 二、必须改造

下列工作从 Goal 2 起进行，Goal 1 只记录契约：

- 将 `app/models_business.py` 与 `sql/init_business_tables.sql` 从电商模型替换为银行业务模型，覆盖用户、银行卡、转账、贷款申请、登录、设备指纹、IP/地理环境等必要实体。
- 将 `sql/init_business_data.sql` 和业务造数脚本改为完全虚构、可重复生成的银行演示数据。
- 将 `app/schemas.py` 的业务事件枚举、`app/service/validator.py` 的 `source_id` 派发表、`app/service/event.py` 的内部补全与黑名单维度改成银行语义，同时保留外部四字段契约与流程顺序。
- 将开发/测试数据库名改为 `bank_risk`/`bank_risk_test`，并同步初始化脚本、Docker 示例和文档。
- 重写三类特征的计算来源：`user_*` 面向客户历史，`order_*` 面向当前业务事件，`addr_*` 面向设备/IP/地理环境。
- 将电商规则数据替换为银行规则数据，并改造前端电商视觉、文案与字段标签。

## 三、同步修改

### 1. 业务模型与事件链

每次业务表或字段变更必须在同一变更集中同步：

`models_business.py` → `sql/init_business_tables.sql` → `sql/init_business_data.sql`/生成脚本 → `schemas.py` → `validator.py` → `event.py` → 相关 API、前端标签与测试。

四类事件的 `source_id` 映射固定为：

| 事件 | `source_id` |
|---|---|
| `登录` | `LoginLog.login_id` |
| `转账` | `Transaction.txn_id` |
| `贷款申请` | `LoanApplication.loan_id` |
| `绑卡` | `BankCard.card_id` |

### 2. 25 维特征兼容策略

当前顺序是 `ml_model.FEATURE_COLUMNS` 的模型输入 ABI。Goal 1 不重命名任何列；后续如重命名银行语义，必须一次性同步以下位置并用测试证明顺序一致：

- `app/engine/feature.py` 的 `compute_user_features`、`compute_order_features`、`compute_address_features`；
- `app/engine/ml_model.py::FEATURE_COLUMNS`；
- `scripts/gen_train_dataset.py`、`scripts/train_demo_model.py`、`scripts/train_xgb_model.py` 及回填脚本；
- `static/app.js::FEATURE_LABELS` 和使用特征名的模板；
- `tests/test_feature_optimization.py`、`tests/test_xgboost.py`、训练与前端契约测试。

兼容命名解释：

- `user_*`：14 维客户历史与关联画像，不限定为订单；
- `order_*`：8 维“当前业务事件”特征，为兼容模型形状保留 `order_` 前缀，可对应登录、转账、贷款申请或绑卡；
- `addr_*`：3 维设备/IP/地理环境特征，为兼容模型形状保留 `addr_` 前缀，不再等同于收货地址。

在特征来源尚未由 Goal 2 的业务表稳定前，不提前决定新列名，避免同一契约反复迁移。

### 3. 规则职责

- 银行业务规则数据统一进入 `sql/init_risk_data.sql`，规则条件只引用 25 维特征或明确的事件上下文。
- `app/engine/rule.py` 只保留通用 JSON 条件解析、操作符比较、递归 `and/or` 和规则匹配职责；不得在其中硬编码银行阈值或业务表查询。
- 规则类别、事件枚举、前端筛选项和规则测试必须同步更新。

### 4. 扩展名单的单一执行路径

`blacklist_extra` 是银行外部或扩展名单的接入数据源，不是实时决策表，也不得取代
核心表 `risk_blacklist`。名单接入流程必须先校验 `type/value/reason/expire_at`，再按以下
规则规范化并幂等同步到 `risk_blacklist`：

- `用户`、`设备指纹`、`IP` 直接使用系统内部标识或规范化 IP；
- `银行卡号`、`身份证号` 只接收不可逆摘要或掩码后的标识，不保存明文；
- 同一 `blacklist_type + blacklist_value` 更新原因、状态和有效期，不创建相互冲突的
  重复执行记录；扩展名单失效或撤销时，同步更新核心名单状态。

实时前置拦截只调用现有 `check_blacklist` 服务并查询 `risk_blacklist`。业务事件处理
不得同时直接查询 `blacklist_extra`，避免扩展表与核心表形成两个互相矛盾的执行真相。
Goal 2 只建立数据结构和该同步契约；自动同步任务及管理界面属于后续 Goal。

## 四、明确不做

- Goal 1 不修改银行业务表、SQL 业务数据、特征实现、规则数据、`process_event`、`run_risk_check`、模板、CSS 或 JavaScript。
- 不改 9 张核心风控表，不新增外部 API 必填字段，不改变两条 pipeline 的顺序或事务边界。
- 不导入源仓库 `.git`、未跟踪草稿、`.env`、缓存、日志、虚拟环境、数据库文件或凭据。
- 不使用真实 PII，不仿制真实银行名称、Logo、商标或完整品牌视觉。
- 不把教学阈值、模型分数或规则命中当作生产授信、反洗钱报告或账户处置结论。
- 不在基线没有能力支持时虚构模型指标页或后台接口。
