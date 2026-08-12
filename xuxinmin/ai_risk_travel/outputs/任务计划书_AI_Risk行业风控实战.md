# AI_Risk 行业风控实战 · 任务计划书

> 依据：《AI_Risk_行业风控实战任务书.md》
> 任务窗口：最后一天（8 学时）
> 推荐行业：**A · 旅游风控**（本计划按旅游为例展开，行业可整体替换）
> 提交物：可运行 Git 仓库 + 现场讲解 5–8 分钟

---

## 0. 一句话总结

用 8 小时把已完成电商版 AI_Risk 风控系统“换皮换芯”到一个新行业：**完全复用** 9 张风控核心表 + 4 个引擎核心 + 7 步决策流水线；**全部自研** 行业业务表、特征计算、业务校验、黑名单类型、事件类型、造数脚本和业务规则。最后交付一个能跑、能讲、有 AI 模型的 Git 仓库。

---

## 1. 项目背景与目标

| 项目 | 内容 |
|---|---|
| 基线 | 尚硅谷 AI_Risk 风控系统（电商版，已完成） |
| 核心能力目标 | ① 业务拓展能力：把风控抽象套到陌生行业；② Vibe Coding 能力：用 LLM 高效产出代码 |
| 提交物 | 可运行的 Git 仓库 + 现场讲解 5–8 分钟 |
| 总时长 | 8 学时（2h + 2h + 2.5h + 1.5h 四个递进任务） |
| 技术栈（基线） | FastAPI + SQLAlchemy 2.x + MySQL 8.0 + XGBoost + LangChain DeepAgents + Pydantic + Jinja2 |

---

## 2. 行业选择：推荐 A · 旅游

### 2.1 8 个候选行业速览

| 编号 | 行业 | 难度 | 推荐组队 | 展示效果 | 是否有深度包 |
|---|---|---|---|---|---|
| A | 旅游 | ★★★ | 小组 | 好 | ✅ 7 表 + 8 规则 |
| B | 银行 | ★★★★ | 小组 | 好 | ✅ 8 表 + 8 规则 |
| C | 教育 | ★★★ | 个人 / 2 人 | 好 | ✅ 6 表 + 8 规则 |
| D | 制造业 | ★★★ | 个人 | 一般 | ✅ 7 表 + 8 规则（业务背景要求高） |
| E | 物流 | ★★ | 个人 | 一般 | ❌ 仅提示 |
| F | 医疗 | ★★★★ | 小组 | 好 | ❌ 仅提示 |
| G | 电信 | ★★★ | 2–3 人 | 一般 | ❌ 仅提示 |
| H | 共享经济 | ★★ | 个人 | 一般 | ❌ 仅提示 |

### 2.2 为什么推荐 A 旅游

1. **设计风险最低**：任务书已给出旅游 7 张表的核心字段草图和 8 条样例规则，几乎“照着填”就能跑，不会卡在 schema 设计。
2. **展示效果好**：任务书点名“展示效果：A 旅游 / C 教育”，现场讲“黄牛囤票 / 拒签刷签 / 0 点突击下单”非常好讲。
3. **数据直观**：订单、乘客、签证、航班、酒店都是大众熟悉的概念，造数和演示都容易自圆其说。
4. **难度适中**：3 星，个人或小组都能做，且事件类型天然清晰（预订 / 支付 / 签证申请 / 退改签）。

### 2.3 替换策略（如果你选其他行业）

- 想更省事：选 **E 物流 / H 共享经济**（2 星），但任务书没给深度包，表和规则要自己设计。
- 想冲高难度：选 **B 银行 / F 医疗**（4 星），建议小组，亮点是“KYC / 医保”话题有监管背书。
- 本计划后续所有步骤以 A 旅游为例；换行业时只替换第 6、7、8 章的“业务设计内容”，步骤骨架、时间表、验收方式完全不变。

---

## 3. 复用边界（红线表，开工前必须背熟）

