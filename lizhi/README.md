# 旅游风控系统 AI_Risk — 项目文档

> 基线项目：尚硅谷 `AI_Risk` 风控系统（电商版）→ 业务拓展到**旅游行业**（OTA 平台：机票 / 酒店 / 签证 / 跟团游）。
> 风控核心 9 张表与 7 步决策流水线完全复用，业务层（7 张业务表 + 25 维特征 + 8 条规则 + 造数）按旅游行业全部重写。

---

## 一、业务说明

### 1.1 业务边界

用户在 OTA 平台完成 **机票 / 酒店 / 签证 / 跟团游** 的「注册 → 搜索 → 下单 → 支付 → 出票/确认 → 出行核销 → 退改售后」全流程。
风控事件统一按基线契约接入：

```python
RiskCheckRequest(event_type, source_id, user_id, event_data) -> RiskCheckResponse
```

完整一页纸业务说明见 [1-业务说明.md](1-业务说明.md)，要点如下。

### 1.2 典型欺诈场景（6 类）

| 场景 | 典型行为 | 风控信号 |
|---|---|---|
| 机票黄牛囤票/占座倒卖 | 放票瞬间批量抢购、占座不付款后高价转售 | 凌晨高频下单、同航班 1 小时多单、取消率高 |
| 退改签诈骗/病退材料造假 | 冒充客服诱导转账；伪造就医材料骗全额退票 | 退改集中、收款账户分离、命中电诈黑名单 |
| 酒店到店无房/恶意索赔 | 幽灵房源；团伙利用免费取消规则批量索赔 | 同设备/IP 关联多人索赔、频次金额异常 |
| 签证材料造假/拒签隐瞒 | 伪造流水、隐瞒拒签史、短期多国密集申请 | 90 天多次拒签、30 天多国申请 |
| 营销薅羊毛/虚假交易 | 优惠红包批量套取、刷单炒信 | 设备农场、同设备多账号、注册即下单 |
| 账户盗用/积分里程套现 | 盗号兑换、绑卡盗刷、异地新设备消费 | 登录地与常用地不符、证件与历史不一致 |

### 1.3 关键业务字段（43 个，覆盖任务书 A.1 全部 7 张必建业务表）

| 业务表 | 核心字段 |
|---|---|
| `user_info` | user_id, name, real_name_status, vip_level, account_age_days |
| `order_info` | order_id, user_id, order_type, total_amount, dest_country, depart_date, return_date, passenger_count |
| `passenger_info` | passenger_id, order_id, name, id_type, id_number, nationality, age |
| `visa_application` | visa_id, user_id, dest_country, visa_type, reject_history, submit_time |
| `booking_hotel` | booking_id, order_id, hotel_id, check_in, check_out, room_count, is_refundable |
| `booking_flight` | booking_id, order_id, flight_no, depart_airport, arrive_airport, cabin_class |
| `blacklist_extra` | entry_id, type, value, reason, expire_at |

### 1.4 业务事件类型（8 种）

`预订下单` / `支付成功` / `出票确认` / `退改签申请` / `出行核销` / `签证申请` / `索赔投诉` / `评价发布`

### 1.5 国内监管合规要点

- 《旅游法》第 52/58 条：旅游者个人信息保密；包价旅游合同书面形式。
- 《在线旅游经营服务管理暂行规定》（文旅部令第 4 号）：平台内经营者实名核验登记、数据安全。
- 实名制：机票记名（购票证件与乘机一致）、酒店住宿实名登记（《旅馆业治安管理办法》第 6 条）。
- 《个人信息保护法》《数据安全法》《网络安全法》：证件号等敏感信息最小必要收集、哈希存储。
- 《反电信网络诈骗法》：机票退改签电诈识别与预警。

---

## 二、快速启动

环境要求：Python 3.12（项目自带 `.venv`）、MySQL 8（本机 `localhost:3306`，密码写在 `.env`）。

```powershell
# 1. 安装依赖（首次）
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 初始化数据库（7 业务表 + 9 风控表 + 8 条规则 + 553 条业务数据）
.\.venv\Scripts\python.exe scripts\init_db.py --reset --yes

# 3. 造旅游业务数据（120 订单 + 5 类 RISK 高风险用户，seed=42 可复现）
.\.venv\Scripts\python.exe scripts\gen_business_data.py --reset

# 4. 造风控评估数据（300 条，正例拉到 30%+，训练用）
.\.venv\Scripts\python.exe scripts\gen_risk_data.py --count 300 --balance-pos --target-pos-ratio 0.30

# 5. 训练 XGBoost（输出 val_auc / val_f1）
.\.venv\Scripts\python.exe -u scripts\train_xgb_model.py

# 6. 启动页面端
.\.venv\Scripts\python.exe scripts\main.py
# 浏览器打开 http://localhost:8000
```

一键跑完整流程（含训练与回填）：

```powershell
.\.venv\Scripts\python.exe scripts\one_command.py
```

