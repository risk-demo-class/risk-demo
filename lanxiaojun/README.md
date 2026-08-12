# AI_Risk — 教育风控系统

> FastAPI + MySQL + XGBoost + LangChain 构建的实时教育风控系统  
> 单次请求经历 7 步决策流水线，毫秒级输出"通过/标记/人工审核/拒绝"四档决策

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化数据库（19 张表 + 30 条规则 + 业务测试数据）
python scripts/init_db.py --reset --yes

# 3. 生成高风险用户（30 个 RISK 用户，5 种风险模式）
python scripts/gen_risky_users.py --count 30

# 4. 生成带日期的评估数据（仪表盘趋势用）
python scripts/gen_risk_data_with_dates.py --days 7 --per-day 50

# 5. 训练 XGBoost 模型（从评估数据训练，保存到 app/engine/xgb_model.json）
python scripts/train_demo_model.py

# 6. 启动服务
python run_app.py
# → http://localhost:8000
```

---

## 系统架构

```
scripts/main.py — FastAPI 入口 (10 个路由注册 + lifespan 调度器)
                    │
     ┌──────────────┼──────────────────┐
     │              │                   │
  pages (Jinja2)  api (10 routers)   agent/chat.py
     │              │             (LangChain + qwen-plus)
     │       service/event.py        agent/tools.py (8 tools)
     │              │
     │       engine/decision.py (7 步决策流水线)
     │     ┌───────┼───────┐
     │     │       │       │
     │  feature   rule  ml_model
     │  (20维)  (30条规则) (XGBoost)
     │     │       │       │
     └─────┴───────┴───────┘
                 │
          database.py (async SQLAlchemy + aiomysql)
                 │
          19 张表 (10 教育业务 + 9 风控)
```

### 六层职责

| 层 | 目录 | 职责 |
|---|------|------|
| 入口 | `scripts/main.py` | FastAPI 创建、路由注册、lifespan |
| 路由 | `app/routers/` (10 模块) | HTTP 端点、Pydantic 校验，无业务逻辑 |
| 服务 | `app/service/` (5 模块) | 编排：校验→补全→黑名单→引擎 |
| 引擎 | `app/engine/` (4 模块) | 20 维教育特征、规则匹配、XGBoost、7 步流水线 |
| Agent | `app/agent/` (2 模块) | LangChain Agent + 8 个工具 |
| 数据 | `app/database.py` + models | 异步 SQLAlchemy，19 个 ORM 表 |

---

## 核心数据流

```
POST /api/risk/check
  → routers/risk.py::api_risk_check()
    → service/event.py::process_event()
      1. 业务实体校验（用户存在、课程归属等）
      2. 自动补全（course_id / device_id）
      3. 黑名单 6 级短路（用户→学号→身份证→设备→支付→手机）
      4. engine/decision.py::run_risk_check()  ← 7 步流水线
