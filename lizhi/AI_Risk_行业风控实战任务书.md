# 传统行业风控系统实战任务书

> **基线项目**: 尚硅谷 `AI_Risk` 风控系统 (电商版, 已完成)
> **任务时长**: 最后一天 (8 学时)
> **核心能力目标**: 业务拓展能力 (把风控抽象套到陌生行业) + Vibe Coding 能力 (用 AI 高效产出代码)
> **提交物**: 可运行的 Git 仓库 + 现场讲解 5-8 分钟

---

## 目录

- [二、基线项目: 复用边界](#二基线项目-复用边界)
- [三、8 个行业方向](#三8-个行业方向)
- [四、详细业务表 + 样例规则 (4 个深度场景包)](#四详细业务表--样例规则-4-个深度场景包)
  - [场景 A: 旅游风控](#场景-a旅游风控)
  - [场景 B: 银行风控](#场景-b银行风控)
  - [场景 C: 教育风控](#场景-c教育风控)
  - [场景 D: 制造业风控](#场景-d制造业风控)
- [五、4 个简化场景包](#五4-个简化场景包)
- [六、4 个递进任务 (vibe coding 节奏)](#六4-个递进任务-vibe-coding-节奏)

---

## 二、基线项目: 复用边界

这是任务里**最重要的一张表**, 学生必须先看明白这个边界:

| 模块 | 学生能不能动 | 说明 |
|---|---|---|
| 风控核心 9 张表 | **完全复用, 不许改** | `risk_rule / risk_event / risk_feature / risk_assessment / risk_case / risk_blacklist / risk_user_profile / risk_action_log / risk_alert` |
| 风控引擎 4 个核心 | **完全复用** | `app/engine/{decision, feature, rule, ml_model}.py` 不许改 schema, 只改特征计算函数 |
| 决策流水线 | **完全复用** | `process_event` 4 步 + `run_risk_check` 7 步不许改流程 |
| 行业业务表 | **必须自己设计** | `app/models_business.py` 跟业务强绑定, 每个行业自己出 schema |
| 行业特征计算 | **必须自己写** | `compute_user_features / compute_order_features / compute_address_features` 三大特征族按行业重写 |
| 业务校验 | **必须自己写** | `app/service/validator.py::ensure_source_matches_event_type` 派发表 |
| 业务黑名单类型 | **必须自己定** | 设备指纹 / IP / 证件号 等按行业定 |
| 业务事件类型 | **必须自己定** | event_type 枚举按行业定 |
| 业务数据生成脚本 | **必须自己写** | `gen_risky_users.py` / `gen_risk_data.py` 全部按行业自己造 |
| 业务规则 | **必须自己出** | 5 条起步, 数量自由 |
| 前端 / 文档 / Docker | **部分复用** | 框架能用, 业务字段要改 |

**核心契约**: `process_event` 接收 4 字段 `RiskCheckRequest(event_type, source_id, user_id, event_data)`, 返回 `RiskCheckResponse`——这层契约**不能改**.

---

## 三、8 个行业方向

| 编号 | 行业 | 典型业务场景 | 难度 | 推荐组队 |
|---|---|---|---|---|
| **A** | **旅游** | 机票 / 酒店 / 签证 / 跟团游 | 三颗星 | 小组 |
| **B** | **银行** | 信用卡 / 贷款 / 转账 / 登录 | 四颗星 | 小组 |
| **C** | **教育** | 课程报名 / 退费 / 学历认证 | 三颗星 | 个人 / 2 人组 |
| **D** | **制造业** | 经销商串货 / 设备保修 / 售后 | 三颗星 | 个人 |
| **E** | **物流** | 寄递实名 / 危险品 / 跨境 | 两颗星 | 个人 |
| **F** | **医疗** | 医保结算 / 处方审核 / 挂号 | 四颗星 | 小组 |
| **G** | **电信** | 宽带 / 套餐 / 话费欺诈 | 三颗星 | 2-3 人组 |
| **H** | **共享经济** | 押金退还 / 车辆报损 | 两颗星 | 个人 |

**推荐选择策略**:
- 小组做: 选 B 银行 / F 医疗——业务复杂
- 个人做: 选 E 物流 / H 共享经济
- 展示效果: A 旅游 / C 教育
- 避免选 D 制造业——业务背景要求高

---

## 四、详细业务表 + 样例规则 (4 个深度场景包)

下面给出 4 个深度场景包, 含**必须有的业务表 schema 草图** + **8 条样例业务规则**. 学生即使选其他行业, 也按这个模板做.

### 场景 A: 旅游风控

**业务边界**: 用户在 OTA 平台预订机票 / 酒店 / 签证 / 跟团游.

#### A.1 必须有的业务表 (7 张)

| 表名 | 核心字段 | 跟电商版的差异 |
|---|---|---|
| `UserInfo` | `user_id, name, real_name_status, vip_level, account_age_days` | 加"实名状态" (旅游必须) |
| `OrderInfo` | `order_id, user_id, order_type, total_amount, dest_country, depart_date, return_date, passenger_count` | 加"目的地国家 / 出行日期 / 乘客数" |
| `PassengerInfo` | `passenger_id, name, id_type, id_number, nationality, age` | 1 个订单 N 个乘客, 跟电商 `ReceiveInfo` 同级 |
| `VisaApplication` | `visa_id, user_id, dest_country, visa_type, reject_history, submit_time` | 全新表, 电商没有"签证"概念 |
| `BookingHotel` | `booking_id, order_id, hotel_id, check_in, check_out, room_count, is_refundable` | 全新表 |
| `BookingFlight` | `booking_id, order_id, flight_no, depart_airport, arrive_airport, cabin_class` | 全新表 |
| `BlacklistExtra` | `entry_id, type, value, reason, expire_at` | `type` 加 `护照号 / 签证号 / 设备指纹` |

#### A.2 必有的业务规则 (举例 8 条)

| 编号 | 规则名 | 触发条件 | 风险等级 | 决策 |
|---|---|---|---|---|
| R001 | 拒签历史拦截 | 用户 90 天内签证被拒 >= 2 次 | 极高 | 拒绝 |
| R002 | 短期多国签证 | 30 天内申请 >= 3 个不同国家签证 | 高 | 人工审核 |
| R005 | 大额跨境游 | 单笔订单 > 50000 元 | 高 | 人工审核 |
| R008 | 黄牛囤票 | 同一支付账号 1 小时内预订 >= 5 张同航班 | 极高 | 拒绝 |
| R012 | 0 点突击下单 | 凌晨 1-5 点下单 + 行程 < 7 天 | 中 | 标记 |
| R018 | 乘客信息不一致 | 订单乘客 ID 号与历史乘客匹配 < 30% | 中 | 标记 |
| R025 | 新用户大单 | 注册 < 7 天 + 订单 > 10000 元 | 中 | 标记 |
| R030 | 黑护照拦截 | 乘客证件号在黑名单 | 极高 | 拒绝 |

---

### 场景 B: 银行风控

**业务边界**: 信用卡 / 贷款 / 转账 / 登录 4 大场景.

#### B.1 必须有的业务表 (8 张)

| 表名 | 核心字段 | 跟电商版的差异 |
|---|---|---|
| `UserInfo` | `user_id, name, id_card_hash, credit_score, register_at, kyc_level` | 加 KYC 等级 / 信用分 |
| `BankCard` | `card_id, user_id, card_no_hash, bank_code, card_type, credit_limit` | 每用户 N 张卡 |
| `Transaction` | `txn_id, from_card, to_card, amount, channel, device_id, ip, geo` | 转账 / 支付都用这张 |
| `LoanApplication` | `loan_id, user_id, amount, term_months, purpose, monthly_income, debt_ratio` | 全新表 |
| `LoginLog` | `login_id, user_id, device_id, ip, geo, success, login_at` | 全新表 (电商没专门做) |
| `DeviceFingerprint` | `device_id, user_id, fingerprint_hash, first_seen, last_seen, os, browser` | 银行业专属 |
| `IpGeoLocation` | `ip, country, province, city, isp, is_proxy, is_tor` | 全新表 |
| `BlacklistExtra` | `entry_id, type, value, reason, expire_at` | `type` 加 `设备指纹 / IP / 银行卡号 / 身份证号` |

#### B.2 必有的业务规则 (举例 8 条)

| 编号 | 规则名 | 触发条件 | 风险等级 | 决策 |
|---|---|---|---|---|
| R001 | 异地大额转账 | 登录城市 != 常用城市 + 转账 > 5 万 | 极高 | 拒绝 |
| R002 | 凌晨密集操作 | 0-5 点 + 1 小时内 >= 3 笔交易 | 高 | 人工审核 |
| R005 | 新设备大额 | 注册设备 < 7 天 + 单笔 > 3 万 | 高 | 人工审核 |
| R008 | 多卡归集 | 1 小时内 N 张卡转入同一卡 | 极高 | 拒绝 |
| R012 | 信贷申请突击 | 当月已申请 >= 3 家不同机构贷款 | 高 | 人工审核 |
| R018 | 设备多人共用 | 同一 device_id 关联 >= 5 个不同 user_id | 中 | 标记 |
| R025 | IP 代理 / 秒拨 | 登录 IP 命中代理库 / Tor 出口 | 中 | 标记 |
| R030 | 黑卡拦截 | 收款卡号在黑名单 | 极高 | 拒绝 |

---

### 场景 C: 教育风控

**业务边界**: 在线教育平台报名 / 退费 / 学历认证 / 直播打赏.

#### C.1 必须有的业务表 (6 张)

| 表名 | 核心字段 | 跟电商版的差异 |
|---|---|---|
| `UserInfo` | `user_id, name, role, student_id, real_name_status, register_at` | 加 `role: 学生 / 家长 / 老师`, 加学号 |
| `Course` | `course_id, name, category, price, teacher_id, total_hours` | 电商的"商品" |
| `OrderInfo` | `order_id, user_id, course_id, total_amount, study_goal, expected_finish_days` | 字段完全不同 |
| `LearningProgress` | `progress_id, user_id, course_id, total_minutes, last_active_at, completion_rate` | 全新表 (电商没"学习进度") |
| `RefundRequest` | `refund_id, order_id, reason, study_minutes_before_refund, refund_amount` | 全新表 (电商售后按退货, 教育按退费) |
| `BlacklistExtra` | `entry_id, type, value, reason, expire_at` | `type` 加 `学号 / 身份证 / 设备指纹 / 直播账号` |

#### C.2 必有的业务规则 (举例 8 条)

| 编号 | 规则名 | 触发条件 | 风险等级 | 决策 |
|---|---|---|---|---|
| R001 | 刷单式报名 | 同一课程 7 天内 >= 3 个新账号报名 | 极高 | 拒绝 |
| R002 | 0 学时退费 | 课程学习时长 < 5 分钟 + 申请退款 | 高 | 人工审核 |
| R005 | 大额连报 | 1 小时内订单金额 > 30000 元 | 高 | 人工审核 |
| R008 | 假学员代理 | 同一设备指纹关联 >= 5 个学员账号 | 极高 | 拒绝 |
| R012 | 退费连环 | 90 天内退款 >= 3 次 + 累计金额 > 10000 | 中 | 标记 |
| R018 | 直播打赏异常 | 单场直播打赏 > 5000 + 打赏账号 < 30 天 | 中 | 标记 |
| R025 | 学员身份不符 | role=老师但购买学生课程 | 中 | 标记 |
| R030 | 黑学号拦截 | 学号 / 身份证在黑名单 | 极高 | 拒绝 |

---

### 场景 D: 制造业风控

**业务边界**: 经销商订货 / 设备保修 / 采购订单 / 售后维修.

#### D.1 必须有的业务表 (7 张)

| 表名 | 核心字段 | 跟电商版的差异 |
|---|---|---|
| `UserInfo` | `user_id, name, role, dealer_level, region, register_at` | `role: 经销商 / 终端用户 / 内部员工` |
| `Product` | `product_id, name, model, category, msrp, warranty_months` | 制造业"商品" + 保修期 |
| `DealerInfo` | `dealer_id, dealer_name, region, authorized_brands, contract_start, contract_end` | 全新表, 经销商档案 |
| `OrderInfo` | `order_id, dealer_id, product_id, quantity, unit_price, total_amount, ship_to_region` | 加"经销商 / 收货区域" |
| `WarrantyRecord` | `warranty_id, product_sn, order_id, issue_date, issue_type, repair_cost, technician_id` | 全新表 (电商没"保修") |
| `CrossRegionReport` | `report_id, order_id, dealer_id, ship_to_region, dealer_region, reporter_id` | 全新表 (串货举报) |
| `BlacklistExtra` | `entry_id, type, value, reason, expire_at` | `type` 加 `设备 SN / 经销商 ID / 维修工` |

#### D.2 必有的业务规则 (举例 8 条)

| 编号 | 规则名 | 触发条件 | 风险等级 | 决策 |
|---|---|---|---|---|
| R001 | 跨区串货举报 | 同一订单被举报跨区销售 >= 2 次 | 极高 | 拒绝 |
| R002 | 保修期外高频保修 | 设备已过保修 + 1 个月内申请 >= 2 次 | 高 | 人工审核 |
| R005 | 大额经销商囤货 | 单笔订单 > 100 万 | 高 | 人工审核 |
| R008 | 套保嫌疑 | 同一设备 SN 90 天内 >= 2 次维修 | 极高 | 拒绝 |
| R012 | 新经销商大单 | 签约 < 30 天 + 首单 > 50 万 | 中 | 标记 |
| R018 | 维修费用异常 | 单次维修费用 > 设备 MSRP 60% | 中 | 标记 |
| R025 | 经销商资质过期 | 合同到期 + 仍有订单 | 中 | 标记 |
| R030 | 黑经销商拦截 | dealer_id 在黑名单 | 极高 | 拒绝 |

---

## 五、4 个简化场景包

下面 4 个行业只给**业务边界 + 关键场景**, 让学生自己设计表 / 字段 / 规则:

### 场景 E: 物流风控

**业务边界**: 寄递实名 / 危险品 / 跨境 / 代收货款.

**关键场景提示**:
- 寄件人 / 收件人 实名信息异常
- 危险品 (电池 / 化学品) 瞒报
- 跨境包裹重量 / 申报价值异常
- 代收货款 (货到付款) 拒收率
- 收件地址 (偏远地区 / 临时地址 / 多人共用地址)
- 寄件频率 (高频寄件 / 凌晨寄件)

**必须有的业务表** (学生自定, 提示):
- `UserInfo` (寄件人 / 收件人)
- `Shipment` (运单主表)
- `ShipmentItem` (运单物品明细)
- `Address` (收件地址)
- `BlacklistExtra`

### 场景 F: 医疗风控

**业务边界**: 医保结算 / 处方审核 / 挂号黄牛 / 药品代购.

**关键场景提示**:
- 医保卡多医院高频使用
- 处方超量 / 重复开方
- 挂号黄牛 (同一身份证 / 手机号频繁挂号 / 退号)
- 药品代购 (单次开药量异常)
- 医生大处方 (单医生 / 单日处方金额异常)
- 跨省异地就医频率

**必须有的业务表** (学生自定, 提示):
- `UserInfo` (患者)
- `Doctor` (医生档案)
- `Prescription` (处方)
- `InsuranceClaim` (医保结算)
- `BlacklistExtra`

### 场景 G: 电信风控

**业务边界**: 宽带 / 套餐 / 集团客户 / 话费欺诈.

**关键场景提示**:
- 同一身份证多 SIM 卡
- 漫游 / 跨境通话异常
- 话费套现 (高频充值 + 即时转出)
- 集团客户子号码异常
- 设备 IMSI / MAC 多次换卡
- 凌晨密集呼叫

**必须有的业务表** (学生自定, 提示):
- `UserInfo` (用户)
- `SimCard` (SIM 卡 + IMSI)
- `CallLog` (通话记录)
- `BillingRecord` (话费账单)
- `DeviceFingerprint` (设备)
- `BlacklistExtra`

### 场景 H: 共享经济风控

**业务边界**: 押金退还 / 车辆报损 / 充电桩占用 / 信用免押.

**关键场景提示**:
- 押金退还账户与充值账户不一致
- 车辆报损时间在免赔期内高频
- 充电桩占位超时
- 信用免押刷脸 / 实名不一致
- 设备 ID 多次解绑
- 短期高频使用同一设备 (疑似转租)

**必须有的业务表** (学生自定, 提示):
- `UserInfo` (用户)
- `Device` (车辆 / 充电桩)
- `DepositRecord` (押金)
- `UsageLog` (使用记录)
- `DamageReport` (报损记录)
- `BlacklistExtra`

---

## 六、4 个递进任务 (vibe coding 节奏)

**关键**: 每个任务都是 vibe coding——学生用 LLM (Claude / GPT / Cursor / Trae) 协作产出, **不是手写**所有代码.

### 任务 1: 业务理解 (2h)

**目标**: 用 vibe coding 输出"业务说明文档", 证明你吃透了这个行业.

**输入**: 你选定的行业 (A-H 之一)77777777

**交付物**:
- `1-业务说明.md`: 1-2 页纸, 含
  - 该行业典型欺诈场景 >= 3 种
  - 关键业务字段 >= 10 个
  - 业务事件类型 >= 3 种
  - 行业术语表 >= 5 个

**vibe 提示词模板**:

> 我要做一个 {行业} 行业的风控系统, 业务层跟电商完全不同. 请帮我调研这个行业的典型欺诈场景、关键业务字段、事件类型, 输出 1 页纸业务说明. 注意要符合国内监管要求.

**验收**: 老师快速扫一眼, 看你是不是真调研了. 重点检查"业务事件类型"是不是这个行业的真实痛点.

### 任务 2: 数据层 (2h)

**目标**: 业务表 + 数据生成 + 数据校验, 跑通 `init_db` 完整流程.

**输入**: 任务 1 产出的业务说明

**交付物**:
- `app/models_business.py`: 你设计的 N 张业务表的 SQLAlchemy 模型
- `sql/init_business_tables.sql`: 同上的 DDL
- `sql/init_business_data.sql`: 至少 100 条业务数据
- `scripts/gen_business_data.py`: 可重复运行的造数脚本
- `app/service/validator.py`: 业务校验派发表
- 改 `app/config.py`: 黑名单 type 集合 + 业务事件类型枚举

**vibe 提示词模板**:
> 这是我的业务说明: <粘贴任务 1 产出>. 请帮我设计 N 张业务表 schema, 写 SQLAlchemy 模型 + DDL, 设计字段 / 关联 / 索引时要考虑后续风控特征计算的便利. 同时写一个 Python 造数脚本, 至少造 100 条业务数据.

**验收**:
- `init_db` 跑通, 数据库里有 N 张表
- `gen_business_data.py` 跑通, 至少 100 条业务事件入库
- 业务表跟电商版有显著差异
- 业务事件类型 >= 3 种

### 任务 3: pipeline + 训练 (2.5h)

**目标**: 跑通 `run_risk_check` 完整链路, 训练 1 个 XGBoost 模型.

**输入**: 任务 2 的业务表 + 数据

**交付物**:
- `app/engine/feature.py::compute_*_features`: 三大特征族按你行业重写
- `app/service/event.py::process_event` 业务分支适配
- `app/engine/rule.py`: 5+ 条行业规则
- `scripts/train_xgb_model.py` 跑通, 出 val_auc + val_f1
- 5-8 张截图: 跑通风险检查 + 案件管理 + 评估历史

**vibe 提示词模板**:
> 这是我的业务表 + 数据: <粘贴 schema + 样例数据>. 请帮我设计 3 大特征族 (用户 / 订单 / 地址), 字段映射到我的行业, 写 compute_*_features 函数. 同时帮我调研这个行业的典型欺诈套路, 设计 8 条业务规则, 跑通 XGBoost 训练. 训练后用 val_auc 和 val_f1 评估.

**验收**:
- `run_risk_check` 跑通, 至少 1 个高风险用户能被识别
- val_auc >= 0.7
- 业务规则 >= 5 条, 至少 3 条能命中样例数据
- 截图能演示完整流程

### 任务 4: 演示 + 文档 (1.5h)

**目标**: 5-8 分钟讲解视频 + 完整 README.

**交付物**:
- 录屏: 5-8 分钟, 含
  - 业务说明 1 分钟
  - 跑通演示 2 分钟
  - XGBoost 评估 1 分钟
  - 业务规则讲解 2 分钟
  - Vibe Coding 复盘 1 分钟
- `README.md`: 完整说明
- `agent_design.md`: 你怎么用 LLM 协作

**验收**: 视频 + README + 老师现场提问.
