# 银行风险运营工作台 AI_Risk-Bank

> 面向教学的**银行风控演示系统**：对「登录 / 转账 / 贷款申请 / 绑卡」四类银行事件，执行黑名单前置检查 → 25 维特征计算 → 规则匹配 → XGBoost 融合 → 决策落库的完整风险决策流水线，并配套规则管理、黑名单、风险案件、评估流水与 AI 辅助分析工作台。

**重要免责声明**：本项目仅用于教学演示。所有数据均为虚构、掩码或哈希值；风险分、规则阈值与模型结果未经真实数据校准，**不得**用于授信审批、冻结账户、可疑交易报告或其他影响客户权益的生产决策，也不代表任何真实银行的授信、反欺诈或反洗钱结论。

---

## 目录

1. [项目定位与能力](#1-项目定位与能力)
2. [业务场景与四个事件](#2-业务场景与四个事件)
3. [系统架构](#3-系统架构)
4. [数据库设计](#4-数据库设计)
5. [25 维特征与 8 个控制场景](#5-25-维特征与-8-个控制场景)
6. [规则 + XGBoost 双轨决策](#6-规则--xgboost-双轨决策)
7. [目录结构](#7-目录结构)
8. [环境依赖](#8-环境依赖)
9. [环境变量配置 (.env)](#9-环境变量配置-env)
10. [MySQL / Docker 启动](#10-mysql--docker-启动)
11. [数据库初始化](#11-数据库初始化)
12. [业务造数与风险数据生成](#12-业务造数与风险数据生成)
13. [XGBoost 模型训练](#13-xgboost-模型训练)
14. [启动服务](#14-启动服务)
15. [运行测试](#15-运行测试)
16. [常见问题 FAQ](#16-常见问题-faq)
17. [页面截图与演示样例](#17-页面截图与演示样例)

---

## 1. 项目定位与能力

| 能力 | 说明 |
|---|---|
| 事件类型 | `登录`、`转账`、`贷款申请`、`绑卡` 四类银行事件 |
| 决策流水线 | `process_event` 四步（实体校验 → 补全兼容字段 → 黑名单前置 → 决策引擎）与 `run_risk_check` 七步（上下文 → 事件 → 特征 → 快照 → 规则 → 决策 → 落库） |
| 特征体系 | 25 维输入：14 个 `user_*` + 8 个 `order_*` + 3 个 `addr_*` |
| 控制手段 | 11 条数据库规则 + 1 个黑名单前置控制（黑卡）共 12 个控制场景 |
| 决策引擎 | 规则分 + XGBoost P(拒绝) sigmoid 校准分加权融合；一票否决（极高风险规则命中即拒绝） |
| 前端 | 专业银行风险运营工作台：运营总览 / 风险检查 / 规则管理 / 黑名单 / 风险案件 / 评估流水 / AI 风控助手 |
| 数据边界 | 只使用虚构数据；身份证号与银行卡号只保存不可逆摘要 |

---

## 2. 业务场景与四个事件

外部风险检查接口只要求四个字段：`event_type / source_id / user_id / event_data`。`source_id` 必须指向对应业务表的真实主键：

| `event_type` | `source_id` 指向 | 触发时机 | 典型风险 |
|---|---|---|---|
| `登录` | `LoginLog.login_id` | 用户发起登录或敏感身份校验 | 账户接管、新设备、异地登录、代理/Tor、撞库 |
| `转账` | `Transaction.txn_id` | 用户提交转账 | 盗转、异地大额、多卡归集、快进快出、黑卡收款 |
| `贷款申请` | `LoanApplication.loan_id` | 用户提交贷款申请 | 多头借贷、高负债、偿付能力不足 |
| `绑卡` | `BankCard.card_id` | 用户绑定新银行卡 | 盗绑卡、黑卡关联、异常设备批量绑卡 |

接口会校验 `source_id` 记录的真实存在（不存在返回 400），以及记录是否归属于请求的 `user_id`（借用他人记录返回 403）。

---

## 3. 系统架构

```
浏览器 (银行风险运营工作台)
   │  Jinja2 模板 + Bootstrap 5 + 原生 JS (static/app.js)
   ▼
FastAPI (app/)
   ├── routers/pages.py        页面路由 (总览/风险检查/规则/黑名单/案件/评估/AI 助手)
   ├── routers/*.py            业务 API (/api/risk /api/rules /api/blacklist ...)
   ├── service/validator.py    source_id 派发与归属校验
   ├── service/event.py        process_event 四步编排
   ├── engine/decision.py      run_risk_check 七步 + 双轨融合 + 一票否决
   ├── engine/feature.py       25 维特征计算
   ├── engine/rule.py          通用规则解析与匹配
   └── engine/ml_model.py      XGBoost 加载与推理 (sigmoid 校准)
   ▼
MySQL 8.0 (utf8mb4)
   ├── 8 张业务表 (user_info / bank_card / bank_transaction / loan_application / login_log / device_fingerprint / ip_geo_location / blacklist_extra)
   └── 9 张核心风控表 (risk_rule / risk_event / risk_feature / risk_assessment / risk_case / risk_blacklist / risk_user_profile / risk_action_log / risk_alert)
```

---

## 4. 数据库设计

### 4.1 8 张银行业务表

| 表 | 用途 | 关键字段 |
|---|---|---|
| `user_info` | 银行客户 | `user_id`、`kyc_level`、`credit_score_band`、`register_at` |
| `bank_card` | 银行卡 | `card_id`、`card_no_hash`、`card_type`、`credit_limit` |
| `bank_transaction` | 转账交易 | `txn_id`、`from_card`、`to_card`、`amount`、`channel`、`txn_at` |
| `loan_application` | 贷款申请 | `loan_id`、`amount`、`debt_ratio`、`monthly_income`、`institution_code` |
| `login_log` | 登录日志 | `login_id`、`device_id`、`ip`、`geo`、`success` |
| `device_fingerprint` | 设备指纹 | `device_id`、`user_id`（复合主键）、`first_seen`、`last_seen` |
| `ip_geo_location` | IP 环境 | `ip`、`geo`、`is_proxy`、`is_tor` |
| `blacklist_extra` | 扩展名单接入源 | `blacklist_type`、`value_hash`、`reason`、`expire_at` |

### 4.2 9 张核心风控表

| 表 | 用途 |
|---|---|
| `risk_rule` | 规则定义（通用 JSON 条件） |
| `risk_event` | 事件记录 |
| `risk_feature` | 25 维特征快照（每次评估 25 条） |
| `risk_assessment` | 评估结果（规则命中、最终分、等级、决策、ML 分） |
| `risk_case` | 风险案件（人工审核 / 自动拒绝） |
| `risk_blacklist` | 实时黑名单（用户/设备/IP/银行卡号/身份证号） |
| `risk_user_profile` | 用户风险画像 |
| `risk_action_log` | 审计操作日志 |
| `risk_alert` | 告警记录 |

---

## 5. 25 维特征与 8 个控制场景

### 5.1 25 维特征（顺序即模型 ABI，不可调换）

| 前缀 | 数量 | 语义 |
|---|---|---|
| `user_*` | 14 | 客户历史与关联画像（转账次数、金额、绑卡数、失败登录、设备数、贷款申请、负债率、账户年龄等） |
| `order_*` | 8 | 当前业务事件特征（金额、1 小时转账数、是否凌晨、设备天数、收款卡聚集、本次贷款机构数等） |
| `addr_*` | 3 | 设备/IP/地理环境（是否代理、是否 Tor、是否偏离常用城市） |

`order_*` 与 `addr_*` 前缀仅用于兼容模型输入形状，语义上分别表示“本次银行事件”与“设备/IP 环境”，与电商订单、收货地址无关。

### 5.2 12 个控制场景

| 场景 | 规则/控制 | 命中信号 |
|---|---|---|
| 异地大额转账 | `BANK_R001` | 偏离常用城市 + 金额 > 50000 |
| 凌晨密集操作 | `BANK_R002` | 0-5 点 + 1 小时内 ≥3 笔成功转账 |
| 新设备大额 | `BANK_R003` | 设备首次出现 <7 天 + 金额 > 30000 |
| 多卡归集 | `BANK_R004` | 1 小时内 ≥3 张付款卡向同一收款卡转入 |
| 信贷申请突击 | `BANK_R005` | 近 30 天 ≥3 家虚构机构贷款申请 |
| 设备多人共用 | `BANK_R006` | 同一设备指纹关联 ≥5 个客户 |
| 代理/Tor IP | `BANK_R007` | 事件环境命中代理或 Tor |
| 新设备失败登录 | `BANK_R008` | 新设备登录 + 近 30 天失败登录 ≥2（撞库） |
| 新设备批量绑卡 | `BANK_R009` | 新设备上绑卡 + 已绑定卡 ≥3（批量养号） |
| 新账户新设备操作 | `BANK_R010` | 注册 <7 天 + 新设备（通用，四事件均生效） |
| 代理网络新设备登录 | `BANK_R011` | 代理网络 + 新设备登录（一票否决拒绝） |
| 黑卡前置拦截 | 核心 `risk_blacklist` | 银行卡号哈希命中黑名单，直接拒绝（`rule_count=0`） |

---

## 6. 规则 + XGBoost 双轨决策

1. **黑名单前置**：先检查用户/设备/IP/银行卡号/身份证号五类黑名单，命中即短路返回 `blocked_by`，不计算特征、不调用模型。
2. **规则分**：`max(各规则分) + 3 × (额外命中数)`，上限 100。
3. **ML 分**：XGBoost 输出 P(拒绝)，经 sigmoid 校准 `100 × (1 - e^(-3p))` 映射到 0-100 风险分。
4. **融合**：`final_score = 0.5 × rule_score + 0.5 × ml_score`。
5. **一票否决**：任意命中规则等级为「极高」→ 强制决策「拒绝」、等级「极高」，分数抬到至少 90，不被 ML 低分推翻。
6. **决策映射**：分数 <30 通过 / <60 标记 / <85 人工审核 / ≥85 拒绝。人工审核与拒绝会创建风险案件。

---

## 7. 目录结构

```
risk-control/
├── app/                    应用代码（5 层：routers / service / engine / models / schemas）
│   ├── engine/             决策引擎：feature.py、rule.py、decision.py、ml_model.py
│   ├── service/            validator.py、event.py、case.py、action_log.py、alert.py
│   ├── routers/            页面与 API 路由
│   ├── models.py           核心风控表 ORM
│   ├── models_business.py  8 张业务表 ORM
│   └── models_risk.py      核心表枚举与关联
├── scripts/                初始化 / 造数 / 训练 / 启动脚本
│   ├── init_db.py          数据库初始化
│   ├── gen_business_data.py  银行业务造数（可重复、幂等）
│   ├── gen_train_dataset.py  训练数据生成
│   ├── train_xgb_model.py     XGBoost 训练
│   └── main.py             FastAPI 入口
├── sql/                    建表与种子数据
│   ├── init_business_tables.sql / init_business_data.sql
│   ├── init_risk_tables.sql / init_risk_data.sql
│   └── migration_*.sql     历史迁移（幂等）
├── templates/              6+1 个页面模板（base + 6 工作台 + AI 助手）
├── static/                 app.css / app.js / favicon.svg
├── tests/                  全量测试
├── docs/                   设计与验证文档、截图
├── docker/                 Dockerfile / docker-compose.yml / nginx.conf
├── uv/                     uv 依赖管理（可选）
├── requirements.txt        pip 依赖
└── .env.example            环境变量模板（复制为 .env）
```

---

## 8. 环境依赖

- Python 3.11+（开发用 3.12 验证）
- MySQL 8.0（本地或 Docker）
- 可选：Docker / Docker Compose、Google Chrome（用于录屏与浏览器验收）

Python 依赖见 `requirements.txt`，核心包括：`fastapi 0.115`、`uvicorn 0.34`、`sqlalchemy 2.0`、`pymysql`/`aiomysql`、`pydantic 2.10`、`jinja2 3.1`、`pandas`/`numpy`、`scikit-learn`、`xgboost 2.0`、`pytest 8.3`、`faker`、`python-dotenv`。

### 8.1 Windows PowerShell 安装

```powershell
cd D:\Program Files\temp_data\Projects\SGG_projects\risk-control
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 8.2 Linux / macOS

```bash
cd /path/to/risk-control
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> Windows 中文环境如遇 GBK 解码问题，先执行 `$env:PYTHONUTF8='1'` 再运行脚本。

---

## 9. 环境变量配置 (.env)

复制根目录 `.env.example` 为 `.env` 并填写（`.env` 已被 `.gitignore` 忽略，不会提交）：

```powershell
Copy-Item .env.example .env
```

`.env.example` 内容（本机开发示例）：

```ini
# 本地开发数据库（示例：Docker MySQL 映射到 127.0.0.1:33307）
DB_HOST=127.0.0.1
DB_PORT=33307
DB_USER=root
DB_PASSWORD=
DB_NAME=bank_risk
TEST_DB_NAME=bank_risk_test

# XGBoost
XGB_MODEL_PATH=app/engine/xgb_model.json
XGB_ENABLED=true

# AI 助手（阿里云百炼，OpenAI 兼容；不填则 AI 助手降级提示）
LLM_API_KEY=
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
```

> 本机已有专用 MySQL 容器时（映射 `127.0.0.1:33307`，root 空密码），可直接使用上述示例。生产环境请改 `DB_PASSWORD` 并切勿提交 `.env`。

---

## 10. MySQL / Docker 启动

### 10.1 方式 A：专用 MySQL 容器（推荐开发用）

```powershell
docker run -d --name ai-risk-goal3-mysql `
  -e MYSQL_ALLOW_EMPTY_PASSWORD=yes `
  -e MYSQL_DATABASE=bank_risk_test `
  -p 127.0.0.1:33307:3306 `
  mysql:8.0 `
  --character-set-server=utf8mb4 `
  --collation-server=utf8mb4_0900_ai_ci
```

### 10.2 方式 B：项目自带 docker-compose（MySQL + app + nginx）

```powershell
cd docker
Copy-Item .env.example .env
docker compose up -d
```

首次启动 MySQL 容器会自动执行 `sql/init_business_tables.sql`、`sql/init_risk_tables.sql`、`sql/init_business_data.sql`、`sql/init_risk_data.sql`。验证：

```powershell
docker compose ps
curl http://localhost:8000/docs
```

---

## 11. 数据库初始化

开发库 `bank_risk` / 测试库 `bank_risk_test`。初始化脚本默认幂等，不删除数据库；只有显式 `--reset --yes` 且库名严格为 `bank_risk` 或 `bank_risk_test` 时才重建：

```powershell
# 开发库（首次）
.\.venv\Scripts\python.exe scripts\init_db.py --db bank_risk

# 空库重建（会清空该库所有数据，谨慎）
.\.venv\Scripts\python.exe scripts\init_db.py --db bank_risk_test --reset --yes
```

初始化会创建 8 张业务表 + 9 张核心风控表，并写入静态业务种子与 11 条银行规则 + 黑卡种子。

---

## 12. 业务造数与风险数据生成

### 12.1 银行业务造数（可重复、幂等）

```powershell
.\.venv\Scripts\python.exe scripts\gen_business_data.py --count 2400 --seed 20260812
```

`--count` 为四类 source 业务记录合计（登录/转账/贷款申请/绑卡各 1/4），固定 `--seed` 可重复生成相同数据。生成的批次覆盖异地大额、凌晨密集、新设备大额、多卡归集、多头借贷、设备多人共用、代理/Tor 与黑卡候选等风险模式。

### 12.2 训练数据生成

```powershell
.\.venv\Scripts\python.exe scripts\gen_train_dataset.py --count 2000 --seed 20260812 --clean
```

从业务数据出发，经完整 `process_event → run_risk_check` 流水线生成 `risk_event`、`risk_feature`、`risk_assessment`。标签：`通过/标记 → 0`，`人工审核/拒绝 → 1`。

> 首次启动完整路径（初始化 → 造数 → 训练 → 启动）可参考 `scripts/one_command.py`。

---

## 13. XGBoost 模型训练

```powershell
.\.venv\Scripts\python.exe scripts\train_xgb_model.py
```

训练脚本从 `risk_assessment`（`ml_score IS NULL`）读取样本，JOIN 出 25 维特征，按 `GroupShuffleSplit(user_id)` 切分防止用户级泄漏，输出指标到 `docs/model-metrics.json`，模型保存到 `app/engine/xgb_model.json`。

训练门槛：验证集 AUC ≥ 0.70、F1 ≥ 0.50。教学数据上的双指标为 1.0（规则即标签来源，属教学可接受结果，不代表真实泛化能力，详见 [docs/model-evaluation.md](docs/model-evaluation.md)）。

---

## 14. 启动服务

```powershell
# 推荐：直接 uvicorn（app-dir 指向 scripts）
.\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --app-dir scripts
```

访问入口：

| URL | 用途 |
|---|---|
| `http://localhost:8000/` | 运营总览 |
| `http://localhost:8000/risk-check` | 风险检查（四事件） |
| `http://localhost:8000/rules` | 规则管理 |
| `http://localhost:8000/blacklist` | 黑名单 |
| `http://localhost:8000/cases` | 风险案件 |
| `http://localhost:8000/assessments` | 评估流水 |
| `http://localhost:8000/chat` | AI 风控助手 |
| `http://localhost:8000/docs` | Swagger API 文档 |

---

## 15. 运行测试

```powershell
# 全量测试（Windows 下用 --basetemp 绕过沙箱临时目录权限）
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest -q --basetemp=$env:TEMP\pytest_risk_control

# DDL 实库验收（需真实数据库，默认 skip）
$env:DDL_CHECK_ENABLED='1'
.\.venv\Scripts\python.exe -m pytest tests\test_ddl_sync.py -q
```

测试需连接专用 MySQL（`bank_risk_test`，默认读取 `.env`）。

---

## 16. 常见问题 FAQ

**Q1: 启动报 `ModuleNotFoundError: No module named 'app'`**
A: 在项目根目录运行，或使用 `--app-dir scripts` 参数；确认 `.venv` 已激活。

**Q2: 连接数据库失败 / Access denied**
A: 确认 MySQL 容器已启动，`.env` 的 `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD` 与容器映射一致（本机容器示例为 `127.0.0.1:33307` / root / 空密码）。

**Q3: XGBoost 模型没加载 / 没有模型文件**
A: 确认 `app/engine/xgb_model.json` 存在且 `XGB_ENABLED=true`。模型缺失时自动降级为纯规则，不影响业务；需要训练执行 `scripts\train_xgb_model.py`。

**Q4: 风险检查返回 400**
A: `source_id` 指向的业务记录不存在，或 `event_type` 与 `source_id` 不匹配（例如用转账 `txn_id` 提交登录事件）。请使用演示样例中的正确配对。

**Q5: 风险检查返回 403**
A: 记录存在但归属的 `user_id` 与请求不符（越权防护）。核对样例的 `user_id` / `source_id` 配对。

**Q6: 数据库中文乱码**
A: 确认 MySQL 使用 utf8mb4 字符集；初始化脚本已带 `CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci`。

**Q7: 端口 8000 被占用**
A: 改启动命令的 `--port`，或结束占用进程。

**Q8: AI 助手报 LLM 错误**
A: 检查 `.env` 的 `LLM_API_KEY` 与 `LLM_BASE_URL`（阿里云百炼 OpenAI 兼容地址）。不填 key 时助手会降级提示。

**Q9: 如何重置演示数据？**
A: 对 `bank_risk_test` 执行 `scripts\init_db.py --reset --yes` 后按顺序重跑造数与训练。

---

## 17. 页面截图与演示样例

截图位于 `docs/screenshots/`（8 张）：

`01-dashboard.png` 运营总览 · `02-risk-check-input.png` 风险检查输入 · `03-risk-check-pass.png` 正常通过 · `04-risk-check-rule-hit.png` 高风险规则命中 · `05-risk-check-blacklist.png` 黑名单拒绝 · `06-cases.png` 风险案件 · `07-assessments.png` 评估流水 · `08-rules.png` 规则管理

### 演示样例（全部为虚构数据）

| 场景 | `event_type` | `source_id` | `user_id` | 预期 |
|---|---|---|---|---|
| 正常登录 | `登录` | `DEMO_LOGIN_006` | `DEMO_USR_006` | 通过 / 0 分 / 低 |
| 异地大额转账 | `转账` | `DEMO_TXN_001` | `DEMO_USR_002` | 拒绝 / 98 / 极高，命中 R001+R003+R007+R006 |
| 多卡归集转账 | `转账` | `DEMO_TXN_003` | `DEMO_USR_002` | 拒绝 / 98 / 极高，命中 R004+R002+R007+R006 |
| 信贷申请突击 | `贷款申请` | `DEMO_LOAN_003` | `DEMO_USR_010` | 拒绝 / 85 / 极高，命中 R005 |
| 正常绑卡 | `绑卡` | `DEMO_CARD_003` | `DEMO_USR_003` | 通过 / 0 分 / 低 |
| 黑卡短路 | `转账` | `DEMO_TXN_017` | `DEMO_USR_009` | 拒绝 / 100 / 极高，`blocked_by=银行卡号`，`rule_count=0` |

### 新增规则演示样例（R008–R011，全部为虚构数据）

| 场景 | `event_type` | `source_id` | `user_id` | 命中规则 | 说明 |
|---|---|---|---|---|---|
| 新设备失败登录 | `登录` | `DEMO_LOGIN_026` | `DEMO_USR_010` | `BANK_R008` | 新设备（DEV_010）+ 近 30 天 3 次失败登录后成功 |
| 新设备批量绑卡 | `绑卡` | `DEMO_CARD_030` | `DEMO_USR_010` | `BANK_R009` | 新设备上绑第 4 张卡（已绑 3 张） |
| 新账户新设备操作 | `转账` | `DEMO_TXN_026` | `DEMO_USR_011` | `BANK_R010` | 注册不足 7 天的新账户用新设备首笔转账 |
| 代理网络新设备登录 | `登录` | `DEMO_LOGIN_001` | `DEMO_USR_001` | `BANK_R011`（一票否决） | 代理网络 + 新设备登录，强制拒绝 / 90 / 极高 |

> 以上 4 条规则的 `risk_level/risk_score/action` 定义见规则管理页；最终 `final_score` 会与 XGBoost 双轨融合（0.5/0.5），除 `BANK_R011` 一票否决外，中/高风险规则命中后仍可能被模型低分稀释为「通过/标记」，属系统设计内行为（与上表 `DEMO_LOAN_003` 依赖模型同理）。

> 演示数据仅供教学，全部为虚构标识或不可逆摘要。
>
> 注意：`DEMO_LOAN_003` 的「拒绝 / 85」依赖 XGBoost 已加载（模型未加载/`XGB_ENABLED=false` 时该样例为「人工审核 / 75」，因 R005 无「极高」一票否决）；其余样例由规则或黑名单决定，不依赖模型。

更完整的业务设计见 `1-业务说明.md`，重构契约见 `docs/refactor-contract.md`，前端设计与设计 token 见 `docs/frontend-design.md`，模型评估见 `docs/model-evaluation.md`，演示讲解脚本见 `docs/demo-script.md`。