> 本机 MySQL 密码已写入 `.env`（`DB_PASSWORD=123456`），`init_db.py` / `gen_business_data.py` 会自动读取，无需 `--password`。

---

## 三、跑通演示

### 3.1 页面端

`scripts/main.py` 启动后提供 7 个页面 + 8 组 API：

| 页面 | 地址 | 说明 |
|---|---|---|
| 仪表盘 | `/` | 今日评估/高风险/待审案件/趋势 |
| 风险检查 | `/risk-check` | 手动发起 8 类事件检查 |
| 规则管理 | `/rules` | 8 条旅游规则增删改查 |
| 案件管理 | `/cases` | 人工审核/拒绝案件 |
| 评估历史 | `/assessments` | 全量评估 + ML 评分 |
| 黑名单 | `/blacklist` | 用户/护照号/设备指纹/IP 等 |
| AI 助手 | `/chat` | qwen-plus 驱动的风控问答 |

### 3.2 高风险用户命中演示（规则 + 模型双轨）

```powershell
# 冒烟：RISK01 黄牛囤票 → 98 分拒绝（R003+R004）
.\.venv\Scripts\python.exe -m app.service.event
```

实测结果（含 XGBoost 融合）：

| 用户 | 事件 | 命中规则 | 评分 | 决策 | ML |
|---|---|---|---|---|---|
| RISK01 黄牛囤票 | 预订下单 | R003(极高)+R004 | 96 | 拒绝 | 0.9558 |
| RISK02 拒签历史 | 签证申请 | R001(极高)+R002 | 98 | 拒绝 | - |
| RISK03 新用户大单 | 预订下单 | R006 | 55 | 标记 | - |
| RISK05 高频退改 | 退改签申请 | R008 | 75 | 人工审核 | - |

### 3.3 跨天趋势数据（仪表盘用）

```powershell
# 近 1 天 50 条（live 模式，今日可见）
.\.venv\Scripts\python.exe scripts\gen_risk_data_with_dates.py --days 1 --per-day 50 --live

# 近 30 天每天 20 条（趋势图跨天）
.\.venv\Scripts\python.exe scripts\gen_risk_data_with_dates.py --days 30 --per-day 20
```

---

## 四、XGBoost 评估

### 4.1 训练数据

- 数据源：`gen_risk_data.py` 从真实业务数据造评估（订单 8 类事件 + 签证申请事件），规则打分作为标签。
- 二分类标签：`通过/标记 → 0`，`人工审核/拒绝 → 1`。
- 训练取数：只取 `risk_assessment.ml_score IS NULL` 的干净数据（造数后强制置 NULL）。

### 4.2 训练结果（实测）

```text
拉取评估: 300 条  训练矩阵: X.shape=(300, 25)  正例 158 条 (52.7%)

全量指标:   AUC=0.9997  F1=0.9968  Acc=0.9967  P=0.9937  R=1.0000
验证集:     n=60  val_auc=1.0000  val_f1=1.0000  Acc=1.0000 (最佳 F1 阈值=0.35)

best_iteration: 50   scale_pos_weight: 0.90
模型保存: app/engine/xgb_model.json (40.8 KB)
```

> 说明：合成业务数据中特征直接编码规则信号，模型区分度极高；真实生产数据正例比例通常 < 15%，可用 `--target-pos-ratio 0.30` 重造、或调 `XGB_*` 超参防假收敛。

### 4.3 双轨融合决策

`final_score = 0.5 × 规则分 + 0.5 × sigmoid(ML 概率)`，命中「极高」规则时一票否决强制拒绝（评分抬到 ≥90，不被 ML 推翻）。实测 RISK01：规则 95 分 + ML 0.9558 → 最终 96 分拒绝。

### 4.4 特征重要性

Top 3 特征解释了约 63% 的模型决策（训练时输出 TOP 10 gain 明细），重点优化：`user_same_flight_1h_count` / `user_visa_reject_count` / `order_is_international` 等旅游专属特征。

---

## 五、业务规则讲解

8 条规则与欺诈场景一一对应（数据在 `risk_rule` 表，JSON 条件由规则引擎求值）：

| 规则 | 触发条件 | 等级/动作 | 分值 | 对应场景 |
|---|---|---|---|---|
| R001 拒签历史拦截 | `user_visa_reject_count >= 2` | 极高/拒绝 | 95 | 签证材料造假 |
| R002 短期多国签证 | `user_visa_multi_country_30d >= 3` | 高/人工审核 | 70 | 非法移民链条 |
| R003 黄牛囤票拦截 | `order_same_flight_1h_count >= 5` | 极高/拒绝 | 95 | 机票黄牛 |
| R004 0点突击下单 | 凌晨下单 且 行程<7 天 | 中/标记 | 45 | 突击抢票 |
| R005 大额跨境游 | 出境 且 金额>20000 | 高/人工审核 | 72 | 大额异常 |
| R006 新用户大单 | 注册<7天 且 金额>10000 | 中/标记 | 55 | 黑产小号 |
| R007 乘客信息不一致 | `order_new_passenger_rate >= 0.7` | 中/标记 | 50 | 证件盗用 |
| R008 高频退改嫌疑 | `user_refund_rate >= 0.5` | 高/人工审核 | 75 | 病退造假 |

