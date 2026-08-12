📦 物流风控 — 详细需求文档
=====================

* * *

一、业务概述
------

### 1.1 业务边界

物流风控覆盖 **4 大核心场景**：

| 场景         | 说明            | 典型风险        |
| ---------- | ------------- | ----------- |
| 寄递实名       | 寄件人实名认证与身份核验  | 冒用身份证、虚假实名  |
| 危险品申报      | 寄递物品的危险品申报与检测 | 瞒报、伪报危险品    |
| 跨境包裹       | 国际件寄递与海关合规    | 违禁品、低报价值、走私 |
| 代收货款 (COD) | 货到付款场景的资金流转   | 卷款跑路、虚假签收   |

### 1.2 与电商风控的核心差异

| 维度    | 电商风控            | 物流风控               |
| ----- | --------------- | ------------------ |
| 核心对象  | **钱** (订单金额、支付) | **物** (包裹、重量、品类)   |
| 风控主体  | 买家 (单向)         | 寄件人 + 收件人 (双向)     |
| 事件触发点 | 下单、支付、退款        | 揽收、转运、签收、COD结算     |
| 特色数据  | 收货地址、设备指纹       | 面单条码、重量、保价、MSDS    |
| 监管强度  | 中等              | 极高 (邮政法、海关法、危化品条例) |

* * *

二、基线项目: 复用边界 (能复用哪些 / 必须改哪些)
----------------------------

> ⚠️ **这是任务里最重要的一张表，必须先看清楚边界再动手。**

| 模块               | 能不能动          | 说明                                                                                                                                                        |
| ---------------- | ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 风控核心 9 张表        | **完全复用, 不许改** | `risk_rule` / `risk_event` / `risk_feature` / `risk_assessment` / `risk_case` / `risk_blacklist` / `risk_user_profile` / `risk_action_log` / `risk_alert` |
| 风控引擎 4 个核心       | **完全复用**      | `app/engine/{decision, feature, rule, ml_model}.py` 不许改 schema, 只改特征计算函数                                                                                  |
| 决策流水线            | **完全复用**      | `process_event` 4 步 + `run_risk_check` 7 步不许改流程                                                                                                           |
| 行业业务表            | **必须重写 80%**  | `app/models_business.py` 跟业务强绑定, 每个行业重做                                                                                                                   |
| 行业特征计算           | **必须重写**      | `compute_user_features` / `compute_order_features` / `compute_address_features` 三大特征族                                                                     |
| 业务校验             | **必须重写**      | `app/service/validator.py::ensure_source_matches_event_type` 派发表                                                                                          |
| 业务黑名单类型          | **必须重写**      | 比如 "设备指纹" 在银行业才有, "IP 地址" 在所有行业都有                                                                                                                         |
| 业务事件类型           | **必须重写**      | 物流有 "寄递实名"、"危险品申报"、"跨境包裹"、"代收货款"                                                                                                                          |
| 业务数据生成脚本         | **必须重写**      | `gen_risky_users.py` / `gen_risk_data.py` 全部按行业重做                                                                                                         |
| 业务规则             | **必须全部重做**    | 数量自由 (5 条起步). 这是行业 know-how 的核心, 规则内容/阈值/决策等级全部按行业重做                                                                                                      |
| 前端 / 文档 / Docker | **部分复用**      | 框架能用, 业务字段要改                                                                                                                                              |

### 核心契约 (不可修改)

    process_event 接收 4 字段:
    RiskCheckRequest(event_type, source_id, user_id, event_data)
    
    返回:
    RiskCheckResponse

这层契约不能改，是自由发挥的边界。

* * *

三、业务表设计 (7 张)
-------------

### E.1 必须有的业务表

