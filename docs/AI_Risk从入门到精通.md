# AI_Risk 电商风控系统：从入门到精通

> 本文档是一份系统的学习路线图 + 源码导读，目标：**零基础的同学 3 天内能把项目跑起来并讲清楚，1 周内能应对面试**。
> 配套资料：`README.md`（启动文档）、`AGENTS.md`（工程约定与陷阱）、`docs/启动运行指南.md`（从零到跑通实录）。

---

## 目录

**第一部分 · 入门**
- 1. 项目是什么
- 2. 核心概念速览（先建立心智模型）
- 3. 技术栈全景

**第二部分 · 上手**
- 4. 20 分钟把项目跑起来
- 5. 页面走查：第一次点击每个功能
- 6. 常用命令速查

**第三部分 · 架构**
- 7. 五层架构总览
- 8. 一次风控请求的完整生命周期
- 9. 后端源码地图（每个文件干什么）

**第四部分 · 前端**
- 10. 前端架构：Jinja2 服务端渲染 + fetch API
- 11. 页面 ↔ 接口对照表

**第五部分 · 精通（核心算法精讲）**
- 12. 规则引擎：JSON 条件表达式求值
- 13. 25 维特征工程
- 14. 评分公式与四档决策
- 15. 双轨融合 + sigmoid 校准（面试核心）
- 16. 一票否决（硬规则兜底）
- 17. XGBoost 训练全流程
- 18. 案件状态机
- 19. 告警与审计体系
- 20. AI Agent 集成

**第六部分 · 工程实践**
- 21. 安全设计
- 22. 性能优化
- 23. 日志与可观测性
- 24. 测试体系

**第七部分 · 学习路线图**
- 25. 三周学习计划
- 26. 自检清单

**第八部分 · 面试**
- 27. 高频面试题与答题框架
- 28. 项目讲解话术（30 秒 / 3 分钟 / 10 分钟）

---

# 第一部分 · 入门

## 1. 项目是什么

**AI_Risk 电商风控系统**是一个模拟真实电商平台的**实时风险控制系统**：当用户"下单、支付、申请售后、发起物流投诉"时，系统实时评估风险，决定**通过 / 标记 / 人工审核 / 拒绝**。

它是一个**教学项目**（不是生产级系统），但麻雀虽小五脏俱全，覆盖了工业风控的核心命题：

| 命题 | 本项目答案 |
|---|---|
| 怎么快速拦截已知风险？ | 规则引擎（30 条规则，可配置、可解释） |
| 怎么捕捉未知的组合风险？ | XGBoost 机器学习模型（25 维特征） |
| 规则和模型怎么配合？ | 双轨融合：0.5×规则分 + 0.5×ML 分 |
| 模型会犯错，怎么兜底？ | 一票否决（极高风险规则强制拒绝）+ 纯规则降级 |
| 怎么证明决策可追溯？ | 事件/特征/评估快照落库 + 操作审计日志 |
| 风控自己出问题怎么办？ | 告警体系（积压/命中率突降/撞黑异常） |
| 业务人员怎么用？ | Web 控制台 + AI 对话助手（LangChain Agent） |

**一句话总结**：`FastAPI + MySQL + XGBoost + LangChain` 实现的"规则 + ML 双轨融合"电商风控平台，含完整的 Web 控制台、AI 助手、调度任务、测试与 Docker 部署。

## 2. 核心概念速览

先记住 5 个词，后面全靠它们展开：

1. **事件（Event）**：一次需要风控的业务动作，4 种：`下单 / 支付 / 售后申请 / 物流投诉`
2. **特征（Feature）**：描述用户/订单/地址行为的数值，共 **25 维**
3. **规则（Rule）**：一条 JSON 条件表达式，命中即加分，共 **30 条（R001-R030）**
4. **评估（Assessment）**：一次事件的风控结论（分数 + 等级 + 决策）
5. **案件（Case）**：需要人工介入的评估（人工审核/拒绝才建案，有状态机流转）

决策链路一句话版：

```
事件 → 算 25 维特征 → 规则打分 + ML 打分 → 加权融合 → 四档决策 → 落库/建案
```

## 3. 技术栈全景

| 层次 | 技术 | 作用 |
|---|---|---|
| Web 框架 | FastAPI 0.115 | 异步高性能 API + Swagger 文档 |
| 服务器 | uvicorn 0.34 | ASGI 服务器（开发）/ gunicorn 4 workers（Docker 生产） |
| ORM | SQLAlchemy 2.0 (async) + aiomysql | 全异步数据库访问，26 张表 |
| 数据库 | MySQL 8.0 (utf8mb4) | 业务表 + 风控表分离设计 |
| 配置 | pydantic-settings | `.env` 加载，环境变量可覆盖 |
| 规则引擎 | 自研（纯 Python） | JSON 条件表达式递归求值 |
| 机器学习 | XGBoost 2.1 + scikit-learn | 二分类模型，训练/评估/推理 |
| AI Agent | LangChain + langchain-openai + deepagents | 8 个工具的 DeepAgent（阿里云百炼 qwen-plus） |
| 前端 | Jinja2 + Bootstrap 5 + 原生 JS fetch | 服务端渲染页面 + 轻量交互 |
| 测试 | pytest 8.3 + pytest-asyncio | 329 个测试 |
| 部署 | Docker Compose（Nginx + app + MySQL） | 三容器生产部署 |

**Python 版本必须 3.11–3.12**（`uv/pyproject.toml` 限制 `<3.13`）。

---

# 第二部分 · 上手

## 4. 20 分钟把项目跑起来