评分公式：`max(命中规则分) + 3 × (额外命中数)`，上限 100；「极高」规则一票否决。

---

## 六、系统架构与数据设计

### 6.1 表结构（16 张）

- 7 张旅游业务表：`user_info / order_info / passenger_info / visa_application / booking_hotel / booking_flight / blacklist_extra`（DDL 见 [sql/init_business_tables.sql](sql/init_business_tables.sql)）
- 9 张风控核心表：`risk_rule / risk_event / risk_feature / risk_assessment / risk_case / risk_blacklist / risk_user_profile / risk_action_log / risk_alert`（完全复用）

### 6.2 三大特征族（25 维，[app/engine/feature.py](app/engine/feature.py)）

| 特征族 | 数量 | 内容 |
|---|---|---|
| 用户 | 14 | 订单活跃度/金额/取消/退改率/凌晨下单/同航班囤票/签证/注册时长 |
| 订单 | 8 | 金额/乘客数/夜间下单/距出发天数/行程天数/出境/同航班窗口/新乘客占比 |
| 目的地（原"地址"族映射） | 3 | 目的地国家数/出境占比/当前目的地是否去过 |

特征名与 `ml_model.py::FEATURE_COLUMNS` 严格对齐；签证申请等无订单事件也补全 25 维（order 特征填 0）。

### 6.3 决策流水线（复用基线 7 步）

`校验 → 事件落库 → 特征计算+快照 → 规则匹配 → 评分决策(规则+ML 双轨) → 落库(评估/案件/画像) → 响应`

黑名单前置拦截：`用户 → 护照号 → 设备指纹 → IP` 短路，撞黑直接拒绝不落审计噪音。

### 6.4 AI 风控助手

`/chat` 页面使用阿里云百炼 `qwen-plus`（配置在 `.env` 的 `LLM_*`），8 个 LangChain 工具（风险检查/案件/画像/黑名单/仪表盘/趋势/规则效果/业务查询），支持多轮会话。

---

## 七、Vibe Coding 复盘

本项目按任务书 4 个递进任务，全程用 LLM 协作（vibe coding）完成，详见 [agent_design.md](agent_design.md)。核心体会：

1. **先摸清基线契约再动手**：`process_event` 4 字段契约、`FEATURE_COLUMNS` 25 维对齐、规则 JSON 条件格式、训练数据 `ml_score IS NULL` 取数——这些"隐形契约"决定改哪、怎么改。
2. **每步都有可验证的验收**：任务 1 一页纸、任务 2 `init_db` + 造数、任务 3 规则命中 + `val_auc/val_f1`、任务 4 文档 + 页面端。
3. **踩过的坑**：SQLAlchemy 枚举读结果也校验（只改 DDL 不够）；PowerShell 管道会吃掉中文（测试脚本要用 UTF-8/base64）；训练样本"特征不全"被静默丢弃（签证事件要补全 25 维）；残留旧服务进程占端口导致新代码不生效。
4. **LLM 的价值**：把"陌生行业业务抽象"（旅游特征映射）和"改完不破坏契约"这两件最耗时的事，从小时级压缩到分钟级；人工负责验收与业务判断。

---

## 八、目录结构

```text
ai_risk/
├── app/
│   ├── models_business.py        # 7 张旅游业务表 ORM
│   ├── models_risk.py            # 9 张风控核心表 ORM（复用）
│   ├── config.py                 # 配置 + 旅游事件类型/黑名单类型
│   ├── engine/
│   │   ├── feature.py            # 25 维旅游特征
│   │   ├── rule.py               # 规则引擎（JSON 条件求值）
│   │   ├── decision.py           # 7 步决策流水线（复用）
│   │   └── ml_model.py           # XGBoost 加载/推理/训练
│   ├── service/                  # event / validator / case 等
│   ├── routers/ + api.py         # 页面 + API
│   └── agent/                    # AI 助手（tools + chat）
├── scripts/                      # 10 个脚本（见上文）
├── sql/                          # DDL + 数据 + 8 条规则
├── templates/ static/            # 页面端
├── 1-业务说明.md                 # 任务 1 交付物
└── agent_design.md               # LLM 协作复盘
```

---

## 九、常见问题

**Q1：8000 端口被占用 / 页面连不上**
结束残留的旧服务进程后重启：`python scripts/main.py`。

**Q2：`python scripts/init_db.py` 连不上 MySQL**
检查 `.env` 的 `DB_PASSWORD` 是否为本机密码，或加 `--password xxx`。

**Q3：训练时提示样本不足 / 正例比例低**
先 `gen_risk_data.py --count 300 --balance-pos --target-pos-ratio 0.30` 重造，再训练。

**Q4：模型文件丢了**
重新训练：`train_xgb_model.py`（真实数据）或 `train_demo_model.py`（合成演示数据）。
