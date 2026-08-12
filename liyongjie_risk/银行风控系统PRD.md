# 银行风控系统 PRD（需求文档）

版本：v0.1 ｜ 日期：2026-08-11

## 1. 文档目的

定义银行风控系统的业务需求，覆盖**登录、转账、信用卡、贷款**四大场景，实现从事件接入、风险识别、决策处置到名单与画像闭环的全流程能力，作为研发、测试与验收的依据。

## 2. 业务范围

- 四大业务场景：登录、转账、信用卡、贷款；
- 核心能力：名单管理、规则引擎、模型评分、风险事件记录、人工审核、账户处置（限额/冻结/止付）；
- 边界说明：本系统输出可疑事件与预警，大额/可疑交易报告报送由合规系统承接，不在本系统范围内。

## 3. 名词定义

| 术语 | 定义 |
| --- | --- |
| 事件 | 一次可风控的业务动作（登录、转账、贷款申请等），携带统一风险要素 |
| 风险等级 | 低 / 中 / 高 / 极高，由规则或模型判定 |
| 决策 | PASS 放行 / CHALLENGE 增强验证 / MANUAL 人工复核 / REJECT 拒绝 |
| 处置 | 决策后的动作：TAG 标记 / LIMIT 限额 / FREEZE 冻结 / STOP_PAYMENT 止付 / REPORT 上报 |
| 名单 | 设备、IP、卡号、身份证、手机号等维度的风险名单，含内部与外部来源 |
| 画像 | 用户、设备、城市维度的历史行为画像（常用城市、常用设备、交易习惯） |
| KYC 等级 | 开户身份核验强度：L1 要素核验 → L2 人脸 → L3 证件上传 → L4 面签 |

## 4. 业务场景与流程

### 4.1 登录场景

用户发起登录 → 采集设备指纹与 IP → 名单校验（设备、IP）→ 规则判断（新设备/异地/凌晨/多人共用/代理）→ 决策。

- 放行：记录 LoginLog（success=1）；
- 增强验证：短信/人脸，通过后放行；
- 拒绝：记录 LoginLog（success=0, fail_reason），必要时联动冻结登录。

关联数据：LoginLog、DeviceFingerprint、IpGeoLocation、BlacklistExtra、UserProfile。

### 4.2 转账场景

用户发起转账 → 校验发卡、收卡要素 → 对手方名单校验（黑卡/涉诈卡）→ 规则判断（金额、频次、时间、设备、城市、归集、试探）→ 决策。

- 放行：执行交易；
- 增强验证：二次确认/人脸；
- 人工复核：交易挂起进入人工队列，按人工结论放行或拒绝；
- 拒绝：交易不执行；命中极高风险规则可联动冻结/止付账户或收款卡。

关联数据：Transaction、BankCard、BlacklistExtra、RiskEvent。

### 4.3 贷款场景

提交申请 → 身份核验（KYC）→ 征信与收入校验（多头、负债、查询次数）→ 申请环境校验（设备/IP 团伙）→ 申请反欺诈评分 → 决策（自动通过/拒绝/人工）→ 放款 → 放款后资金监控（快进快出、放款即转）→ 贷后逾期/失联监控。

关联数据：LoanApplication、UserInfo、DeviceFingerprint、BlacklistExtra、RiskEvent。

### 4.4 信用卡场景

申请（复用贷款申请反欺诈）→ 审批发卡 → 交易监测（盗刷、套现、养卡）→ 额度调整（提额触发人工复核）→ 还款与逾期监控（首逾）。

关联数据：BankCard、Transaction、LoanApplication（申请记录）、RiskEvent。

## 5. 事件类型定义

| 事件类型 | 阶段 | 说明 |
| --- | --- | --- |
| REGISTER | 事前 | 开户/注册，含 KYC 核验 |
| BIND_CARD | 事前 | 绑定银行卡 |
| CARD_APPLY | 事前 | 信用卡申请 |
| LOAN_APPLY | 事前 | 贷款申请 |
| LIMIT_ADJUST | 事前 | 额度调整申请 |
| LOGIN | 事中 | 登录 |
| TRANSFER | 事中 | 转账 |
| PAYMENT | 事中 | 支付消费 |
| WITHDRAW | 事中 | 取现 |
| REPAY | 事中 | 还款 |
| CHANGE_PWD | 事中 | 修改密码 |
| CHANGE_PHONE | 事中 | 换绑手机号 |
| UPDATE_PROFILE | 事中 | 修改关键资料 |
| DISBURSE | 事后 | 贷款放款 |
| OVERDUE | 事后 | 逾期/失联 |
| DISPUTE | 事后 | 交易争议（否认交易） |
| FROZEN | 事后 | 司法/涉诈冻结 |
| SAR | 事后 | 可疑交易上报 |
| REVIEW | 事后 | 存量账户风险排查 |