### 4.1 准备环境（一次性）

```bash
# 1. 进入项目根目录
cd <项目根目录>  # 例: cd /path/to/ai_risk

# 2. 创建虚拟环境 + 装依赖（推荐 uv，89 个包；pip 也行）
uv venv .venv --python 3.12
uv pip install -r uv/requirements-uv.txt
# 或: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 3. 准备 MySQL 8.0（Docker 方式）
docker run -d --name risk-mysql \
  -e MYSQL_ROOT_PASSWORD=123321 -e MYSQL_DATABASE=ecs -p 3306:3306 \
  mysql:8.0 --character-set-server=utf8mb4 --collation-server=utf8mb4_0900_ai_ci

# 4. 配置 .env（根目录，参考 README 1.3 节）
#    DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME=ecs + LLM_API_KEY（Agent 用，没有也能跑）
```

### 4.2 初始化数据库

```bash
python scripts/init_db.py --yes
# 执行顺序：建库 → 17 张业务表+4100 条数据 → 9 张风控表 → 30 条预置规则
```

> ⚠️ `--drop / --reset` 会**删库重建**，谨慎使用。

### 4.3 一键初始化 + 训练 + 启动（推荐）

项目提供了"一条龙"脚本，从 0 到跑通 6 步：

```bash
python scripts/one_command.py
# 1. init_db.py --reset --yes   建库
# 2. gen_risky_users.py --count 30   造高风险用户样本
# 3. gen_train_dataset.py --reset    造 1500 条训练数据
# 4. train_xgb_model.py             训练 XGBoost → app/engine/xgb_model.json
# 5. backfill_ml_score.py           回填 ml_score
# 6. gen_risk_data_with_dates.py    造带日期的今日业务数据
```

也可以分步执行（更利于理解每一步）：

```bash
python scripts/gen_10w_data.py                          # 可选：造 10w 条大业务数据
python scripts/gen_risk_data_with_dates.py --days 7 --per-day 20   # 造 7 天趋势数据
python scripts/train_xgb_model.py                       # 训练模型
```

### 4.4 启动服务

```bash
python run_app.py
```

启动前自动跑 **6 步自检**（.env / 依赖 / MySQL / 数据库初始化 / 8000 端口 / XGBoost 模型），全 OK 后起 uvicorn：

```
汇总: 6 OK / 0 WARN / 0 FAIL
一切就绪, 启动 uvicorn...
INFO:     Uvicorn running on http://0.0.0.0:8000
```

访问入口：

| URL | 用途 |
|---|---|
| `http://localhost:8000/` | 仪表盘 |
| `http://localhost:8000/docs` | Swagger API 文档（强烈建议先逛这里） |
| `http://localhost:8000/risk-check` | 手动风控检查页面 |
| `http://localhost:8000/chat` | AI 对话 |
| `http://localhost:8000/rules` | 规则管理 |
| `http://localhost:8000/cases` | 案件工作台 |
| `http://localhost:8000/assessments` | 评估历史 |
| `http://localhost:8000/blacklist` | 黑名单 |

## 5. 页面走查（第一次点击）

按这个顺序点一遍，就能建立"系统在干什么"的直观感受：

1. **仪表盘**：看今日评估数、风险分布、7 天趋势、规则命中 TOP——这是系统的"监控大屏"
2. **风险检查**：填 `user_id`（如 `1001`）+ 事件类型 + source_id，提交后看返回的 `final_score / risk_level / decision / triggered_rules / ml_score`
3. **规则管理**：看 30 条规则的 JSON 条件、等级、分值、动作；试新增一条规则（如"单笔 ≥3000 触发人工审核"），再去风险检查触发它
4. **案件工作台**：人工审核/拒绝的评估会生成案件，试试"审核通过/拒绝"
5. **评估历史**：全量评估记录，含 ML 评分（sigmoid 校准后的 0-100 分）
6. **AI 对话**：问它"查一下用户 1001 的风险情况"——体验 Agent 调工具
7. **黑名单**：加一条用户黑名单，再去风险检查，看返回 `blocked_by`

## 6. 常用命令速查

```bash
# 全部在项目根目录执行
python run_app.py                                    # 启动（6 步自检）
python scripts/init_db.py --yes                      # 初始化 DB
python scripts/gen_10w_data.py                       # 造 10w 业务数据
python scripts/gen_risk_data_with_dates.py --days 7  # 造 7 天风控数据
python scripts/train_xgb_model.py                    # 训练 XGBoost
python scripts/backfill_ml_score.py                  # 回填 ML 评分
python -m pytest tests/                              # 跑全部测试（必须用 python -m）
python -m pytest tests/test_risk_decision.py -v      # 跑单个测试文件
python app/engine/decision.py                        # 核心算法 Demo（无需 DB，强烈推荐跑）
python app/engine/feature.py                         # 25 维特征清单 Demo
python app/engine/rule.py                            # 规则引擎 Demo
```

---

# 第三部分 · 架构

## 7. 五层架构总览

```
┌─────────────────────────────────────────────────────────┐
│  前端层  templates/ (Jinja2) + static/app.js + Bootstrap │  ← 页面 & 交互
├─────────────────────────────────────────────────────────┤
│  路由层  app/routers/  10 个 router，30 个接口            │  ← 入站
├─────────────────────────────────────────────────────────┤
│  服务层  app/service/  event / case / alert / validator  │  ← 业务编排
├─────────────────────────────────────────────────────────┤
│  引擎层  app/engine/   rule / feature / decision / ml    │  ← ★ 风控核心
├─────────────────────────────────────────────────────────┤
│  数据层  SQLAlchemy ORM (app/models*.py) + MySQL 26 表   │  ← 存储
└─────────────────────────────────────────────────────────┘
    旁挂：app/agent/（LangChain Agent）· app/scheduler.py（后台调度）· scripts/（CLI）
```