| 模块 | 动作 | 具体文件 |
|---|---|---|
| 风控核心 9 张表 | **完全复用，不许改** | `risk_rule / risk_event / risk_feature / risk_assessment / risk_case / risk_blacklist / risk_user_profile / risk_action_log / risk_alert` |
| 风控引擎 4 核心 | **完全复用**（只改特征计算函数） | `app/engine/decision.py`、`app/engine/rule.py`、`app/engine/ml_model.py`；`feature.py` 内部函数重写 |
| 决策流水线 | **完全复用** | `process_event` 4 步 + `run_risk_check` 7 步，流程不动 |
| 行业业务表 | **必须自己设计** | `app/models_business.py`（新行业 schema） |
| 行业特征计算 | **必须自己写** | `compute_user_features / compute_order_features / compute_address_features` 三大特征族按行业重写 |
| 业务校验 | **必须自己写** | `app/service/validator.py::ensure_source_matches_event_type` 派发表 |
| 业务黑名单类型 | **必须自己定** | 设备指纹 / 护照号 / 签证号 / 身份证号 / IP 等 |
| 业务事件类型 | **必须自己定** | event_type 枚举按行业定（同步改 `app/schemas.py` 的 Literal） |
| 业务数据生成脚本 | **必须自己写** | `scripts/gen_business_data.py`、`scripts/gen_risky_users.py` 按行业重造 |
| 业务规则 | **必须自己出** | 5 条起步，数量自由 |
| 前端 / 文档 / Docker | **部分复用** | 框架能用，业务字段、文案要改 |

### 核心契约（不能改）

```text
RiskCheckRequest(event_type, source_id, user_id, event_data)  →  RiskCheckResponse
```

- 请求结构：4 个字段形状不变，**event_type 的取值可以换成行业事件**（如“预订 / 支付 / 签证申请 / 退改签”）。
- 响应结构：`final_score / risk_level / decision / triggered_rules / features` 等字段不变，前端才能复用。
- `process_event` 与 `run_risk_check` 的调用链、7 步流水线、事务边界不动。

---

## 4. 总体执行节奏（8 学时）

```mermaid
flowchart LR
    A[第0步 环境准备 0.5h] --> B[任务1 业务理解 1.5h]
    B --> C[任务2 数据层 2h]
    C --> D[任务3 pipeline+训练 2.5h]
    D --> E[任务4 演示+文档 1.5h]
    E --> F[提交Git仓库+演练]
```

时间总账：0.5 + 1.5 + 2 + 2.5 + 1.5 = 8 学时。环境准备压在任务 1 前面，旅游行业有现成深度包，业务理解实际 1.5h 足够。

---

## 5. 第 0 步：环境准备与基线验证（0.5h）

**目标**：把电商版基线跑起来，确保“底子是好的”，避免把环境问题混进业务改造。

| 步骤 | 命令 / 操作 |
|---|---|
| 1. 拉取基线仓库 | `git clone https://github.com/wyxaxx02419/ai_risk`（或解压本地 `ai_risk_old`） |
| 2. 建虚拟环境 | `conda create -n risk python=3.10 -y && conda activate risk` |
| 3. 装依赖 | `pip install -r requirements.txt` |
| 4. 配置数据库 | 本地起 MySQL 8.0，编辑 `.env`：`DB_USER=root`、`DB_PASSWORD=...`、`DB_NAME=travel_risk`（新行业建议新库名，不污染基线） |
| 5. 初始化数据库 | `python scripts/init_db.py --drop` |
| 6. 跑通基线测试 | `pytest tests/` 全绿 |
| 7. 启动服务 | `python _run.py`，浏览器打开 `/docs` 和风控检查页面 |
| 8. 基线留底 | `git init`（如需要）→ 提交一次“基线快照”，业务改造全部在新分支做 |

**验收**：能跑通一次电商版风控检查（如“下单”事件返回 200），pytest 全绿，服务日志无异常。

**建议**：整个开发过程每完成一个可运行节点就 `git commit` 一次（见第 11 章提交规范），最后直接就是一个合格的 Git 仓库。

