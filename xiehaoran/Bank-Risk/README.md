# Bank-Risk · 银行风控系统

> 基于 **XGBoost 模型 + 可解释反欺诈规则引擎** 的银行交易风险评分与分级决策原型。
> 覆盖转账、贷款申请、卡片交易、还款、登录五类业务事件，输出 `pass / review / reject / freeze / report` 五级决策。

---

## 目录

- [1. 项目概述](#1-项目概述)
- [2. 环境依赖](#2-环境依赖)
- [3. 安装步骤](#3-安装步骤)
- [4. 使用说明](#4-使用说明)
- [5. 文件结构](#5-文件结构)
- [6. 运行示例](#6-运行示例)
- [7. 结果解读](#7-结果解读)
- [8. 核心设计](#8-核心设计)
- [9. Web 控制台（FastAPI + React）](#9-web-控制台fastapi--react)

---

## 1. 项目概述

银行面临电诈资金链、洗钱、伪冒盗刷、多头借贷四类资金风险。传统"硬编码阈值"规则误杀率高、迭代慢。本项目采用双引擎：

| 引擎 | 职责 | 实现 |
|------|------|------|
| **模型引擎** | 捕捉非线性、弱信号组合，输出 `risk_score ∈ [0,1]` | `XGBoost` 二分类 |
| **规则引擎** | 把分数翻译成可审计、可落地的决策，合规兜底 | `DISPATCH_TABLE` 路由 + `severity` 聚合 |

**样本策略**：离线造数，正例:负例 = 1:4（银行真实欺诈率约 0.2），可通过 `--hard-neg` 开启难负样本增强以防控过拟合。

---

## 2. 环境依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | ≥ 3.9 | 运行环境 |
| xgboost | 3.4.0 | 梯度提升模型 |
| scikit-learn | ≥ 1.0 | 指标 / 训练集切分 |
| pandas / numpy | 最新 | 数据处理 |
| faker | 最新 | 业务数据造数 |
| matplotlib | 最新 | 截图 / 可视化 |
| fastapi / uvicorn | 最新 | Web 控制台接口层（对齐基线 AI_Risk 的 app/routers 模式） |

> 数据来源采用**离线造数**（详见 `1-业务说明.md`）：在内存中 import 造数函数构造 DataFrame 训练，已保留连库（MySQL）扩展点，无需实时连库即可复现。

### Web 控制台额外依赖（Node ≥ 18）

| 依赖 | 版本 | 用途 |
|------|------|------|
| node / npm | ≥ 18 | 前端构建环境 |
| vite | 5 | 前端开发 / 构建 |
| react / react-dom | 18 | SPA 框架 |
| antd | 5 | 企业级金融 UI 组件库 |
| recharts | 2 | 仪表盘与模型评估图表 |
| @ant-design/icons | 5 | 菜单与页面图标 |
| tailwindcss | 3.4 | 样式系统 |

---

## 3. 安装步骤

```bash
# 1. 克隆 / 进入项目根目录
cd d:/codebuddy/Bank-Risk

# 2. 创建虚拟环境（可选）
python -m venv .venv && source .venv/Scripts/activate   # Windows: .venv\Scripts\activate

# 3. 安装依赖
pip install xgboost scikit-learn pandas numpy faker matplotlib
```

---

## 4. 使用说明

### 4.1 生成业务数据（造数）
```bash
python scripts/gen_business_data.py --count 120 --out sql/init_business_data.sql
```
生成 6 张关联表（商户 / 交易流水 / 结算 / 行为日志 / 风险事件 / 关联关系），并保证外键一致。

### 4.2 运行规则引擎演示
```bash
python scripts/demo_rules.py
```
展示 8 条规则对样例交易的命中情况与最终 severity。

### 4.3 训练与评估模型
```bash
# 基线版（无难负增强）
python scripts/train_xgb_model.py

# 难负样本增强版（防控过拟合，推荐）
python scripts/train_xgb_model.py --hard-neg
```
训练指标写入 `scripts/eval_history.jsonl`，模型保存为 `scripts/xgb_fraud_model.json`。

### 4.4 生成讲解截图
```bash
python scripts/make_screenshots.py
```
输出 5 张 PNG 到 `scripts/screenshots/`。

---

## 5. 文件结构

```
Bank-Risk/
├── 1-业务说明.md              # 业务背景与风险场景
├── 5-运行说明.md              # 运行手册与截图说明
├── 6-技术讲解文档.md          # 5–8 分钟讲解稿（含 5 环节）
├── agent_design.md            # LLM 协作方法沉淀
├── README.md                  # 本文件
├── app/
│   ├── config.py              # 事件枚举 / 黑名单 / 阈值 / 决策常量
│   ├── main.py                # [新增] FastAPI 入口：挂载 /api 路由 + 托管 web/dist
│   ├── __main__.py            # [新增] 支持 `python -m app` 启动
│   ├── engine/
│   │   ├── feature.py         # 11 维特征工程（客户/交易/设备等族，归一化到 [0,1]）
│   │   ├── ml_model.py        # XGBoost 模型加载与推理（输出 ml_score）
│   │   └── decision.py        # 7 步决策流水线：校验→事件→特征→快照→规则→决策→持久化
│   ├── models_risk.py         # SQLAlchemy 模型（RiskRule/RiskEvent/RiskAssessment/RiskCase/...），SQLite 持久化
│   ├── database.py            # 引擎与 init_db()（启动时 create_all 建表）
│   ├── service/
│   │   ├── validator.py       # 规则引擎 DISPATCH_TABLE（8 条规则）+ TxnContext
│   │   └── event.py           # 5 类事件分发路由 process_event
│   ├── agent/                 # LLM 风控辅助分析（tools.py 含仪表盘统计等 Agent 工具）
│   └── routers/               # REST 接口层（12 个路由）
│       ├── risk.py            # POST /api/risk 提交事件决策
│       ├── rule.py            # /api/rules 规则增删改查
│       ├── case.py            # /api/cases 案件管理
│       ├── assessment.py      # /api/assessments 评估历史
│       ├── dashboard.py       # /api/dashboard 统计概览
│       ├── blacklist.py       # /api/blacklist 黑名单
│       ├── features.py        # /api/features 特征计算展示
│       ├── model_eval.py      # /api/model-eval 读取 scripts/eval_history.jsonl
│       ├── agent.py           # /api/agent/chat AI 风控助手
│       └── ...                # decision/alert/profile 等
├── web/                       # React + Vite + Ant Design + Recharts 前端工程
│   ├── src/pages/             # 风控仪表盘 / 规则管理 / 案件管理 / 评估历史 / 风险检查 / AI风控助手 / 黑名单 共 7 页
│   └── dist/                  # 构建产物（FastAPI 静态托管）
├── scripts/
│   ├── gen_business_data.py   # Faker 造数（精确 1:4 配比）
│   ├── train_xgb_model.py     # XGBoost 训练 + 难负增强开关
│   ├── demo_rules.py          # 规则引擎命中演示
│   ├── make_screenshots.py    # 5 张讲解截图生成
│   ├── eval_history.jsonl     # 训练评估记录
│   └── screenshots/           # 01_feature ~ 05_eval PNG
└── sql/
    └── init_business_data.sql # 造数导出的初始化 SQL
```

---

## 6. 运行示例

**终端输出示意**：
```text
✅ 已写出初始化数据: sql/init_business_data.sql
   merchant_info: 20 行
   txn_flow: 120 行
   settlement_log: 96 行
   user_behavior_log: 120 行
   risk_event_biz: 28 行
   relation_graph: 112 行

[TRAIN] hard_negative_aug=False
  train_auc=1.000  val_auc=1.000  val_f1=1.000
[TRAIN] hard_negative_aug=True
  train_auc=1.000  val_auc=0.821  val_f1=0.889
```

**规则引擎演示示意**：
```text
交易 T300007 命中: rule_transfer_disperse(sev=3), rule_abnormal_hour(sev=2)
  最终 severity=3 → 决策: review
```

---

## 7. 结果解读

### 7.1 模型指标
| 模式 | train_auc | val_auc | val_f1 | 解读 |
|------|-----------|---------|--------|------|
| BASE | 1.000 | 1.000 | 1.000 | 标签泄漏，虚假完美，**不可信** |
| HARD | 1.000 | **0.821** | **0.889** | 概率化造数 + 难负增强，真实泛化 |

> **重要**：AUC=1.0 并非好事。初版把"是否欺诈"直接写成强特征，模型无需学习即满分（标签泄漏）。修复后 `val_auc=0.821` 才是模型真实能力。`train_auc` 与 `val_auc` 的 gap 即过拟合程度，可由 `--hard-neg` 量化对比。

### 7.2 特征重要性（top）
`geo_deviation`（异地）> `disperse_peer_cnt`（分散对手）> `over_query_freq`（征信密集查询）> `login_brute_freq`（爆破登录），与业务直觉一致。

### 7.3 五级决策语义
| 决策 | 含义 | 触发条件 |
|------|------|----------|
| `pass` | 放行 | 风险低 |
| `review` | 人工复核 | 中风险 / 规则部分命中 |
| `reject` | 拒绝交易 | 高风险 |
| `freeze` | 保护性止付（一票否决） | 命中黑名单（severity=4） |
| `report` | 反诈/AML 报送 | 大额 / 可疑模式 |

---

## 8. 核心设计

- **特征归一化**：所有特征归一到 [0,1]，但保留 `disperse_peer_cnt_raw` 供规则层使用真实对手数。
- **规则热插拔**：`DISPATCH_TABLE` 增删一行即上线/下线一条策略，无需重训模型。
- **模型与规则并行**：规则优先（合规兜底），模型补盲（弱信号组合），融合决策可解释。
- **可复现**：固定 `random.seed(20260811)` 与 `Faker.seed`，训练结果可复现。
- **防过拟合开关**：`--hard-neg` 注入难负样本（边界化）+ 对抗性难正样本（伪装成正常）+ 高斯噪声，量化泛化能力。

详见 `6-技术讲解文档.md`（讲解稿）与 `agent_design.md`（协作方法）。

---

## 9. Web 控制台（FastAPI + React）

为纯后端风控内核补齐的可视化控制台，前端采用 **React 18 + Ant Design 5 + Recharts**，由 Vite 构建后由 FastAPI 同源托管。后端仅做"薄封装"：直接复用 `process_event` 纯函数与现有规则/特征/评估数据，不改动任何算法逻辑。

### 9.1 安装与构建

```bash
# 后端接口层依赖
pip install fastapi uvicorn

# 前端依赖与构建
cd web
npm install
npm run build        # 产物输出 web/dist，由 FastAPI 托管
```

### 9.2 启动

```bash
# 方式一：python -m app（内部用 uvicorn 拉起，端口 8010）
python -m app

# 方式二：直接用 uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8010
```

浏览器访问 **http://127.0.0.1:8010/** 即可使用。

> 开发期（前端未构建时）也可单独跑 Vite：`cd web && npm run dev`，Vite dev server（端口 5173）已配置 `/api` 代理到 FastAPI 8010，无需前后端分离部署。

### 9.3 七大页面

| 页面 | 路由 key | 功能 |
|------|----------|------|
| 风控仪表盘 | `dashboard` | 今日评估/高风险/通过率/待处理统计卡 + 7 天评估趋势双折线图 + 风险等级分布环形图 + 今日决策动作分布条形图 + Top 命中规则 |
| 规则管理 | `rules` | 反欺诈规则增删改查，事件类型以中文显示（转账/贷款申请/登录/卡片交易/还款/通用） |
| 案件管理 | `cases` | 风险案件列表与处置，默认展示"全部状态" |
| 评估历史 | `assessments` | 历史评估记录查询（评分/决策/命中规则） |
| 风险检查 | `risk` | 录入 transfer/loan_apply/card_txn/repay/login 事件，实时返回五级决策 + 命中规则时间线 + 特征向量 |
| AI 风控助手 | `agent` | 基于 LLM 的风控问答与辅助分析 |
| 黑名单 | `blacklist` | 黑名单（账户/设备/IP 等维度）增删查 |

### 9.4 REST 接口（节选）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/risk` | 提交一笔事件决策（event_type + event_data） |
| GET  | `/api/rules` | 规则列表与增删改查 |
| GET  | `/api/cases` | 案件列表（支持 `active_only` / `all` 状态筛选） |
| GET  | `/api/assessments` | 评估历史 |
| GET  | `/api/dashboard` | 仪表盘统计概览 |
| GET  | `/api/blacklist` | 黑名单查询 |
| GET  | `/api/features` | 特征计算展示 |
| GET  | `/api/model-eval` | 读取 `scripts/eval_history.jsonl` 返回 BASE/HARD 对比与特征重要性 |
| POST | `/api/agent/chat` | AI 风控助手对话 |
| GET  | `/api/health` | 健康检查 |

> 架构对齐基线 `AI_Risk` 的 `app/routers` REST 模式；前端调用同源 `/api/*`，由 FastAPI `StaticFiles` 挂载 `web/dist`，避免跨域与独立部署。
