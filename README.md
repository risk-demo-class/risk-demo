# 华信银行 · 信贷风控平台 — AI-BankRisk

> 双轨决策引擎（规则 + XGBoost）· 4 类信贷事件 · 25 维特征 · 30 条规则 · 8 个 AI Agent 工具

银行信贷风控系统 AI-BankRisk —— 一套面向**贷款审批全流程**的智能风控平台：以贷款申请为主线，叠加反欺诈、信用风险、反洗钱合规三个风险维度，通过「规则引擎 + XGBoost 双轨融合」实时决策，并接入 LLM Agent 提供自然语言风险问答与处置能力。

本系统由早期电商风控项目做**全量业务改造**而来，所有业务实体、特征、规则、模型均已迁移到**银行信贷风控**语境，适合作为**面试述职与课程演示**的完整实战项目。

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.0-4479A1?logo=mysql&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-2.0-1691B3?logo=xgboost&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-362%20passing-2ea44f)
![LLM](https://img.shields.io/badge/LLM-%E9%98%BF%E9%87%8C%E4%BA%91%E7%99%BE%E7%82%BC-FF6A00)
![License](https://img.shields.io/badge/License-MIT-blue)

---

## 目录

1. [项目简介](#项目简介)
2. [功能特性](#功能特性)
3. [技术栈](#技术栈)
4. [快速开始](#快速开始)
5. [项目结构](#项目结构)
6. [核心设计](#核心设计)
7. [使用说明](#使用说明)
8. [测试](#测试)
9. [部署](#部署)
10. [常见问题 FAQ](#常见问题-faq)
11. [License](#license)

---

## 项目简介

AI-BankRisk 是一个**端到端可运行**的银行信贷风控系统，覆盖「数据建模 → 特征工程 → 规则制定 → 模型训练 → 实时决策 → 人工复核 → 案件处置 → Agent 问答」全链路。

- **背景**：由电商风控项目做银行信贷风控全量改造，业务实体、25 维特征、30 条规则、PD 违约概率模型全部按信贷业务语境重建；
- **双轨决策**：规则引擎（30 条 R101-R604 银行规则）+ XGBoost 违约概率模型（sigmoid 校准）融合打分，规则一票否决、ML 协同增强；
- **面向人群**：应届生 / 转岗工程师面试述职、课程演示、风控系统入门实战。

系统名：**华信银行 · 信贷风控平台**（前端品牌）/ **银行信贷风控系统 AI-BankRisk**（工程名）。

---

## 功能特性

- 🚦 **双轨决策引擎**：规则分 + ML 违约概率加权融合（α/β 权重可调），规则可一票否决（命中高风险直接拒绝），ML 概率经 sigmoid 校准对齐风险分量纲；
- 📏 **30 条预置银行规则**（R101-R604）：欺诈 / 信用 / 反洗钱 / 账户 / 贷后 / 合规 6 大分类，支持嵌套条件（`and` / `or`）、软删、优先级排序；
- 🧠 **XGBoost 违约概率（PD）模型**：25 维特征（`cust_14 + loan_8 + dev_3`），80/20 stratify 拆分、早停、`scale_pos_weight` 防过拟合、最佳 F1 阈值、特征重要性 TOP10；
- 🧩 **4 类信贷事件**：贷款申请 / 放款 / 还款 / 客户投诉，统一走 7 步 `process_event()` 决策流水线；
- 📋 **案件管理**：自动建案、状态机流转（待审核 → 审核中 → 通过/拒绝/关闭）、24h 超时自动关闭、案件与评估/规则命中关联；
- 🚫 **多类型黑名单**：客户 / 手机号 / 地址 / 设备 4 类，支持新增、命中检查、软删；
- 🤖 **8 个 AI Agent 工具**：风险检查、案件查询、客户画像、黑名单管理、仪表盘统计、风险趋势、规则效能、业务数据查询，LangChain `@tool` 封装，支持自然语言对话；
- ⏰ **后台调度**：案件超时自动关闭（24h）、告警自动检查（15 分钟）；
- 🔔 **实时告警**：待审积压、规则命中率异常、黑名单命中率异常等阈值告警；
- 🧪 **362 个自动化测试**：含 DDL 同步、特征一致性、规则引擎、决策引擎、Agent、日志、调度、分页布局等全量覆盖；
- 🐳 **一键部署**：Docker Compose 三容器（Nginx + FastAPI + MySQL）开箱即用；
- 📊 **可视化仪表盘**：风险趋势、规则命中分布、待审案件、黑名单命中统计，左侧固定布局 + 通用分页。

---

## 技术栈

| 分层 | 技术 |
|---|---|
| **后端** | Python 3.11 · FastAPI 0.115 · Uvicorn 0.34 · SQLAlchemy 2.0 · Pydantic 2.10 |
| **数据库** | MySQL 8.0（utf8mb4）· aiomysql 0.2 · pymysql 1.1 |
| **前端** | Jinja2 3.1 · 原生 HTML/CSS/JS 模板 · Nginx 反代 |
| **数据** | pandas 2.2 · numpy 2.2 · faker 33 · ulid-py 1.1 |
| **ML** | XGBoost 2.1 · scikit-learn（train_test_split / roc_auc / f1） |
| **LLM** | LangChain 1.2 · langchain-openai 1.1 · langchain-deepagents 0.5（阿里云百炼 OpenAI 兼容） |
| **质量** | pytest 8.3 · pytest-asyncio 0.25 · httpx 0.27 · cryptography 44 |

---

## 快速开始

> 目标：新环境 **10 分钟内**跑通「初始化 → 造数据 → 训练 → 启动」全流程。

### 前置条件

- Python 3.11
- MySQL 8.0（本地或 Docker）
- （可选）阿里云百炼 API Key，用于 Agent 对话

### 1. 安装依赖

```bash
# conda（推荐）
conda create -n risk python=3.11 -y
conda activate risk
pip install -r requirements.txt

# 或 venv
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 准备 MySQL

```bash
# Docker（推荐）
docker run -d --name risk-mysql \
  -e MYSQL_ROOT_PASSWORD=123321 \
  -e MYSQL_DATABASE=ecs \
  -p 3306:3306 \
  mysql:8.0 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_0900_ai_ci

# 或本地 MySQL：确保 utf8mb4 + 用户能 CREATE DATABASE
```

### 3. 配置 .env

```ini
# .env（项目根目录）
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=123321
DB_NAME=ecs
TEST_DB_NAME=ecs_test

# LLM（阿里云百炼 OpenAI 兼容，Agent 功能需要）
LLM_API_KEY=sk-你的key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

# XGBoost 开关（默认 True，第一次没模型时自动降级为纯规则）
XGB_ENABLED=True
```

### 4. 初始化数据库

```bash
python scripts/init_db.py
```

按顺序执行：创建 `ecs` 库 → `init_business_tables.sql`（17 张业务表）→ `init_business_data.sql`（约 4100 条业务数据）→ `init_risk_tables.sql`（9 张风控表）→ `init_risk_data.sql`（30 条预置规则 R101-R604）。

加 `--drop` 参数可**先删后建**（⚠️ 危险，会清空所有数据）。

### 5. 生成业务数据 + 训练模型

```bash
# 造 5000 客户 / 30000 贷款申请（脚本名为历史命名 gen_10w_data.py）
python scripts/gen_10w_data.py

# 造 3000 条严格 PD 训练数据（60 逾期 × 25 + 60 正常 × 25）
python scripts/gen_train_dataset.py --reset

# 训练 XGBoost 违约概率模型
python scripts/train_xgb_model.py

# 回填 ml_score（用训好的模型对历史评估推理回填）
python scripts/backfill_ml_score.py
```

### 6. 启动服务

```bash
python run_app.py
```

启动前自动跑 6 步自检（`.env` / Python 核心依赖 / MySQL 连接 / 数据库初始化 / 8000 端口 / XGBoost 模型），全部通过后启动 uvicorn：

```
============================================================
【启动前自检】
============================================================
  [OK] .env           .env 存在
  [OK] Python 依赖      所有 11 个核心依赖已装
  [OK] MySQL 连接       MySQL root@ecs 可连
  [OK] 数据库初始化         数据库已初始化, risk_rule 有 30 条规则
  [OK] 端口 8000        端口 8000 空闲
  [OK] XGBoost 模型     XGBoost 模型已加载 (317.1 KB)
============================================================
汇总: 6 OK / 0 WARN / 0 FAIL
INFO:     Uvicorn running on http://0.0.0.0:8000
```

打开 **http://localhost:8000/** 即可看到仪表盘。🎉

> 💡 **全流程一键命令**：也可用 `python scripts/one_command.py` 一键跑完「初始化 → 业务数据 → PD 训练数据 → 训练 → 回填 → 启动指引」6 步，支持 `--skip-init` / `--skip-train` / `--only-start` 分段跳过。

---

## 项目结构

```text
AI_Risk/
├── app/                      # 核心代码（5 层架构）
│   ├── api.py                # FastAPI 应用入口与路由注册
│   ├── config.py             # 全局配置（DB / LLM / XGB 开关 / ML 权重阈值）
│   ├── database.py           # 异步 SQLAlchemy 会话管理
│   ├── models.py             # 业务 + 风控模型汇总
│   ├── models_business.py    # 17 张业务表模型
│   ├── models_risk.py        # 9 张风控表模型（包含事件/黑名单类型 ENUM）
│   ├── schemas.py            # Pydantic 请求/响应模型
│   ├── scheduler.py          # 案件超时关闭 + 告警检查后台调度
│   ├── logging_config.py     # 统一日志配置（stdout + 文件轮转）
│   ├── engine/               # 风控核心引擎
│   │   ├── decision.py       # 7 步 process_event 决策流水线 + 双轨融合
│   │   ├── feature.py        # 25 维特征计算（cust_/loan_/dev_）
│   │   ├── rule_engine.py    # 30 条规则匹配引擎
│   │   ├── ml_model.py       # XGBoost 加载/预测（自动降级）
│   │   └── xgb_model.json    # 训练产物（模型文件）
│   ├── agent/                # AI Agent
│   │   ├── chat.py           # Agent 对话（流式）
│   │   └── tools.py          # 8 个 LangChain @tool
│   ├── routers/              # /api 路由（rules/blacklist/cases/agent/...）
│   └── service/              # 业务服务（案件状态机、黑名单、告警等）
├── scripts/                  # 运维/训练脚本
│   ├── run_app.py¹           # ① 一键启动入口（含 6 步自检）
│   ├── init_db.py            # 数据库初始化 / --drop 重建
│   ├── gen_10w_data.py       # 造业务数据（--users/--loans/--batch）
│   ├── gen_train_dataset.py  # 造 3000 条严格 PD 训练数据
│   ├── train_xgb_model.py    # 训练 XGBoost（PD 违约概率）
│   ├── train_demo_model.py   # 教学场景合成训练（无需真实 DB）
│   ├── backfill_ml_score.py  # 回填 ml_score
│   ├── gen_risk_data.py      # 造风控评估数据（--balance-pos 正例控制）
│   ├── gen_risk_data_with_dates.py  # 带日期范围造数（仪表盘趋势）
│   ├── one_command.py        # 6 步全流程一键命令
│   ├── migrate_2026_08_07.py # 老环境升级迁移
│   └── main.py               # 直接启动（跳过自检，开发用）
├── sql/                      # DDL / 初始化 / 迁移 SQL
├── templates/                # J2 前端模板
├── static/                   # 静态资源（CSS/JS）
├── tests/                    # 362 个自动化测试
├── docker/                   # Dockerfile + docker-compose.yml + nginx.conf + .env.example
├── uv/                       # uv 环境管理（pyproject.toml + uv.lock）
└── requirements.txt
```

> ¹ 注意：一键启动入口是 **`run_app.py`**（项目根目录），不是 `_run.py`。

> 目录速记：代码 `app/` · 脚本 `scripts/` · SQL `sql/` · 文档 `docs/` · 测试 `tests/` · 部署 `docker/`。

---

## 核心设计

### 双轨决策流程

```
                 ┌──────────────────────────────────────────────┐
  入参(event) ──▶ │  process_event() 7 步决策流水线              │
                 │  ① 事件清洗/补全  ② 查 25 维特征              │
                 │  ③ 规则引擎匹配  ④ XGBoost 违约概率           │
                 │  ⑤ 双轨融合打分  ⑥ 黑名单命中检查             │
                 │  ⑦ 落地评估/特征/案件 + 触发告警              │
                 └──────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
             规则引擎（30 条）               XGBoost（PD 概率）
             R101-R604 6 大分类             sigmoid 校准转风险分
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                    双轨融合 final = α·规则分 + β·ML分
                      规则一票否决 → 直接拒绝 / 人工审核
                                    │
                                    ▼
                         决策落库 + 案件 + 告警
```

### 25 维特征（`cust_14 + loan_8 + dev_3`）

| 维度 | 数量 | 前缀 | 示例 |
|---|---|---|---|
| 客户维度 | 14 | `cust_` | 历史申请数、近 30/7 天申请数、累计金额、负债率、逾期次数/率 |
| 申请维度 | 8 | `loan_` | 申请金额、期限、负债比、收入比、是否夜间申请 |
| 设备维度 | 3 | `dev_` | 设备数量、是否新设备、跨省标志 |

> 特征顺序固定于 `app/engine/ml_model.py::FEATURE_COLUMNS`，与 `feature.py` 计算 key 一一对应，改特征必须同步测试 `test_bank_features.py`。

### 30 条预置规则（R101-R604）

| 场景 | 数量 | 典型规则 |
|---|---:|---|
| 欺诈风险 | 6 | R101（30 天 ≥8 笔多头借贷）/ R102（≥8 笔，一票否决） |
| 信用风险 | 6 | R201（负债率 ≥50%）/ R202（≥80%，一票否决） |
| 反洗钱 | 4 | R301（频繁大额 / 拆分交易） |
| 账户风险 | 5 | R401（异常登录 / 新设备 / 密码尝试） |
| 贷后风险 | 5 | R501（历史逾期率 ≥30%）/ R502（≥50%，一票否决） |
| 合规风险 | 4 | R601（黑名单 / 制裁名单 / 敏感行业） |

规则 JSON 结构（支持嵌套 `and` / `or`）：

```json
{
  "and": [
    {"field": "loan_debt_ratio", "op": ">=", "value": 0.5},
    {"field": "cust_total_loans", "op": ">=", "value": 5}
  ]
}
```

- `field`：25 维特征名（`cust_` / `loan_` / `dev_` 前缀）
- `op`：`>` `>=` `<` `<=` `==` `!=` `in` `not_in` `between`

### PD 违约概率模型

- **标签**：客户逾期事实（`overdue_record` → 1 违约 / 0 履约）
- **阈值**：`ML_PASS_THRESHOLD=0.30` / `ML_MARK_THRESHOLD=0.60` / `ML_REVIEW_THRESHOLD=0.80`
- **双轨权重**：`ML_WEIGHT_RULE=0.5`（α）+ `ML_WEIGHT_XGB=0.5`（β），α+β=1
- **sigmoid 校准**：`risk_score = 100 * (1 - exp(-3 * prob))`，0.1→26 / 0.3→59 / 0.5→78 / 0.7→90，修复量纲错配
- **训练优化**：80/20 stratify 拆分、早停 10 轮、`scale_pos_weight` 上限防过拟合、样本 <1250 打 WARNING、最佳 F1 阈值

### 4 类事件映射

| 事件 | 说明 | 黑名单类型 |
|---|---|---|
| 贷款申请 | 主事件，source_id = 申请 ID | 客户 / 手机号 / 设备 |
| 放款 | 放款环节复审 | 客户 / 手机号 / 设备 |
| 还款 | 还款记录关联补全 | 客户 |
| 客户投诉 | 投诉记录 | 客户 / 手机号 / 地址 / 设备 |

17 张业务表 + 9 张风控表（含案件、告警、黑名单、评估、特征、规则命中日志）。

---

## 使用说明

### 页面入口

| URL | 用途 |
|---|---|
| http://localhost:8000/ | 仪表盘（趋势 / 规则命中 / 待审案件） |
| http://localhost:8000/docs | Swagger API 文档 |
| http://localhost:8000/api/agent/chat | AI 对话（流式） |
| http://localhost:8000/api/risk/check | 实时风控检查（POST） |
| http://localhost:8000/api/alerts/check | 手动触发告警（POST） |

### API 示例

实时风控检查：

```bash
curl -X POST http://localhost:8000/api/risk/check \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "贷款申请",
    "source_id": "LN_TEST_001",
    "user_id": "C00001"
  }'
```

规则增删查：

```bash
# 创建规则
curl -X POST http://localhost:8000/api/rules \
  -H "Content-Type: application/json" \
  -d '{
    "rule_id": "R605",
    "rule_name": "我的新规则",
    "rule_category": "信用风险",
    "event_type": "贷款申请",
    "rule_condition": {"field": "loan_debt_ratio", "op": ">=", "value": 0.5},
    "risk_level": "高",
    "risk_score": 60,
    "action": "人工审核",
    "priority": 50,
    "description": "负债率 ≥50% 触发审核"
  }'

# 列表
curl http://localhost:8000/api/rules
```

> 也可通过 SQL `INSERT INTO risk_rule` 直接加规则；软删用 `UPDATE risk_rule SET deleted_at = NOW() WHERE rule_id = 'R605'`，业务查询统一 `WHERE deleted_at IS NULL`。

### Agent 对话

打开 Agent 页面，用自然语言提问，例如：

- “帮我查一下 C00001 这个客户在当前贷款申请上的风险结论”
- “今天有哪些待审核案件？”
- “近 7 天风险趋势怎么样？”
- “把手机号 138xxxx 拉进黑名单”

Agent 会通过 8 个 LangChain `@tool` 自动查询并给出可追溯的结论。

---

## 测试

共 **362 个**自动化测试（`pytest collect` 实测值），覆盖风控全链路：

```bash
# 全部 362 个（约 3 分钟）
pytest tests/

# 详细输出
pytest tests/ -v

# 单个文件
pytest tests/test_risk_decision.py -v

# 端到端 DDL 同步检查（需真实 DB）
DDL_CHECK_ENABLED=1 pytest tests/test_ddl_sync.py -v
```

主要覆盖点：

- **DDL 同步**：SQLAlchemy 反射真实库，对比 `models_risk.py` 字段定义（默认 skip，需真实 DB）；
- **特征一致性**：特征命名、25 维对齐、特征计算正确性；
- **规则引擎**：30 条规则匹配、嵌套条件、优先级、软删、一票否决；
- **决策引擎**：7 步流水线、双轨融合、sigmoid 校准、标签正确性；
- **训练质量验收**：假收敛检测、最佳 F1 阈值、训练数据纯度/正例比例/时间跨度校验、`--balance-pos` 正例控制；
- **Agent**：8 工具会话锁、银行化领域对话；
- **调度与日志**：案件超时关闭、调度器回归、统一日志 13 个、通用分页 9 个、左侧固定布局 10 个、一键启动 preflight 16 个、校验去重 15 个等。

---

## 部署

### Docker 一键部署（推荐）

Docker 相关文件统一放在 `docker/` 子目录（`Dockerfile` + `docker-compose.yml` + `nginx.conf` + `.env.example`）。

```bash
# 1. 进入 docker/ 并复制环境变量模板
cd docker
cp .env.example .env
# 编辑 .env：改 MYSQL_ROOT_PASSWORD + LLM_API_KEY

# 2. 启动（MySQL + FastAPI app + Nginx 三个容器）
docker compose up -d

# 3. 查看启动日志
docker compose logs -f app

# 4. 首次部署：跑数据初始化
docker compose exec app python scripts/init_db.py --yes

# 5. 灌业务数据 + 训练 XGBoost
docker compose exec app python scripts/gen_10w_data.py
docker compose exec app python scripts/gen_risk_data_with_dates.py --days 7 --per-day 20
docker compose exec app python scripts/train_xgb_model.py

# 6. 访问
# http://localhost        ← Nginx 80 → app 8000
# http://localhost/docs    ← Swagger API
```

### Docker 架构

```
┌─ Nginx (80/443) ─┐
│  反代 + 静态文件  │
└────────┬─────────┘
         ↓
┌─ FastAPI app (gunicorn 4 workers) ─────┐
│  lifespan 启/停后台调度器               │
│  • 案件超时自动关闭 (24h)              │
│  • 告警自动检查 (15 分钟)              │
│  • XGBoost 自动加载 + 双轨融合         │
└────────┬────────────────────────────────┘
         ↓
┌─ MySQL 8.0 (utf8mb4) ──────────────────┐
│  26 张表 (17 业务 + 9 风控)           │
│  init SQL 自动跑 (entrypoint-initdb.d) │
└────────────────────────────────────────┘
```

### 关键配置（.env）

```env
# 调度
CASE_TIMEOUT_HOURS=24            # 待审案件超 24h 自动关闭
ALERT_SCHEDULER_INTERVAL_MIN=15  # 告警检查 15 分钟一次（0 = 关闭）

# 告警阈值
ALERT_PENDING_CASE_THRESHOLD=50  # 待审核积压告警阈值
ALERT_RULE_HIT_RATE_MIN=5.0      # 命中率下限 (%)
ALERT_BLACKLIST_HIT_RATE_MAX=30.0# 撞黑率上限 (%)
ALERT_CHECK_WINDOW_HOURS=1       # 时间窗口（小时）

# 阿里云百炼 LLM
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx  # 必填，否则 Agent 功能降级
```

### 老环境升级

```bash
# 不重置数据，只补字段 + ENUM 扩展（幂等）
docker compose exec app python scripts/migrate_2026_08_07.py
# 会自动补 6 字段 + 1 索引 + 1 ENUM (AUTO_REJECT_CASE / AUTO_CLOSE_CASE)
```

### 传统部署（不用 Docker）

```bash
# 1. 系统装 Python 3.11 + MySQL 8.0
# 2. 创建数据库 + 跑 init SQL
mysql -u root -p < sql/init_all.sql

# 3. pip install
pip install -r requirements.txt

# 4. gunicorn 启动（4 workers）
gunicorn scripts.main:app \
    -w 4 -k uvicorn.workers.UvicornWorker \
    -b 0.0.0.0:8000 \
    --timeout 120

# 5. 配 systemd 开机自启
# /etc/systemd/system/ai-risk.service
[Unit]
Description=AI Risk System
After=network.target mysql.service

[Service]
Type=simple
User=app
WorkingDirectory=/opt/ai-risk
ExecStart=/usr/local/bin/gunicorn scripts.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 日志管理

`app/logging_config.py` 统一配置：业务 logger + uvicorn 全部走 stdout + `logs/app.log`，50 MB 自动轮转保留 5 份。

| 输出目标 | 路径 | 适用场景 |
|---|---|---|
| **stdout** | 终端 / 容器 | 开发实时看，Docker 自动捕获 |
| **logs/app.log** | `项目根/logs/app.log` | 事后排查、历史归档、自动轮转 |

- 轮转：`MAX_BYTES = 50 MB`，`BACKUP_COUNT = 5`，满 50MB 重命名为 `app.log.1`，最多占 250 MB；
- 覆盖 logger：业务 logger（14 个文件）+ `uvicorn.access`（每个请求一行）+ `uvicorn.error`（异常 traceback）；
- 启动方式：`python run_app.py` 用 `LOGGING_CONFIG` 启动 uvicorn；容器化部署亦然。

```bash
# Linux / Mac
tail -f logs/app.log

# 看最新一个 HTTP 请求
grep "uvicorn.access" logs/app.log | tail -1

# 看 ERROR
grep "ERROR" logs/app.log

# 打印完整配置（demo）
python app/logging_config.py
```

---

## 常见问题 FAQ

**Q1: 启动报 “ModuleNotFoundError: No module named 'app'”**
A: 在项目根目录运行，或先 `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))`。

**Q2: 启动报 “aiomysql 跨 event loop 时 Event loop is closed”**
A: `database.py::get_db_async` 已处理（显式 `try/finally + 显式 close`）。若仍遇到，重启服务。

**Q3: XGBoost 加载失败 / 模型没训练**
A: 看 `app/engine/ml_model.py::_schedule_load()`。若 `xgb_model.json` 不存在，自动走纯规则（不影响业务）。要训练跑 `python scripts/train_xgb_model.py`。

**Q4: 训练时报 “没有评估数据，先跑几次 /api/risk/check”**
A: 先造评估数据：
```bash
python scripts/gen_risk_data.py --count 200
python scripts/gen_risk_data.py --count 200 --balance-pos   # 正例占比 20%+
python scripts/train_xgb_model.py
```

**Q5: 训练样本不足 50 条**
A: 多造数据（业务表 + 评估数据），建议 200+ 条才有意义。样本 <1250 条时 `ml_model.py` 打 WARNING 但不阻断训练（教学可小样本试跑），生产前须积累到 1250+（25 维 × 50 倍经验值）。

**Q6: 数据库中文乱码**
A: 必须 utf8mb4 字符集。`init_db.py` 已加 `CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci`。老库需 ALTER TABLE 转码。

**Q7: AI Agent 报 LLM 错误**
A: 检查 `.env` 的 `LLM_API_KEY`；阿里云百炼需 OpenAI 兼容接口 `LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`；Qwen-Plus 按输入/输出分别计费。

**Q8: 端口 8000 被占**
A: 改 `scripts/main.py`：
```python
uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
```

**Q9: 软删字段对业务影响**
A: 软删后 `is_enabled=0` + `deleted_at=NOW()`，规则匹配 / 黑名单检查 / 列表查询都加 `WHERE deleted_at IS NULL`。业务看不到软删记录，审计日志永久保留。

**Q10: 告警配置**
A: 见上文「关键配置（.env）」中的 `ALERT_*` 参数。

**Q11: 案件状态机流转错误**
A: 状态机白名单在 `app/service/case.py::_ALLOWED_CASE_TRANSITIONS`：
```
待审核 → 审核中 / 已通过 / 已拒绝 / 已关闭
审核中 → 已通过 / 已拒绝 / 已关闭
已通过 / 已拒绝 / 已关闭 → 终态
```

**Q12: 我改了 `app/engine/feature.py` 加新特征，怎么让 XGBoost 用上？**
A:
1. 在 `compute_*_features` 的 dict 里加新 key；
2. 在 `app/engine/ml_model.py::FEATURE_COLUMNS` 列表里加同名字符串；
3. **重训**：`python scripts/train_xgb_model.py`；
4. **改测试**：确保 `tests/test_xgboost.py::test_feature_columns_align`、`tests/test_bank_features.py` 通过；
5. 启动服务，验证 `is_model_loaded() == True`。

---

## 附录：数据生成与训练参数

### 业务数据生成（`gen_10w_data.py`）

```bash
# 默认规模（5000 客户 / 30000 贷款申请）
python scripts/gen_10w_data.py

# 指定业务规模
python scripts/gen_10w_data.py --users 5000 --loans 30000

# 指定批量插入批次
python scripts/gen_10w_data.py --batch 1000
```

- 参数：`--users`（客户数，默认 5000）/ `--loans`（申请数，默认 30000）/ `--batch`（批量批次，默认 500）

**产出**：每个客户 1-3 个联系信息、1-8 笔贷款申请（平均 3）、每笔 1-36 期分期、10-20% 概率有还款记录、5% 概率有逾期记录（PD 正例）、3% 概率有客户投诉。

**风险画像自动注入**：
- 80% 正常客户；
- 15% 中风险（多头借贷 / 高负债 / 被拒史）；
- 5% 高风险（多头 + 逾期史，PD 违约概率正例）。

### 教学场景训练（`train_demo_model.py`）

不需要真实 DB，纯 numpy 合成训练数据：

```bash
python scripts/train_demo_model.py --n 2000
# 6 种高风险模式 + 1 种正常模式：
#   多头借贷 / 高负债 / 大额申请 / 逾期史 / 夜间高频申请 / 设备异常 (+ 普通)
# 5 秒出结果，val_auc = 1.0（合成数据太干净，教学够用）
```

### 带日期范围造数（`gen_risk_data_with_dates.py`）

```bash
python scripts/gen_risk_data_with_dates.py                 # 近 7 天，每天随机 1~30 条
python scripts/gen_risk_data_with_dates.py --per-day 15    # 每天固定 15 条
python scripts/gen_risk_data_with_dates.py --days 30 --per-day 10   # 近 30 天
python scripts/gen_risk_data_with_dates.py --days 7 --per-day 20 --clean  # 清空重建
```

### 训练建模参数

| 参数 | 默认值 | 含义 |
|---|---|---|
| `XGB_TEST_SIZE` | 0.2 | 验证集比例（stratify 拆分） |
| `XGB_EARLY_STOPPING_ROUNDS` | 10 | 验证集 logloss 连续 N 轮不升就停 |
| `XGB_MIN_SAMPLES` | 1250 | 最小训练样本数 = 25 维 × 50 倍 |
| `XGB_MAX_SCALE_POS_WEIGHT` | 10.0 | scale_pos_weight 上限，防过拟合 |
| `ML_WEIGHT_RULE` | 0.5 | 规则分权重（α） |
| `ML_WEIGHT_XGB` | 0.5 | XGBoost 分权重（β，α+β=1） |
| `ML_PASS_THRESHOLD` | 0.30 | ML 通过阈值 |
| `ML_MARK_THRESHOLD` | 0.60 | ML 标记阈值 |
| `ML_REVIEW_THRESHOLD` | 0.80 | ML 人工审核阈值 |

> 所有参数在 `app/config.py` 配置，`.env` 可覆盖。模型自动加载：import `app.engine.ml_model` 时按 `XGB_ENABLED` + 模型文件存在性自动调度，无需手动加载。

---

## 一句话总结

```bash
pip install -r requirements.txt
python scripts/init_db.py
python scripts/gen_10w_data.py
python scripts/train_xgb_model.py
python run_app.py          # 一键启动（含 6 步自检）
# → http://localhost:8000
```

---

## License

[MIT](LICENSE)