```

---

## 核心引擎

### 7 步决策流水线

| 步骤 | 模块 | 说明 |
|------|------|------|
| Step 1 | `_build_context()` | Context Object 模式，准备共享状态 |
| Step 2 | `_create_event_record()` | INSERT risk_event |
| Step 3 | `feature.compute_all_features()` | 20 维教育特征 |
| Step 4 | `_save_feature_snapshot()` | INSERT risk_feature × 20 行 |
| Step 5 | `rule.load_enabled_rules()` + `match_rules()` | JSON 条件求值 |
| Step 6 | `_calculate_decision()` | 评分 + veto + XGBoost 融合 |
| Step 7 | 持久化 | commit assessment/case/profile |

### 评分公式

```
final_score = max(命中规则分) + 3 × (额外命中数), 上限 100
```

### 双轨融合

```
final = 0.5 × 规则分 + 0.5 × XGBoost ML 分
```

- 规则分：确定性、可解释
- ML 分：P(拒绝) → sigmoid 校准 `100 × (1 - e^(-3 × prob))`
- 权重从 `.env` 配置（`ML_WEIGHT_RULE` / `ML_WEIGHT_XGB`）

### 一票否决（Veto）

任何 `risk_level="极高"` 的规则命中 → 强制拒绝  
**ML 分即使为 0 也无法推翻**

### 黑名单短路（6 级）

优先级：用户 > 学号 > 身份证 > 设备指纹 > 支付账号 > 手机号  
命中任意一级 → 直接拒绝，不进引擎

---

## 20 维教育特征

| 维度 | 数量 | 特征示例 |
|------|:----:|---------|
| 用户特征 | 8 | `account_age_days`、`is_real_name`、`total_enrollments`、`refund_rate`、`complaint_count` |
| 课程特征 | 4 | `price`、`category_code`、`total_hours`、`teacher_rating` |
| 订单特征 | 4 | `amount`、`pay_hour`、`multi_course_count`、`payment_account_count` |
| 行为特征 | 4 | `today_minutes`、`active_courses`、`night_session`、`device_count` |

## 30 条预置规则（ER001-ER030）

| 风险等级 | 分值 | 动作 | 示例规则 |
|---------|:----:|------|---------|
| 低 | 0-29 | 通过 | 正常学习行为 |
| 中 | 30-59 | 标记 | 单设备多账号 |
| 高 | 60-79 | 人工审核 | 退费率 > 50% |
| 极高 | 80-100 | 拒绝 | 极端退费率、凌晨大额 |

规则条件支持 9 种运算符（`>` `>=` `<` `<=` `==` `!=` `between` `in` `not_in`）+ `and`/`or` 嵌套。

---

## 网页功能

| 页面 | 路由 | 说明 |
|------|------|------|
| 📊 仪表盘 | `/` | 今日统计 + 7 天趋势 |
| ⚙️ 规则管理 | `/rules` | CRUD + 启停 + 可视化条件编辑 |
| 🔍 风险评估 | `/risk-check` | 手动输入风险检测 |
| 📋 案件管理 | `/cases` | 待审核案件工作台 |
| 📈 评估历史 | `/assessments` | 全量评估审计 |
| 🤖 AI 对话 | `/chat` | LangChain Agent 自然语言查询 |
| 🚫 黑名单 | `/blacklist` | 6 级黑名单管理 |

---

## 项目结构

```
AI_Risk/
├── app/                      # 核心代码
│   ├── engine/               # 决策引擎（特征/规则/ML）
│   ├── service/              # 业务编排（事件/校验/案件/审计）
│   ├── routers/              # HTTP 路由（10 个）
│   ├── agent/                # LangChain 智能体
│   ├── config.py             # 全局配置
│   ├── schemas.py            # Pydantic 模型
│   ├── database.py           # 异步数据库引擎
│   └── models.py             # ORM 表集合
├── scripts/                  # 命令行脚本
├── sql/                      # DDL / 初始化 SQL
├── templates/                # Jinja2 页面模板
├── tests/                    # 测试用例
├── docker/                   # Docker 部署
└── .env                      # 环境变量
```

### 数据库（19 张表）

**教育业务表（10）：** `UserInfo`、`StudentProfile`、`TeacherInfo`、`Course`、`OrderInfo`、`LearningProgress`、`RefundRequest`、`Complaint`、`PaymentAccount`、`DeviceFingerprint`

**风控表（9）：** `risk_rule`、`risk_event`、`risk_feature`、`risk_assessment`、`risk_case`、`risk_blacklist`、`risk_user_profile`、`risk_action_log`、`risk_alert`

---

## 可用脚本

```bash
python scripts/init_db.py --reset --yes           # 初始化 DB（19 表 + 数据 + 规则）
python scripts/gen_risky_users.py --count 30      # 生成高风险用户
python scripts/gen_risk_data_with_dates.py --days 7 --per-day 50  # 评估数据
python scripts/train_xgb_model.py                 # 训练 XGBoost
python scripts/train_demo_model.py                # 教学演示训练
python run_app.py                                 # 一键启动（含 6 步自检）
```

---

## 环境变量（.env）

```ini
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=123321
DB_NAME=ecs

# 阿里云百炼 LLM（Agent 功能用）
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

# ML 权重
ML_WEIGHT_RULE=0.5
ML_WEIGHT_XGB=0.5

# 决策阈值
RISK_PASS_THRESHOLD=30
RISK_MARK_THRESHOLD=60
RISK_REVIEW_THRESHOLD=80
```

---

## AI Agent

- **模型**：阿里云百炼 `qwen-plus`（OpenAI 兼容接口）
- **框架**：LangChain + DeepAgents
- **8 个工具**：风险检查、查询案件、用户画像、黑名单管理、仪表盘统计、趋势查询、规则效果、业务数据

---

## 测试

```bash
pytest tests/ -v                    # 全部测试
pytest tests/test_risk_decision.py  # 决策引擎单测
```

---

## Docker 部署

```bash
cd docker
cp .env.example .env
docker compose up -d
docker compose exec app python scripts/init_db.py --yes
docker compose exec app python scripts/gen_risky_users.py --count 30
docker compose exec app python scripts/gen_risk_data_with_dates.py --days 7 --per-day 50
docker compose exec app python scripts/train_demo_model.py
# → http://localhost
```

---

## 项目介绍

详细的项目介绍文档见 [`PROJECT_INTRO.md`](PROJECT_INTRO.md)，适合 5-10 分钟技术分享。