---

## 6. 任务 1：业务理解（1.5h）

### 6.1 目标与交付物

- 交付物：`1-业务说明.md`（1–2 页纸）
- 证明你已经吃透旅游行业，这是老师验收的第一关。

### 6.2 `1-业务说明.md` 必含 4 块

| 模块 | 要求 | 旅游示例（可直接用） |
|---|---|---|
| 典型欺诈场景 | ≥ 3 种 | ① 黄牛囤票/倒票（同支付账号短时间订同航班多张）；② 拒签刷签/虚假材料（90 天内多次被拒后换国家申请）；③ 黑产代订（盗用他人身份证/护照预订，乘客信息与历史不匹配）；④ 0 点突击下单低价票倒卖；⑤ 签证中介洗客（短期多国签证申请） |
| 关键业务字段 | ≥ 10 个 | `real_name_status`、`vip_level`、`account_age_days`、`dest_country`、`depart_date`、`return_date`、`passenger_count`、`passenger_id_number`、`visa_reject_history`、`is_refundable`、`cabin_class`、`check_in/check_out` |
| 业务事件类型 | ≥ 3 种 | 预订（机票/酒店/跟团游）、支付、签证申请、退改签 |
| 行业术语表 | ≥ 5 个 | OTA（在线旅游平台）、PASS/拒签、黄牛囤票、退改签、尾单/特价舱、实名制核验、目的地国家 |

### 6.3 Vibe Coding 提示词模板（可直接粘贴给 LLM）

```text
我要做一个【旅游行业】的风控系统，业务层跟电商完全不同。请帮我调研这个行业的典型欺诈场景（至少 3 种）、关键业务字段（至少 10 个）、业务事件类型（至少 3 种），输出 1 页纸业务说明。注意要符合国内监管要求（实名制、护照/签证校验、航旅数据合规）。输出结构：欺诈场景表 / 关键字段表 / 事件类型表 / 术语表。
```

### 6.4 自检清单

- [ ] 欺诈场景不是泛泛而谈，而是“在哪个业务环节、用什么手法、骗什么钱”
- [ ] 事件类型能映射到基线 `RiskCheckRequest.event_type`（后续直接当枚举用）
- [ ] 字段清单覆盖后续规则要用的所有字段（拒签次数、下单时间、目的地国家等）

**完成标志**：`1-业务说明.md` 写完，老师看一眼能确认“你真调研了”。

---

## 7. 任务 2：数据层（2h）

### 7.1 交付物清单

| 交付物 | 路径 | 说明 |
|---|---|---|
| 业务表 ORM | `app/models_business.py` | 7 张旅游业务表 SQLAlchemy 模型 |
| 业务表 DDL | `sql/init_business_tables.sql` | 与 ORM 一致的 DDL |
| 业务数据 | `sql/init_business_data.sql` | ≥ 100 条业务数据（脚本导出的快照） |
| 造数脚本 | `scripts/gen_business_data.py` | 可重复运行，直连 MySQL 造数 |
| 业务校验 | `app/service/validator.py` | 重写派发表，事件类型 ↔ 业务表映射 |
| 配置 | `app/config.py` | 黑名单 type 集合 + 业务事件类型枚举 |

### 7.2 旅游业务表设计（7 张，含索引建议）