## 8. 一次风控请求的完整生命周期

以"用户 1001 提交一笔 8000 元的订单"为例，调用 `POST /api/risk/check`：

```
前端 risk_check.html
  ↓ fetch('/api/risk/check')
app/routers/risk.py  →  POST /api/risk/check
  ↓ Depends(get_db_async) 注入异步 session
app/service/event.py::process_event（4 步）
  ① validate_risk_check_request      用户存在？订单归属一致？（防越权）
  ② _enrich_request                  按事件类型补全 order_id / receive_id
  ③ _check_all_blacklists            用户>地址>手机号，撞黑直接拒绝（不写库）
  ④ run_risk_check（决策引擎 7 步）
     ├ 1. _build_context + _enrich_receive_id     准备上下文
     ├ 2. _create_event_record                    写 risk_event（evt_xxx）
     ├ 3. _compute_features                       算 25 维特征（查询业务表）
     ├ 4. _save_feature_snapshot                  写 risk_feature（25 行）
     ├ 5. _evaluate_rules                         加载启用规则 → JSON 求值
     ├ 6. _calculate_decision                     规则分 + ML 分 → 融合 → 四档决策
     └ 7. _save_assessment + _maybe_create_case
            + _update_user_profile                写 risk_assessment / risk_case / risk_user_profile
  ↓ 单事务 commit
返回 RiskCheckResponse（final_score / decision / triggered_rules / ml_score / blocked_by）
```

**记住两条主线**：
- 入口主线：`routers → service.event(4步) → engine.decision(7步) → 落库`
- 决策主线：`25 维特征 → 规则命中列表 → max+bonus 规则分 + XGBoost P(拒绝) → sigmoid 校准 → 加权融合 → 四档决策 → veto 兜底`

## 9. 后端源码地图

| 文件 | 职责 | 学习优先级 |
|---|---|---|
| `app/config.py` | 全部配置：DB / 阈值 / LLM / XGBoost / 告警 | ★★★ 先读，理解阈值从哪来 |
| `app/database.py` | 异步引擎 + Session 工厂 + 依赖注入 | ★★ 了解即可 |
| `app/models_business.py` | 17 张业务表 ORM | ★ 用到再查 |
| `app/models_risk.py` | 9 张风控表 ORM（规则/事件/特征/评估/案件/黑名单/画像/日志/告警） | ★★★ |
| `app/schemas.py` | Pydantic 请求/响应模型 | ★★ |
| `app/service/validator.py` | 业务实体校验 + 防越权 | ★★ |
| `app/service/event.py` | **process_event 入口（4 步）** | ★★★ |
| `app/service/case.py` | 案件状态机 + 黑名单 + 超时关案 | ★★★ |
| `app/service/alert.py` | 3 个告警场景 | ★★ |
| `app/service/action_log.py` | 操作审计日志 | ★ |
| `app/engine/rule.py` | **规则引擎：JSON 条件求值** | ★★★ |
| `app/engine/feature.py` | **25 维特征计算** | ★★★ |
| `app/engine/decision.py` | **★ 7 步流水线 + 评分公式 + 双轨融合 + veto** | ★★★★★ |
| `app/engine/ml_model.py` | **XGBoost 加载/推理/训练/兜底** | ★★★★ |
| `app/agent/chat.py` | Agent 会话管理（内存 + 锁） | ★★ |
| `app/agent/tools.py` | 8 个 LangChain @tool | ★★ |
| `app/scheduler.py` | asyncio 调度器（关案 + 告警） | ★★ |
| `app/routers/*.py` | 30 个 API 接口 | ★★ |
| `run_app.py` | 6 步自检 + 启动 | ★ |
| `scripts/*.py` | 初始化/造数据/训练/回填 CLI | ★★ 会用即可 |

---

# 第四部分 · 前端

## 10. 前端架构

**形态**：Jinja2 服务端渲染 + Bootstrap 5 + 原生 JS `fetch`。不是前后端分离，没有 Vue/React。

```
templates/
├── base.html        ← 布局基座：左侧固定 sidebar + 右侧滚动区 + 公共分页组件
├── dashboard.html   ← 仪表盘（fetch /api/dashboard/overview）
├── risk_check.html  ← 风控检查（fetch /api/risk/check）
├── rules.html       ← 规则管理（增删改查 + 启停）
├── cases.html       ← 案件工作台（列表/详情/审核）
├── assessments.html ← 评估历史（列表/详情）
├── chat.html        ← AI 对话（fetch /api/agent/chat）
└── blacklist.html   ← 黑名单管理
static/app.js        ← 公共函数：apiRequest 封装、风险等级 Badge、ML 评分渲染
```

**交互模式**：
1. 页面路由（`app/routers/pages.py`）只负责把模板渲染出来（HTML 骨架）
2. 页面内 JS 用 `fetch` 调后端 JSON API（如 `/api/cases?page=1`）
3. `static/app.js` 提供统一封装：`apiRequest()`、`getRiskBadgeClass()`、`mlProbToRiskScore()`（**前端也实现了 sigmoid 校准**，和 Python 端公式一致，保证显示统一）
4. 分页是统一组件：`{items, total, page, page_size}` 返回结构 + `pagination-bottom` 粘底样式

**改前端的方法**：改页面 → 改 `templates/*.html`；改公共交互 → 改 `static/app.js`；改布局 → 改 `base.html`。