统一事件字段：`event_id, event_type, user_id, card_id, device_id, ip, geo, amount, channel, event_at, rule_ids, risk_score, decision, action, status, created_at`。

## 6. 业务规则

规则统一通过 `rule_config` 配置化，支持场景隔离、窗口计数（1 小时/24 小时）、灰度发布与回滚。"常用城市/常用设备"取自已建立的画像表。

| 编号 | 场景 | 规则名 | 触发条件 | 风险等级 | 决策 | 处置 |
| --- | --- | --- | --- | --- | --- | --- |
| R001 | 转账 | 异地大额转账 | 登录城市 != 常用城市 且 转账 > 5 万 | 极高 | 拒绝 | 交易不执行 |
| R002 | 转账 | 凌晨密集操作 | 0-5 点 且 1 小时内 >= 3 笔交易 | 高 | 人工复核 | 挂起至人工结论 |
| R003 | 登录 | 盗号快速改绑 | 新设备 + 异地 且 登录后 30 分钟内改密/换绑手机 | 极高 | 拒绝 | 冻结登录 |
| R005 | 转账 | 新设备大额 | 设备首次出现 < 7 天 且 单笔 > 3 万 | 高 | 人工复核 | 挂起 |
| R008 | 转账 | 多卡归集 | 1 小时内 >= N 张卡转入同一收款卡 | 极高 | 拒绝 | 收款卡止付 |
| R010 | 转账 | 试探后大额 | 24 小时内同一对手小额(<=100 元) >= 2 笔 且 随即 > 1 万 | 高 | 人工复核 | 挂起 |
| R012 | 贷款 | 信贷申请突击 | 当月已申请 >= 3 家不同机构贷款 | 高 | 人工复核 | 挂起 |
| R015 | 贷款 | 放款即转 | 放款后 24 小时内转出 >= 90% 至非本人卡 | 极高 | 拒绝 | 账户冻结 |
| R018 | 登录 | 设备多人共用 | 同一 device_id 关联 >= 5 个不同 user_id | 中 | 标记 | 降低设备信任 |
| R020 | 贷款 | 多头查询 | 近 1 个月征信查询 >= 6 次 | 高 | 人工复核 | 挂起 |
| R022 | 信用卡 | 养卡套现 | 同一商户月内 >= 5 笔 且 累计 >= 额度 80% | 中 | 标记 | 限额 |
| R025 | 登录 | IP 代理/秒拨 | 登录 IP 命中代理库/Tor 出口 | 中 | 标记 | 增强验证 |
| R028 | 转账 | 涉诈收款 | 收款卡命中公安涉诈名单 | 极高 | 拒绝 | 上报 |
| R030 | 转账 | 黑卡拦截 | 收款卡号在黑名单 | 极高 | 拒绝 | 交易不执行 |
| R033 | 贷款/信用卡 | 团伙申请 | 同一设备或 IP 关联 >= 3 个不同申请人 | 高 | 人工复核 | 挂起 |
| R035 | 贷款 | 收入与征信不符 | 申请收入 > 征信收入 30% 且无税单佐证 | 高 | 人工复核 | 挂起 |

## 7. 数据库表结构设计

### 7.1 用户信息表 user_info

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| user_id | BIGINT PK | 是 | 用户 ID |
| name | VARCHAR(64) | 是 | 姓名 |
| id_card_hash | CHAR(64) | 是 | 身份证号哈希 |
| phone_hash | CHAR(64) | 是 | 手机号哈希 |
| credit_score | INT | 否 | 信用分 |
| kyc_level | TINYINT | 是 | L1-L4 |
| risk_tag | VARCHAR(128) | 否 | 风险标签（涉诈/失信/涉案） |
| status | TINYINT | 是 | 正常/冻结/止付/销户 |
| register_at | DATETIME | 是 | 注册时间 |
| updated_at | DATETIME | 是 | 更新时间 |

### 7.2 银行卡表 bank_card

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| card_id | BIGINT PK | 是 | 卡 ID |
| user_id | BIGINT | 是 | 持卡人，FK user_info |
| card_no_hash | CHAR(64) | 是 | 卡号哈希 |
| bank_code | VARCHAR(16) | 是 | 发卡行代码 |
| card_type | TINYINT | 是 | 储蓄卡/信用卡 |
| credit_limit | DECIMAL(18,2) | 否 | 信用卡额度 |
| single_limit | DECIMAL(18,2) | 是 | 单笔限额 |
| daily_limit | DECIMAL(18,2) | 是 | 单日限额 |
| status | TINYINT | 是 | 正常/冻结/止付/挂失/销户 |
| open_at | DATETIME | 是 | 开户时间 |
| updated_at | DATETIME | 是 | 更新时间 |