| 表名 | 核心字段 | 索引建议 | 与电商版差异 |
|---|---|---|---|
| `user_info` | `user_id, name, real_name_status, vip_level, account_age_days, phone_hash, register_at` | PK `user_id` | 加“实名状态”“VIP 等级” |
| `order_info` | `order_id, user_id, order_type, total_amount, dest_country, depart_date, return_date, passenger_count, status, create_time` | `(user_id, create_time)`、`(dest_country)` | 加“目的地国家 / 出行日期 / 乘客数” |
| `passenger_info` | `passenger_id, order_id, name, id_type, id_number, nationality, age` | `(order_id)`、`(id_number)` | 1 订单 N 乘客，等价电商 `ReceiveInfo` 位置 |
| `visa_application` | `visa_id, user_id, dest_country, visa_type, reject_history, submit_time, status` | `(user_id, submit_time)`、`(dest_country)` | 全新表，电商没有“签证” |
| `booking_hotel` | `booking_id, order_id, hotel_id, check_in, check_out, room_count, is_refundable` | `(order_id)` | 全新表 |
| `booking_flight` | `booking_id, order_id, flight_no, depart_airport, arrive_airport, depart_time, cabin_class` | `(order_id)`、`(flight_no, depart_time)` | 全新表 |
| `blacklist_extra` | `entry_id, type, value, reason, expire_at` | `(type, value)` | type 含 护照号 / 签证号 / 身份证号 / 设备指纹 |

> 注意：表名用小写下划线（基线风格 `user_info`），编码 `utf8mb4`，金额用 `DECIMAL(10,2)`，时间用 `DATETIME`。

### 7.3 事件类型与黑名单类型定义

**业务事件类型（≥3 种，改 `app/schemas.py` 的 Literal 与 `app/config.py`）**：

```text
预订 / 支付 / 签证申请 / 退改签
```

**黑名单类型（改 `app/config.py`）**：

```text
用户 / 护照号 / 身份证号 / 手机号 / 设备指纹 / IP / 签证号
```

### 7.4 造数脚本设计要点

- 用户约 40 个：其中 6–8 个“风险画像”用户（新注册、拒签多次、多设备、黑名单证件），保证第 8 章规则能命中。
- 订单约 120 条、乘客约 200 人、签证申请约 60 条、航班/酒店预订若干，总量 ≥ 100 条业务数据。
- 时间字段用相对“今天”的偏移（`now() - timedelta(days=n)`），保证“近 90 天拒签”“近 7 天注册”等规则永远可命中。
- 脚本可重复运行：先清理旧数据再插入（或幂等 upsert），不依赖手改 SQL。
- 跑完后把数据导出成 `sql/init_business_data.sql` 快照，保证 `init_db.py` 一条命令也能还原。

### 7.5 执行步骤

1. 用 vibe 提示词生成 7 张表 schema + ORM + DDL（粘贴 7.2 表 + 业务说明给 LLM）。
2. 改 `app/models_business.py`，并确保 ORM 被 `init_db` / `Base.metadata` 收集到（在 `app/models.py` 里 import 新模型）。
3. 改 `app/schemas.py` 的 event_type Literal → 行业事件。
4. 改 `app/config.py` 黑名单类型集合。
5. 改 `app/service/validator.py`：事件类型 ↔ 表名派发表（见 8.3）。
6. 写 `scripts/gen_business_data.py` 造数 → 跑通。
7. `python scripts/init_db.py --drop` 全流程验证，导出 `init_business_data.sql`。

### 7.6 常见坑

- SQLAlchemy 模型忘在 `app/models.py` import，导致 `init_db` 建不出新表。
- 表名大小写不一致（Windows/MySQL 不敏感但 Linux 敏感）。
- 造数时间全用固定日期，过几天规则就不命中了。
- 黑名单类型枚举改了一处，另一处（`schemas.py` Literal 或 `config.py`）忘改，API 报 422。

**验收**：`init_db` 跑通且库里能看到 7 张新表；`gen_business_data.py` 跑通且 ≥ 100 条数据；业务表与电商版差异显著；事件类型 ≥ 3 种。

---

## 8. 任务 3：pipeline + 训练（2.5h）

### 8.1 交付物清单

| 交付物 | 路径 |
|---|---|
| 三大特征族重写 | `app/engine/feature.py` |
| 业务分支适配 | `app/service/event.py::_enrich_request` |
| 行业规则（≥ 8 条） | `sql/init_risk_data.sql`（或规则管理 API 插入）+ `app/engine/rule.py` 保持不动 |
| 特征列清单同步 | `app/engine/ml_model.py::FEATURE_COLUMNS` |
| 模型训练 | `scripts/train_xgb_model.py` 跑通，输出 val_auc + val_f1 |
| 演示截图 | 5–8 张：风控检查、案件管理、评估历史、规则命中、仪表盘、模型评估 |