## 11. 页面 ↔ 接口对照表

| 页面 | 调用接口 |
|---|---|
| 仪表盘 `/` | `GET /api/dashboard/overview` |
| 风险检查 `/risk-check` | `POST /api/risk/check` |
| 规则 `/rules` | `GET/POST /api/rules`、`PUT/DELETE /api/rules/{id}`、`PUT /api/rules/{id}/toggle` |
| 案件 `/cases` | `GET /api/cases?status=&page=`、`GET /api/cases/statistics`、`GET /api/cases/{id}`、`POST /api/cases/{id}/review` |
| 评估历史 `/assessments` | `GET /api/assessments?page=`、`GET /api/assessments/{id}` |
| 黑名单 `/blacklist` | `GET/POST /api/blacklist`、`DELETE /api/blacklist/{id}` |
| AI 对话 `/chat` | `POST /api/agent/chat`、`POST /api/agent/clear` |
| （控制台内部） | `GET /api/profile/{user_id}`、`GET /api/alerts`、`POST /api/alerts/check`、`POST /api/alerts/{id}/resolve` |

**全部 30 个接口**（`app/api.py` 汇总）：

- 风控检查 1：`POST /api/risk/check`
- 规则管理 6：`GET /api/rules`、`GET /api/rules/{rule_id}`、`POST /api/rules`、`PUT /api/rules/{rule_id}`、`PUT /api/rules/{rule_id}/toggle`、`DELETE /api/rules/{rule_id}`
- 案件管理 4：`GET /api/cases`、`GET /api/cases/statistics`、`GET /api/cases/{case_id}`、`POST /api/cases/{case_id}/review`
- 黑名单 3：`GET /api/blacklist`、`POST /api/blacklist`、`DELETE /api/blacklist/{blacklist_id}`
- 用户画像 1：`GET /api/profile/{user_id}`
- 仪表盘 1：`GET /api/dashboard/overview`
- AI Agent 2：`POST /api/agent/chat`、`POST /api/agent/clear`
- 告警 3：`POST /api/alerts/check`、`GET /api/alerts`、`POST /api/alerts/{alert_id}/resolve`
- 评估历史 2：`GET /api/assessments`、`GET /api/assessments/{assessment_id}`
- 页面 7：`/`、`/rules`、`/cases`、`/assessments`、`/risk-check`、`/chat`、`/blacklist`

---

# 第五部分 · 精通（核心算法精讲）

## 12. 规则引擎：JSON 条件表达式求值

**文件**：`app/engine/rule.py`

规则是一条 JSON 条件表达式，支持 **9 种比较运算符 + and/or 递归嵌套**：

```json
{ "field": "order_total_amount", "op": ">=", "value": 5000 }
{ "and": [ {"field": "user_refund_rate", "op": ">=", "value": 0.3},
           {"field": "user_total_orders", "op": ">=", "value": 5} ] }
```

**求值逻辑**（`evaluate_condition`）：

```
有 "and" → all(递归求值子条件)
有 "or"  → any(递归求值子条件)
单条件   → features.get(field)，特征缺失 → 未命中；否则 _compare(actual, op, value)
```

**容错设计（面试可讲）**：
- 条件 JSON 解析失败 → 跳过该规则，不影响其他规则
- 特征算不出来（None）→ 条件算"未命中"，不算错
- 未知运算符 → 兜底 False，不中断流程

**规则加载**（`load_enabled_rules`）：只查 `is_enabled=1 AND deleted_at IS NULL`（软删过滤），按 `priority` 降序，支持按事件类型过滤（含"通用"规则对所有事件生效）。

## 13. 25 维特征工程

**文件**：`app/engine/feature.py`

| 维度 | 数量 | 特征 | 含义示例 |
|---|---|---|---|
| 用户 | 14 | `user_total_orders` / `user_orders_7d` / `user_orders_30d` / `user_total_amount` / `user_avg_order_amount` / `user_max_order_amount` / `user_refund_count` / `user_refund_rate` / `user_refund_amount` / `user_postsale_count` / `user_postsale_rate` / `user_cancel_count` / `user_complaint_count` / `user_address_count` | 高频下单、高退款率、多地址 |
| 订单 | 8 | `order_total_amount` / `order_item_count` / `order_sku_count` / `order_discount_amount` / `order_discount_rate` / `order_pay_interval_sec` / `order_is_night` / `order_category_count` | 大额、深夜下单、极速支付、高折扣 |
| 地址 | 3 | `addr_total_count` / `addr_province_count` / `addr_is_new` | 多省份、新地址 |

**关键设计**：
1. **命名前缀即实体类型**：`user_*` → 用户，`order_*` → 订单，其他 → 地址（`_classify_feature_entity` 决定 `risk_feature` 表的 entity_type）
2. **特征顺序固定**：`ml_model.py::FEATURE_COLUMNS` 与 `feature.py` 一一对应，有对齐测试防止特征错位
3. **查询优化**：`user_total_orders` 一次 SQL 查完，复传给平均金额/退款率/售后率 3 个函数（4 次 SQL → 1 次，省 75%）

**加特征的标准流程**（AGENTS.md 陷阱，面试常问）：
```
改 feature.py 特征 dict → 同步 ml_model.py::FEATURE_COLUMNS（保持 25 维）
→ 重训模型 → 跑 tests/test_xgboost.py::test_feature_columns_align_with_feature_module
```

## 14. 评分公式与四档决策

**文件**：`app/engine/decision.py`

**规则分**（`calculate_final_score`）：