### 7.3 交易表 transaction

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| txn_id | BIGINT PK | 是 | 交易 ID |
| from_card_id | BIGINT | 是 | 出款卡，FK bank_card |
| to_card_id | BIGINT | 否 | 入款卡（本行卡时填写） |
| to_card_no_hash | CHAR(64) | 否 | 对手方卡号哈希（跨行） |
| to_account_name_hash | CHAR(64) | 否 | 对手方户名哈希 |
| to_bank_code | VARCHAR(16) | 否 | 对手方银行代码 |
| amount | DECIMAL(18,2) | 是 | 金额 |
| txn_type | TINYINT | 是 | 转账/支付/取现/还款/收款 |
| channel | VARCHAR(16) | 是 | APP/网银/ATM/POS/第三方 |
| device_id | BIGINT | 否 | 设备 ID |
| ip | VARCHAR(45) | 否 | IP |
| geo | VARCHAR(64) | 否 | 省市 |
| risk_score | DECIMAL(5,2) | 否 | 风控评分 |
| status | TINYINT | 是 | 成功/失败/挂起/拒绝 |
| created_at | DATETIME | 是 | 交易时间 |

索引：`(from_card_id, created_at)`、`(to_card_id, created_at)`、`(device_id, created_at)`；按 user_id 哈希分库，按 created_at 分区。

### 7.4 贷款申请表 loan_application

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| loan_id | BIGINT PK | 是 | 申请 ID |
| user_id | BIGINT | 是 | 申请人 |
| amount | DECIMAL(18,2) | 是 | 申请金额 |
| term_months | INT | 是 | 期限（月） |
| purpose | VARCHAR(32) | 是 | 用途（消费/经营/购车/装修） |
| monthly_income | DECIMAL(18,2) | 是 | 月收入 |
| debt_ratio | DECIMAL(5,2) | 是 | 负债率 |
| credit_query_1m | INT | 否 | 近 1 月征信查询次数 |
| credit_query_3m | INT | 否 | 近 3 月征信查询次数 |
| credit_query_6m | INT | 否 | 近 6 月征信查询次数 |
| channel | VARCHAR(16) | 是 | 申请渠道 |
| device_id / ip / geo | — | 否 | 申请环境 |
| status | TINYINT | 是 | 待审批/通过/拒绝/人工/放款/结清/逾期 |
| applied_at | DATETIME | 是 | 申请时间 |

### 7.5 登录日志表 login_log

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| login_id | BIGINT PK | 是 | 登录 ID |
| user_id | BIGINT | 是 | 用户 |
| device_id | BIGINT | 否 | 设备 |
| ip | VARCHAR(45) | 是 | IP |
| geo | VARCHAR(64) | 否 | 省市 |
| success | TINYINT | 是 | 是否成功 |
| fail_reason | VARCHAR(128) | 否 | 失败原因（密码错/被拒/风控） |
| login_at | DATETIME | 是 | 登录时间 |

索引：`(user_id, login_at)`、`(device_id, login_at)`、`(ip, login_at)`。

### 7.6 设备指纹表 device_fingerprint

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| device_id | BIGINT PK | 是 | 设备 ID |
| fingerprint_hash | CHAR(64) | 是 | 设备指纹哈希 |
| os | VARCHAR(32) | 否 | 操作系统 |
| browser | VARCHAR(32) | 否 | 浏览器 |
| is_emulator | TINYINT | 否 | 是否模拟器 |
| is_root | TINYINT | 否 | 是否越狱/root |
| status | TINYINT | 是 | 正常/高风险/黑名单 |
| first_seen | DATETIME | 是 | 首次出现 |
| last_seen | DATETIME | 是 | 最近出现 |

设备与用户为多对多关系（一设备多用户即团伙特征），通过关联表 `device_user_rel(device_id, user_id, rel_type, first_seen, last_seen)` 维护，不在本表冗余唯一用户。

### 7.7 IP 地理位置表 ip_geo_location

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| ip | VARCHAR(45) PK | 是 | IP |
| country / province / city | VARCHAR(64) | 否 | 地理信息 |
| isp | VARCHAR(32) | 否 | 运营商 |
| is_proxy | TINYINT | 是 | 是否代理 |
| is_tor | TINYINT | 是 | 是否 Tor |
| is_vpn | TINYINT | 是 | 是否 VPN |
| is_mobile | TINYINT | 是 | 是否移动网络 |
| updated_at | DATETIME | 是 | 更新时间 |