### 8.2 三大特征族设计（电商 → 旅游映射）

保留函数签名 `compute_user_features / compute_order_features / compute_address_features`，内部逻辑按行业重写（“地址族”在旅游里变成“乘客/目的地族”）。

| 电商特征（参考） | 旅游特征（替换后） | 含义 |
|---|---|---|
| `user_total_orders` | `user_total_orders` | 历史订单数 |
| `user_orders_30d` | `user_orders_30d` | 近 30 天订单数 |
| `user_refund_count` | `user_visa_reject_count_90d` | 近 90 天拒签次数 |
| `user_address_count` | `user_visa_countries_30d` | 近 30 天申请签证国家数 |
| `user_account_age` | `user_account_age_days` | 账号注册天数 |
| `user_avg_order_amount` | `user_avg_order_amount` | 平均订单金额 |
| `order_total_amount` | `order_total_amount` | 订单金额 |
| `order_item_count` | `order_passenger_count` | 乘客数 |
| `order_is_night` | `order_is_night` | 是否凌晨下单（1–5 点） |
| `order_trip_days` | `order_trip_days` | 出行天数（return - depart） |
| `addr_province_count` | `dest_country_count` | 目的地国家种类 |
| `addr_is_new` | `dest_country_is_new` | 是否新目的地 |
| — | `passenger_id_consistency` | 乘客证件号与历史乘客匹配率（R018 用） |
| — | `passenger_blacklist_hits` | 乘客证件是否命中黑名单（R030 用） |

> 建议总维度 15–25 个；**每新增/改名一个特征，必须同步改 `ml_model.py::FEATURE_COLUMNS` 并重训**，否则推理时特征对齐会报错或错位。

### 8.3 validator 与 event 适配（关键改动点）

**`app/service/validator.py`**：把 `ensure_source_matches_event_type` 的 if/elif 链换成字典派发表，新增行业映射：

```python
_EVENT_SOURCE_VALIDATORS = {
    ("预订", "支付"):   ("order_info", "order_id", "订单"),
    ("签证申请",):      ("visa_application", "visa_id", "签证申请"),
    ("退改签",):        ("order_info", "order_id", "订单"),
}
```

**`app/service/event.py::_enrich_request`**：按事件类型补全关联字段，如“预订/支付”把 `source_id` 当 `order_id`；“签证申请”不需要订单，直接从签证表取用户维度数据。

### 8.4 旅游业务规则（8 条，写入 `risk_rule`）

| 编号 | 规则名 | 条件（基于特征） | 风险等级 | 决策 |
|---|---|---|---|---|
| R001 | 拒签历史拦截 | `user_visa_reject_count_90d >= 2` | 极高 | 拒绝 |
| R002 | 短期多国签证 | `user_visa_countries_30d >= 3` | 高 | 人工审核 |
| R005 | 大额跨境游 | `order_total_amount > 50000` | 高 | 人工审核 |
| R008 | 黄牛囤票 | 1 小时内同航班订 ≥ 5 张（订单维度特征/事件数据） | 极高 | 拒绝 |
| R012 | 0 点突击下单 | `order_is_night == 1 and order_trip_days < 7` | 中 | 标记 |
| R018 | 乘客信息不一致 | `passenger_id_consistency < 0.3` | 中 | 标记 |
| R025 | 新用户大单 | `user_account_age_days < 7 and order_total_amount > 10000` | 中 | 标记 |
| R030 | 黑护照拦截 | `passenger_blacklist_hits > 0` | 极高 | 拒绝 |

> 规则条件就是 `rule.py` 的 JSON 表达式格式，字段名必须与特征名完全一致。R008 这类“同一支付账号短时同航班多单”如果特征里不好算，可以先做成订单族特征（1 小时内同航班订单数），或写进 event_data 统计。