```
final_score = max(所有命中规则分) + 3 × (命中数 - 1)     # 上限 100
例：命中 [70]          → 70
    命中 [70,40,20]    → 70 + 3×2 = 76
    命中 [95,80,70]    → 95 + 3×2 = 101 → 100
    命中 []            → 0
```

**四档映射**（阈值在 `app/config.py`，`.env` 可覆盖）：

| 分数 | 等级 | 决策 | 行为 |
|---|---|---|---|
| `< 30` | 低 | 通过 | 放行 |
| `< 60` | 中 | 标记 | 放行但留底 |
| `< 80` | 高 | 人工审核 | 建案件，人工处理 |
| `≥ 80` | 极高 | 拒绝 | 自动拒绝并建"已拒绝"案件 |

## 15. 双轨融合 + sigmoid 校准（★面试核心）

**问题**：XGBoost 输出的是概率 `P(拒绝) ∈ [0,1]`，规则分是 `0-100` 的风险分，**两者量纲不同，不能直接加权平均**。

```
错误做法：ml_score = int(prob × 100)      # 0.7 概率 ≠ 70 风险分（量纲错配）
```

**sigmoid 校准**（`_ml_prob_to_risk_score`，k=3）：

```
risk_score = 100 × (1 - e^(-3p))
校准点：p=0.1→26, p=0.3→59, p=0.5→78, p=0.7→90, p=0.9→97
特性：低概率被压低（避免误报），高概率被推高（强化高风险信号）——指数饱和函数
```

**融合公式**：

```
final_score = α × rule_score + β × ml_score_100
α = ML_WEIGHT_RULE = 0.5，β = ML_WEIGHT_XGB = 0.5（.env 可调，α+β=1）
模型未加载 → final_score = rule_score（纯规则兜底）
```

**效果对比**（rule=60 + ml_prob=0.5）：
- 旧（错误）：`ml=50, final=55` —— 规则分被拉低，风险被低估
- 新（校准后）：`ml=78, final=69` —— 与规则协同增强，正确反映中高风险

## 16. 一票否决（硬规则兜底）

**规则**：任意一条 `risk_level="极高"` 的规则命中（当前 3 条：R002 单笔≥10000 / R007 30天30单 / R015 退款率≥80%）→ 强制拒绝。

**双保险设计**（`_calculate_decision` 内）：

```
① 融合前：rule_score = max(rule_score, 90)     # 把规则分先抬到 90
② 融合后：若 has_veto → decision="拒绝", level="极高",
           final_score = max(final_score, 90)   # 不被 ML 低分推翻
```

**为什么需要**：原实现只把 veto 作用在规则分上，融合平均后可能被降级成"标记"放行（业务事故）。修复后即使 ML 给出 0.05 低分，极高风险规则命中就是拒绝。

## 17. XGBoost 训练全流程

**文件**：`app/engine/ml_model.py` + `scripts/train_xgb_model.py`

### 17.1 建模口径

- 标签二分类：`0=通过/标记，1=人工审核/拒绝`
- 输入：25 维特征，固定顺序 `FEATURE_COLUMNS`（缺失补 0）
- 输出：`predict_proba[:,1]` = P(拒绝)
- ML 独立四档：`P < 0.30 通过 / < 0.60 标记 / < 0.80 人工审核 / ≥ 0.80 拒绝`

### 17.2 训练数据（严格化）

- 普通脚本随机抽样会导致正例 <3%，模型"假收敛"
- 改用 `gen_train_dataset.py`：30 个高风险用户 × 25 条售后 + 30 个普通用户 × 25 条下单 = **1500 条**，正例占比 25%-35%
- 标签来自 30 条规则跑出的 `decision`（规则即标注器）
- `ml_score` 强制置 NULL（干净，避免"未训练模型"垃圾值），训练完用 `backfill_ml_score.py` 回填

### 17.3 训练参数与防过拟合（面试重点）

| 手段 | 参数 | 目的 |
|---|---|---|
| 类别平衡 | `scale_pos_weight = neg/pos`，上限 10 截断 | 防极端不平衡过拟合 |
| 样本拆分 | 80/20 **stratify** 拆分 | 验证集正负比 = 训练集 |
| 早停 | 验证集 AUC/logloss 连续 10 轮不升即停，前 50 轮强制不早停 | 防过拟合 |
| 正则化 | L1(α=0.1) + L2(λ=1.0) + min_child_weight=3 + gamma=0 | 防噪声 |
| 采样 | subsample=0.8 + colsample_bytree=0.8 | 随机森林式抗过拟合 |
| 树复杂度 | max_depth=6, eta=0.1 | 中等复杂度 |

### 17.4 质量验收门禁（防假收敛）

```
样本量 < 1250        → WARNING（25 维 × 50 倍经验值）
正例比例 < 15% / >60% → WARNING（可能假收敛 / 标签噪声）
scale_pos_weight > 10 → 截断 + WARNING
best_iter < 30        → WARNING（可能假收敛）
val_auc < 0.70        → WARNING（模型无效）
val_f1  < 0.50        → WARNING（不平衡下 F1 更敏感）
```

### 17.5 优雅降级（★核心设计）

- 模型文件 `app/engine/xgb_model.json` 不存在 → 自动纯规则模式，业务照常
- import 时自动加载（模块级调度），`is_model_loaded()` 供决策层判定
- 推理失败 → 兜底返回 `score=0, 决策=通过, is_loaded=True`（不抛异常）

## 18. 案件状态机

**文件**：`app/service/case.py::_ALLOWED_CASE_TRANSITIONS`