| #   | 表名                     | 核心字段                                                                                                        | 跟电商版的差异                                              |
| --- | ---------------------- | ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| 1   | `UserInfo`             | `user_id`, `name`, `real_name_status`, `account_type`, `register_at`                                        | 区分**个人/企业**寄件人 (`account_type`: personal/enterprise) |
| 2   | `Parcel`               | `parcel_id`, `sender_id`, `receiver_id`, `weight_kg`, `declared_value`, `item_category`, `is_international` | 包裹 (电商"订单"变"包裹"，业务核心是"**物**"不是"钱")                   |
| 3   | `SenderInfo`           | `sender_id`, `name`, `id_type`, `id_number`, `phone`, `address`, `is_blacklisted`                           | 寄件人实名 (电商的"买家"是收件人，物流**寄收双方都是风控对象**)                 |
| 4   | `ReceiverInfo`         | `receiver_id`, `name`, `phone`, `address`, `is_proxy_received`                                              | 收件人，1 包裹 1 收件人；`is_proxy_received` 标记是否代签收           |
| 5   | `DangerousDeclaration` | `decl_id`, `parcel_id`, `item_type`, `is_liquid`, `is_battery`, `msds_url`, `declared_at`                   | 危险品申报 (**物流专属**，电商没这个)                               |
| 6   | `CodTransaction`       | `cod_id`, `parcel_id`, `amount`, `cod_status`, `paid_at`, `returned_at`                                     | 代收货款流水 (**物流专属**，货到付款跟电商"已付款"完全不同)                   |
| 7   | `BlacklistExtra`       | `entry_id`, `type`, `value`, `reason`, `expire_at`                                                          | `type` 加 **身份证号 / 手机号 / 地址 / 面单条码**                  |

### E.2 表关系 ER 图 (文字描述)

    UserInfo (1) ──── (N) Parcel
    SenderInfo (1) ──── (N) Parcel
    ReceiverInfo (1) ──── (N) Parcel
    Parcel (1) ──── (0..1) DangerousDeclaration
    Parcel (1) ──── (0..1) CodTransaction

### E.3 字段详细说明

#### `Parcel` (核心业务表)

| 字段名                | 类型         | 必填  | 说明                                        |
| ------------------ | ---------- | --- | ----------------------------------------- |
| `parcel_id`        | String(32) | ✅   | 主键，面单号                                    |
| `sender_id`        | String(32) | ✅   | FK → SenderInfo                           |
| `receiver_id`      | String(32) | ✅   | FK → ReceiverInfo                         |
| `weight_kg`        | Float      | ✅   | 实际称重 (kg)                                 |
| `declared_value`   | Float      | ✅   | 申报价值 (元)                                  |
| `item_category`    | String(50) | ✅   | 物品类目 (电子产品/服装/食品/化工品/普通)                  |
| `is_international` | Boolean    | ✅   | 是否国际件                                     |
| `piece_count`      | Integer    | ❌   | 货物件数 (用于"大额低报"规则)                         |
| `status`           | String(20) | ❌   | 状态: created/in_transit/delivered/returned |
| `created_at`       | DateTime   | ✅   | 揽收时间                                      |

#### `CodTransaction` (代收货款)

| 字段名            | 类型         | 必填  | 说明                            |
| -------------- | ---------- | --- | ----------------------------- |
| `cod_id`       | String(32) | ✅   | 主键                            |
| `parcel_id`    | String(32) | ✅   | FK → Parcel                   |
| `amount`       | Float      | ✅   | 代收金额 (元)                      |
| `cod_status`   | String(20) | ✅   | pending/paid/returned/overdue |
| `paid_at`      | DateTime   | ❌   | 实际付款时间                        |
| `returned_at`  | DateTime   | ❌   | 退回时间                          |
| `days_overdue` | Integer    | ❌   | 逾期天数 (签收后未付款)                 |

* * *

四、业务事件类型设计
----------

| 事件类型 (`event_type`) | 触发时机   | `source_id` 指向                 | 说明                |
| ------------------- | ------ | ------------------------------ | ----------------- |
| `parcel_pickup`     | 揽收下单   | `Parcel.parcel_id`             | 寄件人提交寄件，触发实名+物品校验 |
| `dangerous_declare` | 危险品申报  | `DangerousDeclaration.decl_id` | 申报危险品时触发合规检查      |
| `cross_border_ship` | 跨境发运   | `Parcel.parcel_id`             | 国际件出关前触发违禁品+价值校验  |
| `cod_settlement`    | COD 结算 | `CodTransaction.cod_id`        | 代收货款结算时触发资金风险检查   |

### 事件派发表 (`validator.py`)

    EVENT_SOURCE_MAP = {
        "parcel_pickup": "Parcel",
        "dangerous_declare": "DangerousDeclaration",
        "cross_border_ship": "Parcel",
        "cod_settlement": "CodTransaction",
    }

* * *

五、业务规则设计 (8 条起步)
----------------

### E.2 必有的业务规则