### 8.5 XGBoost 训练（防假收敛是重点）

```bash
python scripts/gen_risk_data.py 200 --target-pos-ratio 0.30   # 正例比例拉到 25–35%
python scripts/train_xgb_model.py
```

必须检查的输出：

| 指标 | 达标线 |
|---|---|
| val_auc | ≥ 0.70 |
| val_f1 | ≥ 0.50（越高越好） |
| best_iteration | > 30（太小 = 假收敛） |
| acc | > baseline_acc + 2% |
| `is_fake_convergence` | 必须为 False |

如果假收敛：加大造数正例比例 → 重造数据 → 重训，不要调模型参数硬凑。

### 8.6 截图清单（5–8 张）

1. `init_db` 成功输出（新库 + 新表）
2. 风控检查 API 返回（命中规则 + 评分）
3. 规则管理页（8 条行业规则可见）
4. 案件管理页（人工审核/拒绝案件出现）
5. 评估历史页（多次检查记录）
6. 用户风险画像页
7. 训练输出（val_auc / val_f1 / baseline 对比）
8. 仪表盘（今日评估数、风险趋势、Top 规则）

**验收**：`run_risk_check` 跑通，至少 1 个高风险用户能被识别；val_auc ≥ 0.7；业务规则 ≥ 5 条且 ≥ 3 条能命中样例数据；截图能演示完整流程。

---

## 9. 任务 4：演示 + 文档（1.5h）

### 9.1 录屏脚本（5–8 分钟，建议 7 分钟）

| 段落 | 时长 | 内容要点 |
|---|---|---|
| ① 业务说明 | 1 min | 旅游风控业务边界：OTA 预订/签证，欺诈场景 3 种（黄牛囤票、拒签刷签、黑产代订） |
| ② 跑通演示 | 2 min | `init_db` → 启动服务 → 跑一次风控检查 → 案件管理 → 评估历史 |
| ③ XGBoost 评估 | 1 min | 训练输出：val_auc / val_f1 / baseline 对比，说明“模型不是摆设” |
| ④ 业务规则讲解 | 2 min | 挑 3 条规则讲透：为什么设计、怎么命中、命中后决策（R001 / R008 / R030 效果最好） |
| ⑤ Vibe Coding 复盘 | 1 min | 用了哪些 LLM 协作产出、人做了哪些判断（schema、规则、验收） |

### 9.2 `README.md` 结构

1. 项目简介（一句话 + 行业背景）
2. 技术栈与架构图
3. 目录结构
4. 快速开始（环境 → `init_db` → 造数 → 启动 → 演示路径）
5. 业务设计（表结构、事件类型、黑名单类型）
6. 规则清单（8 条）
7. 特征清单 + 模型评估结果
8. 截图（8.6 的 5–8 张）
9. FAQ / 已知问题

### 9.3 `agent_design.md` 结构

1. 使用的 AI 工具（Claude / GPT / Cursor 等）与分工
2. 4 个任务的提示词模板（本计划附录可直接引用）
3. 人机协作流程：LLM 产出 → 人 review → 跑通验证
4. 迭代记录：哪次产出返工了、为什么、怎么改的（这是加分项）

### 9.4 现场提问准备（高频 5 问）

1. “你复用了哪些、新写了哪些？” → 背熟第 3 章红线表。
2. “这条规则为什么这么定？” → 讲业务动机（如 R001 拒签率高的人有刷签嫌疑）。
3. “特征怎么算的？” → 讲 1 条特征 SQL/查询逻辑（如拒签次数 = 近 90 天签证表 reject_history 求和）。
4. “模型 AUC 0.7 够吗？怎么提？” → 说够用于演示，提到更多样本 + 特征工程 + 调阈值。
5. “如果规则和模型打架怎么办？” → 双轨融合 + 一票否决的设计哲学。

---

## 10. 风险与预案