```
待审核 ──→ 审核中 / 已通过 / 已拒绝 / 已关闭
审核中 ──→ 已通过 / 已拒绝 / 已关闭
已通过 / 已拒绝 / 已关闭  → 终态（不可再流转）
```

**配套逻辑**：
- **条件建案**：只有决策 = 人工审核/拒绝 才建案；通过/标记不留案件（但 event/feature/assessment 已留底）
- **自动拒绝**：决策=拒绝 的案件直接初始状态"已拒绝"；人工审核才进"待审核"
- **去重建案**：同一 `(source_id, event_type)` + 未结案 → 跳过
- **超时关案**：待审核超过 `CASE_TIMEOUT_HOURS=24h` 自动关闭（调度器执行）
- **案件类别**：命中规则里出现最多的 rule_category（Counter.most_common）

## 19. 告警与审计体系

### 19.1 告警（`app/service/alert.py`，3 个场景）

| 场景 | 指标 | 阈值 | 等级 |
|---|---|---|---|
| 待审核案件积压 | pending_case_count | > 50 | P1/BUSINESS |
| 规则命中率突降（1h 窗口） | rule_hit_rate | < 5% | P2/MODEL |
| 撞黑比例过高（1h 窗口） | blacklist_hit_rate | > 30% | P2/BUSINESS |

- 统一 helper `check_and_alert()`：超阈值写 1 条 `risk_alert`，记录 metric_value / threshold
- 不真发通知（企业微信/钉钉），只写 DB，前端仪表盘查询
- **调度**：`app/scheduler.py` 用 `asyncio.create_task` 轻量循环（每 15 分钟，`ALERT_SCHEDULER_INTERVAL_MIN`），由 FastAPI `lifespan` 启停，优雅停止（标志位 + 最多等 10s），不用 APScheduler/Celery（面试可讲为什么）

### 19.2 审计日志（`app/service/action_log.py`）

- 规则增删改/启停、案件审核、黑名单增删 → 全部写 `risk_action_log`
- 字段：operator（admin/system/ai_agent）、action_type、target、**before_value / after_value**（JSON）、IP
- 价值：可追溯、可追责、符合合规要求（银保监风控审计）——面试话术点

## 20. AI Agent 集成

**文件**：`app/agent/chat.py` + `app/agent/tools.py`

- 框架：`create_deep_agent`（LangChain DeepAgents），模型阿里云百炼 `qwen-plus`，temperature=0.1（业务确定性优先）
- **8 个工具**：

| 工具 | 能力 |
|---|---|
| `risk_check` | 实时风控检查 |
| `query_cases` | 案件查询 |
| `query_user_profile` | 用户画像 |
| `manage_blacklist` | 黑名单增删查 |
| `query_dashboard_stats` | 仪表盘统计 |
| `analyze_risk_trend` | 风险趋势分析 |
| `analyze_rule_effectiveness` | 规则命中效果分析 |
| `query_business_data` | 订单/售后/地址业务查询 |

- 架构模式：业务实现是 `_impl` 函数，`@tool` 包装层只负责 LLM 入参转换 → `_safe_call`（开 session → 调 impl → 异常转字符串）→ `_impl`，**LLM 永远接触不到裸 SQL/DB 对象**
- 会话：全局单例（惰性初始化）、内存级存储（重启丢失）、`asyncio.Lock` 防并发丢消息
- 容错：Agent 执行异常被捕获返回"Agent 执行出错: {e}"，不 500

---

# 第六部分 · 工程实践

## 21. 安全设计

| 风险 | 对策 | 位置 |
|---|---|---|
| 水平越权（拿别人订单调风控） | `ensure_order_belongs_to_user`：订单归属不一致 → 403 | `validator.py` |
| 实体不存在 | 泛型 `ensure_exists` → 404 | `validator.py` |
| 黑名单绕过 | 三层黑名单前置拦截（用户/地址/手机号） | `event.py` |
| 敏感特征外泄 | `RISK_FEATURES_FULL_RETURN` 开关，生产按角色返回空 features | `config.py` |
| 凭据泄露 | 凭据只放 `.env`（pydantic-settings 加载） | `config.py` |
| 数据删除风险 | 规则/黑名单软删（`deleted_at`），所有查询过滤 | `models_risk.py` |

## 22. 性能优化

- **N+1 消除**：案件列表 1 次 `LEFT JOIN` 拿 final_score/risk_level（21 次 SQL → 2 次），`tests/test_case_n_plus_1.py` 回归保障
- **特征查询复用**：total_orders 一次查询供 3 个特征使用（75% SQL 减少）
- **连接池**：`pool_size=10, max_overflow=20, pool_recycle=3600`（避开 MySQL wait_timeout）
- **统一分页**：`{items, total, page, page_size}`，前端粘底分页组件
- **全局单例**：Agent / XGBoost 模型都是进程内单例，避免重复握手/加载

## 23. 日志与可观测性

- 统一配置：`app/logging_config.py`（dictConfig），业务 logger + uvicorn.access 全部进 stdout + `logs/app.log`
- 轮转：`RotatingFileHandler`，50MB × 5 份（最多 250MB）
- 业务代码约定：`logging.getLogger(__name__)`，不另起 logger
- 启动自检：`run_app.py` 6 步自检（.env/依赖/MySQL/初始化/端口/模型），WARN 提示 + FAIL 退出

## 24. 测试体系

- **规模**：329 过 / 1 挂（环境相关：`test_mysql_down` 断言 host 与远程 DB 不符）/ 1 skip（需 `DDL_CHECK_ENABLED=1`）
- **命令**：必须 `python -m pytest tests/`（裸 `pytest` 会 `ModuleNotFoundError: app`）
- **重点测试文件**：