| 编号   | 规则名    | 触发条件                                    | 风险等级 | 决策       |
| ---- | ------ | --------------------------------------- | ---- | -------- |
| R001 | 实名不一致  | 寄件人身份证号 + 手机号在权威源不匹配                    | 极高   | **拒绝揽收** |
| R002 | 危险品瞒报  | 申报类目为"普通" + 重量异常 > 50kg + 国际件           | 极高   | **拒绝揽收** |
| R005 | 跨境违禁品  | 国际件 + 物品类目命中违禁品库 (锂电池/液体/粉末)            | 极高   | **拒绝**   |
| R008 | 代收货款卷款 | COD 包裹签收 30 天后仍未付款 + 寄件人月均 ≥ 3 单        | 高    | **人工审核** |
| R012 | 同地址高频  | 同一收件地址 24 小时内 ≥ 10 个不同寄件人               | 高    | **人工审核** |
| R018 | 改派异常   | 1 票包裹改派 ≥ 3 次 + 每次改派地址跨省                | 中    | **标记**   |
| R025 | 大额低报   | 申报价值 < 100 元 + 实际货物件数 ≥ 5 件 + 重量 > 20kg | 中    | **标记**   |
| R030 | 黑地址拦截  | 收件地址在黑名单                                | 极高   | **拒绝**   |

### 规则实现要求

每条规则需要实现：

1. **`match` 函数**: 判断是否命中规则
2. **`score` 阈值**: 对应的风险分数
3. **`enabled=True`**: 必须在数据库中启用
4. **`db.commit()`**: 注册后必须提交

* * *

六、黑名单类型设计
---------

| `type` 值          | 说明         | 示例 `value`           |
| ----------------- | ---------- | -------------------- |
| `id_number`       | 身份证号       | `110101199001011234` |
| `phone`           | 手机号        | `13800138000`        |
| `address`         | 收件/寄件地址    | `广东省深圳市XX路XX号`       |
| `waybill_barcode` | 面单条码       | `SF1234567890`       |
| `ip_address`      | IP 地址 (通用) | `192.168.1.1`        |

* * *

七、特征计算设计 (3 大特征族)
-----------------

> 必须重写 `app/engine/feature.py` 中的 3 个函数，返回字段名必须与 `FEATURE_COLUMNS` (25 维) 对齐。

### 7.1 `compute_user_features` → 寄件人特征

| 特征名 (示例)                 | 计算逻辑         |
| ------------------------ | ------------ |
| `account_age_days`       | 注册至今天数       |
| `real_name_verified`     | 是否实名认证 (0/1) |
| `is_enterprise`          | 是否企业账号 (0/1) |
| `total_parcel_count_30d` | 近 30 天寄件总量   |
| `cod_overdue_count`      | COD 逾期次数     |
| `blacklist_hit_count`    | 关联黑名单命中次数    |

### 7.2 `compute_order_features` → 包裹特征 (原电商"订单"族)

| 特征名 (示例)                | 计算逻辑                                |
| ----------------------- | ----------------------------------- |
| `weight_kg`             | 包裹重量                                |
| `declared_value`        | 申报价值                                |
| `value_per_kg`          | 单位重量价值 (declared_value / weight_kg) |
| `piece_count`           | 货物件数                                |
| `is_international`      | 是否国际件 (0/1)                         |
| `is_dangerous_declared` | 是否申报危险品 (0/1)                       |
| `has_cod`               | 是否代收货款 (0/1)                        |
| `cod_amount`            | COD 金额                              |

### 7.3 `compute_address_features` → 地址特征

| 特征名 (示例)                        | 计算逻辑               |
| ------------------------------- | ------------------ |
| `sender_province`               | 寄件省份 (编码)          |
| `receiver_province`             | 收件省份 (编码)          |
| `is_cross_province`             | 是否跨省 (0/1)         |
| `same_address_sender_count_24h` | 同一收件地址 24h 内不同寄件人数 |
| `address_blacklist_hit`         | 地址是否命中黑名单 (0/1)    |
| `is_proxy_received`             | 是否代签收 (0/1)        |

* * *

八、数据生成要求
--------

### 8.1 高风险种子用户 (`gen_risky_users.py`)

需造 **20-30 个**高风险种子用户，覆盖以下画像：