### 7.8 黑名单表 blacklist_extra

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| entry_id | BIGINT PK | 是 | 名单 ID |
| type | TINYINT | 是 | 设备/IP/银行卡号/身份证/手机号 |
| value | VARCHAR(128) | 是 | 命中值（哈希或原文） |
| reason | VARCHAR(256) | 否 | 入单原因 |
| source | VARCHAR(32) | 是 | 内部/公安涉诈/法院/同业/外部 |
| risk_level | TINYINT | 是 | 名单风险等级 |
| expire_at | DATETIME | 否 | 过期时间，空为永久 |
| status | TINYINT | 是 | 有效/失效 |

### 7.9 用户画像表 user_profile

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| user_id | BIGINT PK | 是 | 用户 |
| common_city | VARCHAR(64) | 否 | 常用城市 |
| common_device_id | BIGINT | 否 | 常用设备 |
| avg_txn_amount | DECIMAL(18,2) | 否 | 平均单笔金额 |
| txn_freq_day | DECIMAL(8,2) | 否 | 日均交易笔数 |
| active_hours | VARCHAR(32) | 否 | 常用活跃时段 |
| profile_at | DATETIME | 是 | 画像更新时间 |

### 7.10 风险事件表 risk_event

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| event_id | BIGINT PK | 是 | 事件 ID |
| event_type | VARCHAR(32) | 是 | 见第 5 节 |
| user_id / card_id / device_id | BIGINT | 否 | 关联对象 |
| ip | VARCHAR(45) | 否 | IP |
| amount | DECIMAL(18,2) | 否 | 金额 |
| rule_ids | VARCHAR(128) | 否 | 命中的规则列表 |
| risk_score | DECIMAL(5,2) | 否 | 模型分 |
| decision | VARCHAR(16) | 是 | 决策结果 |
| action | VARCHAR(64) | 否 | 处置动作 |
| status | TINYINT | 是 | 待处理/已处理/误报 |
| handler / handled_at / remark | — | 否 | 人工处理信息 |
| created_at | DATETIME | 是 | 事件时间 |

### 7.11 规则配置表 rule_config

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| rule_id | VARCHAR(16) PK | 是 | 规则编号 |
| rule_name | VARCHAR(64) | 是 | 规则名 |
| scene | VARCHAR(16) | 是 | 所属场景 |
| conditions | JSON | 是 | 条件表达式（含窗口/阈值） |
| risk_level | TINYINT | 是 | 风险等级 |
| decision | VARCHAR(16) | 是 | 决策 |
| action | VARCHAR(64) | 否 | 处置动作 |
| priority | INT | 是 | 优先级，小者先执行 |
| status | TINYINT | 是 | 启用/停用 |
| operator / updated_at | — | 是 | 配置维护信息 |

## 8. 决策与处置机制

**决策链路（实时）**：事件接入与标准化 → 名单快速命中（区分本人/对手方维度）→ 规则引擎（窗口聚合计算）→ 模型评分（申请反欺诈分/交易行为分/团伙分）→ 综合决策 → 处置执行 → 异步落库、画像更新、名单联动、审计留痕。

**决策优先级**：名单命中 > 极高风险规则 > 高风险规则 > 模型分档；低风险默认放行并记录。

**人工审核队列**：风险事件进入 MANUAL 队列后状态流转：待处理 → 已处理（通过/拒绝/冻结），所有操作留痕；处置结果回写 risk_event 与交易/账户状态。

**处置联动**：

- 拒绝后连续触发 N 次可自动降额/限额；
- 冻结/止付同步更新 bank_card、user_info 状态，交易发起时前置校验；
- 名单命中自动新增黑名单记录（含来源与原因），支持过期失效；
- 涉诈/可疑事件输出给合规系统做上报（SAR）。

## 9. 非功能与合规要求

- 实时决策：单事件 P99 <= 50ms，支持 1 万 TPS 峰值；
- 数据安全：卡号、身份证、手机号等敏感字段哈希存储，展示仅脱敏后 4 位；
- 规则可配置：新增/调整规则不发布版本即可生效，支持灰度与回滚；
- 名单对接：预留公安涉诈名单、法院被执行人、征信数据的接入接口；
- 审计留痕：所有风控决策、人工处理、名单变更可追溯；
- 合规联动：配合断卡行动、涉诈账户管控要求，支持账户限额、暂停非柜面业务等处置。