| 文件 | 验证什么 |
|---|---|
| `test_risk_decision.py` | 评分公式、四档映射、veto |
| `test_match_rules.py` / `test_rule_engine.py` | 规则求值 14 种 op + 嵌套 |
| `test_xgboost.py` | 特征列对齐、模型加载/缺失兜底 |
| `test_ml_prob_calibration.py` | sigmoid 校准单调性/非线性 |
| `test_case_state_machine.py` | 状态流转白名单 |
| `test_case_n_plus_1.py` | SQL 次数回归 |
| `test_ddl_sync.py` | ORM 与真实 DDL 反射对比 |
| `test_scheduler.py` / `test_alert.py` | 调度与告警阈值 |
| `test_agent_session_lock.py` | Agent 并发不丢消息 |
| `test_train_data_validation.py` / `test_train_data_purity.py` | 训练数据质量 |

---

# 第七部分 · 学习路线图

## 25. 三周学习计划

### 第 1 周：跑起来 + 看懂主线（约 8 小时）

- [ ] 跑 `scripts/one_command.py` + `run_app.py`，把 7 个页面点一遍
- [ ] 用 `curl` 调 `POST /api/risk/check`，观察返回字段
- [ ] 通读 `app/config.py`（阈值）、`app/schemas.py`（数据结构）
- [ ] 读 `app/engine/decision.py` 的 7 步流水线注释 + 跑 `python app/engine/decision.py` Demo
- [ ] 读 `app/service/event.py`（4 步入口）
- [ ] 交付物：能画出"事件 → 特征 → 规则 → 融合 → 决策 → 落库"流程图

### 第 2 周：吃透算法 + 动手改（约 12 小时）

- [ ] 精读 `app/engine/ml_model.py`：训练参数、早停、scale_pos_weight、质量门禁
- [ ] 精读 `app/engine/feature.py`：25 维特征，跑 `python app/engine/feature.py`
- [ ] 精读 `app/engine/rule.py`：JSON 求值，跑 Demo
- [ ] 读 `app/service/case.py`：状态机 + 超时关案 + 黑名单
- [ ] 动手改 1 个功能：新增一条规则（API/SQL 两种方式）并触发验证
- [ ] 动手改 1 个 Bug 场景：把 `XGB_ENABLED=False` 验证纯规则降级
- [ ] 跑 `python -m pytest tests/test_risk_decision.py -v` 看核心测试
- [ ] 交付物：能徒手写出 `_ml_prob_to_risk_score` 和评分公式

### 第 3 周：工程视角 + 面试演练（约 10 小时）

- [ ] 读 `app/scheduler.py` / `app/service/alert.py`：调度与告警
- [ ] 读 `app/agent/tools.py`：8 个工具 + `_safe_call` 模式
- [ ] 读 `docker/`：compose 架构（Nginx → gunicorn → MySQL）
- [ ] 对照第 8 部分"面试篇"逐题自答，每题写 1-2 分钟口述稿
- [ ] 录一遍 3 分钟项目讲解，听回放修正
- [ ] 交付物：30 秒 / 3 分钟 / 10 分钟三版讲解稿

## 26. 自检清单

**基础层（必须全对）**：
- 4 种事件类型？25 维特征分几类？30 条规则几大类？
- 四档决策阈值（30/60/80）？多规则加分公式？veto 最低分（90）？
- 双轨融合公式？sigmoid 校准公式和 4 个校准点？
- 模型文件缺失时系统行为？（纯规则降级，业务不中断）

**进阶层**：
- 加一个特征要动哪 4 个地方？（feature.py / FEATURE_COLUMNS / 重训 / 对齐测试）
- 案件在什么决策下才会建？状态机有哪些合法流转？
- 黑名单检查优先级？撞黑为什么不写库？
- 训练数据怎么保证正例比例？（gen_train_dataset.py / --balance-pos）
- scale_pos_weight 为什么要截断？stratify 拆分解决什么？

**工程层**：
- 防越权怎么实现？（订单归属 403）
- 怎么消除案件列表 N+1？（1 次 LEFT JOIN）
- 告警 3 个场景和阈值？调度器用什么实现、怎么优雅停止？
- 操作审计怎么做的？（before/after JSON）
- 前端为什么也有 sigmoid 校准？（显示口径统一）

---

# 第八部分 · 面试

## 27. 高频面试题与答题框架

### Q1：你的系统怎么判定一笔订单是风险订单？（必考）

**答**（按流水线走）：
> 入口是 `POST /api/risk/check`。先做业务校验（用户存在、订单归属一致，防越权），再查三层黑名单（用户/地址/手机号，命中直接拒绝）。然后进入决策引擎：先算 25 维特征（用户 14 + 订单 8 + 地址 3），拿特征去匹配 30 条规则（JSON 条件求值），得到规则分 = 最高规则分 + 3×额外命中数；同时 XGBoost 输出 P(拒绝)，经 sigmoid 校准成 0-100 的 ML 分；最后 0.5/0.5 加权融合，按 30/60/80 四档映射成 通过/标记/人工审核/拒绝。人工审核和拒绝会建案件，全程事件/特征/评估落库可审计。

### Q2：为什么要"规则 + ML"双轨，只用一种不行吗？（必考）