| 画像类型      | 数量   | 特征                |
| --------- | ---- | ----------------- |
| 实名异常用户    | 5    | 身份证与手机号不匹配        |
| 危险品瞒报用户   | 5    | 申报"普通"但实际寄化工品     |
| 跨境违禁品用户   | 5    | 频繁寄国际件 + 锂电池/液体   |
| COD 卷款用户  | 5    | 大量 COD 单 + 长期逾期   |
| 高频刷单用户    | 5    | 同一地址 24h 内大量不同寄件人 |
| 正常用户 (对照) | 5-10 | 所有指标正常            |

### 8.2 评估数据 (`gen_risk_data.py`)

| 要求     | 指标                     |
| ------ | ---------------------- |
| 总量     | 500 - 2000 条           |
| 正例比例   | ≥ 15% (即至少 75 条被标记为风险) |
| 事件类型覆盖 | 4 种 `event_type` 都要有   |
| 风险等级覆盖 | 极高/高/中/低 至少 3 种        |

### 8.3 补数据命令

    # 如果正例比例不足 15%，先跑这个补齐
    python scripts/gen_risk_data.py --balance-pos

* * *

九、验收标准
------

### 9.1 任务 2 验收 (数据层 + 规则引擎)

* [ ] `python -m app.service.validator` 能跑通 (demo 块不报错)
* [ ] `python scripts/init_db.py --reset --yes` 能建表
* [ ] `python scripts/gen_risky_users.py` 能造种子用户
* [ ] `python scripts/gen_risk_data.py` 能造数据，正例比例 ≥ 15%

### 9.2 任务 3 验收 (端到端 + XGBoost)

* [ ] 浏览器能打开前端 (`http://localhost:8000/`)
* [ ] 至少 1 条规则触发"拒绝"决策 (case 列表可见)
* [ ] XGBoost 模型能成功加载 + 推理 (前端 ML 评分显示非 0)
* [ ] `val_auc ≥ 0.7`
* [ ] `val_f1 ≥ 0.5`
* [ ] `is_fake_convergence = False`
* [ ] `pytest tests/ -k "not scheduler"` 通过 200+ 个

### 9.3 唯一硬底线

> **跑通端到端 + 至少跑出 1 次"非通过"的决策**

* * *

十、任务节奏 (8 学时)
-------------

| 阶段             | 时长   | 产物                                                        |
| -------------- | ---- | --------------------------------------------------------- |
| 任务 1: 业务理解     | 2h   | `docs/行业分析.md` + `docs/业务表设计.md` + `docs/规则设计.md`         |
| 任务 2: 数据层改造    | 2h   | 改写 `models_business.py` + `feature.py` + `rule.py` + 数据脚本 |
| 任务 3: 端到端 + 训练 | 2.5h | 跑通 pipeline + XGBoost 训练达标                                |
| 任务 4: 演示 + 提交  | 1.5h | README 更新 + Git 提交 + 讲解 PPT                               |

* * *

十一、纪律约束
-------

1. **风控 9 张表不许改 schema**: 动了就回到原始项目重新对齐
2. **`process_event` 4 步流程不许改**: 动了会破坏下游所有 hook 点
3. **规则必须能讲清楚**: 每条都要能讲出"为什么这条规则在物流行业有效"
4. **Git 仓库要求**:
   * 至少 15 次 commit (个人)
   * commit message 规范 (`feat: 改写物流业务表` / `fix: 修复规则匹配 bug`)
5. **代码量下限**: ≥ 1500 行 (含注释)，含测试 ≥ 30 个

* * *

十二、常见翻车点 (提前警告)
---------------

| #   | 翻车点                              | 后果                                                                      | 预防                           |
| --- | -------------------------------- | ----------------------------------------------------------------------- | ---------------------------- |
| 1   | 改 schema 时漏改 Pydantic            | `app/schemas.py::RiskCheckRequest` 跟 `models_business.py` 是双胞胎，漏一个就跑不起来 | 每改一个 model 就同步改 schema       |
| 2   | 特征函数返回字段名跟 `FEATURE_COLUMNS` 不一致 | 训练时 25 维，推理时 key 错位，ml_score 全是 0                                       | 打印 `FEATURE_COLUMNS` 逐一核对    |
| 3   | 规则 `enabled=False`               | 前端永远看不到规则                                                               | 注册后立即 `db.commit()`          |
| 4   | 训练数据全是 0 标签                      | XGBoost 训练失败 (val_auc=0.5)                                              | 确保正例 ≥ 15%                   |
| 5   | XGBoost 模型没回填                    | 前端 ML 评分永远是 0                                                           | 训完必须跑 `backfill_ml_score.py` |


-----------------