| 风险 | 影响 | 预案 |
|---|---|---|
| MySQL 起不来 / 密码不对 | 卡住全部任务 | 第 0 步先验证；连不上就用 Docker 起 MySQL 或改 `.env` |
| 依赖装不上（xgb/pymysql） | 训练/初始化失败 | 用 conda 环境 + requirements.txt；确认 Python 3.10 |
| XGBoost 假收敛（AUC 高但模型没用） | 验收不合格 | 用 `--target-pos-ratio 0.30` 重造数据；看 `is_fake_convergence` |
| 规则不命中样例数据 | 演示翻车 | 造数脚本内置风险画像用户；造数后先跑一遍规则验证脚本 |
| 特征名与规则/模型列不一致 | 运行时 500 或错位 | 改完特征立刻跑 `pytest` + 一次风控检查；`FEATURE_COLUMNS` 同步 |
| 时间不够 | 交不出完整仓库 | 优先级：任务 3 的“跑通 + 规则命中” > 任务 4 的“README + 录屏”；先保功能再补文档 |
| event_type 枚举改漏（schemas/config/validator） | API 422 | 全局搜索旧事件类型字符串，全部替换 |

---

## 11. 最终验收清单（对照任务书）

### 仓库可运行性

- [ ] Git 仓库完整，含代码、SQL、脚本、文档、截图
- [ ] `pip install -r requirements.txt` 后一条命令 `init_db` 建库建表成功
- [ ] `gen_business_data.py` 跑通，≥ 100 条业务数据
- [ ] 服务启动无报错，`/docs` 可访问

### 业务差异化

- [ ] 7 张业务表与电商版差异显著（实名/目的地/乘客/签证）
- [ ] 事件类型 ≥ 3 种且是行业真实痛点
- [ ] 黑名单类型含行业特有项（护照号/签证号/设备指纹）

### 引擎链路

- [ ] `run_risk_check` 跑通，≥ 1 个高风险用户被识别
- [ ] 业务规则 ≥ 5 条，≥ 3 条命中样例数据
- [ ] 三特征族已按行业重写，且 `FEATURE_COLUMNS` 同步
- [ ] val_auc ≥ 0.7，`is_fake_convergence = False`

### 演示与讲解

- [ ] 录屏 5–8 分钟（业务 1min / 跑通 2min / 模型 1min / 规则 2min / 复盘 1min）
- [ ] README 完整可读
- [ ] `agent_design.md` 说明 LLM 协作过程

---

## 12. 附录：Vibe Coding 提示词速查

### 任务 1：业务说明

```text
我要做一个【旅游行业】的风控系统，业务层跟电商完全不同。请帮我调研这个行业的典型欺诈场景、关键业务字段、事件类型，输出 1 页纸业务说明。注意符合国内监管要求。
```

### 任务 2：Schema + 造数

```text
这是我的业务说明：<粘贴 1-业务说明.md>。请帮我设计 7 张业务表 schema，写 SQLAlchemy 模型 + DDL，设计字段/关联/索引时要考虑后续风控特征计算的便利。同时写一个 Python 造数脚本，至少造 100 条业务数据，并包含风险画像用户。
```

### 任务 3：特征 + 规则 + 训练

```text
这是我的业务表 + 数据：<粘贴 schema + 样例数据>。请帮我设计 3 大特征族（用户/订单/乘客），字段映射到我的行业，写 compute_*_features 函数。同时设计 8 条业务规则，跑通 XGBoost 训练，用 val_auc 和 val_f1 评估，并检查假收敛。
```

### 任务 4：文档与讲解

```text
这是我的项目代码与截图：<粘贴 README 草稿 + 截图清单>。请帮我写完整 README 和 agent_design.md（我怎么用 LLM 协作），并生成一个 5–8 分钟现场讲解脚本，分 5 段：业务说明/跑通演示/XGBoost 评估/业务规则讲解/Vibe Coding 复盘。
```

---

> 一句话收尾：**先跑通，再完善；规则保底，AI 加分；每一步都可提交、可演示。**