> 规则可解释、可快速上线、冷启动就能用，但只能覆盖已知模式（比如单笔≥5000）。ML 能捕捉特征组合的复杂模式（比如"高退款率 + 深夜 + 新地址 + 大额"这种规则写不出来的组合），泛化能力强。但 ML 是黑盒、依赖训练数据、有冷启动问题。所以双轨：规则兜底保证业务底线，ML 增强识别能力，加权融合取两者之长。

### Q3：规则分和 ML 分都是 0-100，直接加权平均有什么坑？（进阶必考）

> 量纲问题。XGBoost 输出的是概率 P(拒绝)∈[0,1]，直接 ×100 当风险分是"伪转换"：0.7 概率意味着"有 70% 概率拒绝"，不等于"风险分 70"。直接平均会把规则分拉低，比如规则 60 + 概率 0.5 → 旧算法 final=55，把中高风险判成低风险。我改用 sigmoid 校准 `100×(1-e^(-3p))`：低概率压低（0.3→59）避免误报，高概率推高（0.7→90）强化高风险信号，让 ML 分和规则分语义对齐后再融合。

### Q4：模型会出错，怎么保证业务底线？（必考）

> 三个层次：① **一票否决**：risk_level="极高"的规则命中（单笔≥1 万、30 天 30 单、退款率≥80%）→ 融合前后双重校验，强制拒绝 + 分数抬到 90，ML 低分推不翻；② **优雅降级**：模型文件缺失/加载失败 → 自动纯规则模式，业务不中断；③ **质量门禁**：训练时 val_auc<0.7、F1<0.5、正例比例异常都会告警，不让烂模型上线。

### Q5：类别不平衡怎么处理？（ML 必考）

> 风控场景"通过"远多于"拒绝"，XGBoost 默认会偏向多数类。我做了四件事：① `scale_pos_weight = neg/pos` 加权，上限 10 截断防过拟合；② 80/20 stratify 拆分，保证验证集正负比和训练集一致，评估才可信；③ 造数据阶段用 `gen_train_dataset.py` 严格控制正例 25%-35%（规则即标注器）；④ 监控 AUC + F1 双指标（logloss 在极度不平衡下会假收敛）。

### Q6：系统上线后怎么知道风控自己出了问题？（工程必考）

> 三场景告警：待审核案件积压 >50（业务堵了）、规则命中率突降 <5%（规则失效或被绕过）、撞黑比例 >30%（黑名单异常）。用 asyncio 轻量调度器每 15 分钟跑一轮（不用 Celery 是因为任务简单、不想引入重依赖），配合操作审计日志（before/after JSON）和统一日志轮转，能快速定位。

### Q7：性能上做过什么优化？

> ① 案件列表 N+1 → 1 次 LEFT JOIN 联表查，20 条/页从 21 次 SQL 降到 2 次，还有测试回归；② 特征计算复用：user_total_orders 一次查询供 3 个特征，SQL 减少 75%；③ 连接池 pool_size=10/max_overflow=20/pool_recycle=3600；④ 模型和 Agent 全局单例，避免重复加载/握手。

### Q8：Agent 是怎么接的？LLM 会不会乱操作数据库？

> 用 LangChain DeepAgents 接阿里云百炼 qwen-plus，8 个工具覆盖风控检查/案件/画像/黑名单/统计/业务查询。关键设计是 `_impl` + `_safe_call` 两层：`@tool` 只做入参转换，业务逻辑在 `_impl` 里用受控的 ORM 查询，异常统一转字符串返回给 LLM，LLM 永远拿不到裸 DB 对象，从架构上杜绝 SQL 注入和越权操作。

## 28. 项目讲解话术

### 30 秒版（电梯演讲）

> 我做一个电商风控系统：用户在平台下单/支付/售后时，系统实时计算 25 维特征（用户行为、订单、地址），用 30 条可配置规则 + XGBoost 模型双轨打分，加权融合后四档决策：通过、标记、人工审核、拒绝。人工审核/拒绝自动建案件走状态机流转，全程审计留痕，配 AI 对话助手、告警监控和 Docker 部署，329 个测试。

### 3 分钟版

> （30 秒版 + 以下 2 个深度点）
> **最有挑战的是双轨融合**：ML 输出概率、规则输出分数，量纲不同。我做了 sigmoid 校准统一量纲，并用一票否决保证极高风险规则不被模型推翻——这是实际踩过的坑：原来只把 veto 作用在规则分上，融合平均后会被降级放行，改成融合前后双重校验。
> **数据质量**：风控天然正负样本不平衡，我通过 scale_pos_weight 截断、stratify 拆分、规则标注器造平衡数据、AUC+F1 质量门禁四层保障，模型文件缺失时自动降级纯规则，业务不中断。

### 10 分钟版

> 按"业务 → 架构 → 算法 → 工程 → 演进"五段讲：
> 1. 业务：4 种事件、四档决策、案件闭环
> 2. 架构：五层（前端/路由/服务/引擎/数据）+ 请求生命周期图
> 3. 算法：规则引擎 JSON 求值 → 25 维特征 → 评分公式 → sigmoid 校准融合 → veto
> 4. 工程：安全（防越权/黑名单/软删）、性能（N+1/特征复用）、可观测（日志/告警/审计）、测试
> 5. 演进：如果重构，我会加 Redis 缓存特征（大促场景）、规则热更新、实时特征流、模型 A/B 实验、可视化监控大盘

---

> **最后提醒**：仓库只有一个 git commit（"提交信息"），面试别主动展开"迭代过程"；但代码里大量 `【Px-Sx 修复】` 注释是最好的"踩坑复盘"素材（量纲错配、veto 被拉低、N+1、脚本 GBK 乱码等），讲成"我在开发中遇到并解决的问题"更有说服力。
