# AI_Risk · 旅游行业风控系统

> 尚硅谷 AI_Risk 行业风控实战项目 —— 在电商版基线上完成的**旅游行业**风控系统。
>
> 复用电商版 9 张风控核心表 + 4 个引擎核心 + 7 步决策流水线；
> 自研旅游业务层：7 张行业表、25 维行业特征、11 条业务规则、XGBoost 模型、行业数据生成。

---

## 1. 项目简介

把“规则 + AI”双保险的风控能力迁移到在线旅游平台（OTA）：

- **业务边界**：机票 / 酒店 / 签证 / 跟团游预订、支付、退改签
- **典型欺诈**：黄牛囤票、拒签刷签、盗用证件代订、0 点突击下单、高频退订套利、黑护照
- **技术栈**：FastAPI + SQLAlchemy 2.x (async) + MySQL 8.0 + XGBoost + LangChain DeepAgents + Jinja2

## 2. 复用边界（红线表）

| 模块 | 动作 |
|---|---|
| 风控核心 9 张表（risk_rule/risk_event/risk_feature/risk_assessment/risk_case/risk_blacklist/risk_user_profile/risk_action_log/risk_alert） | **结构复用**，仅业务枚举值按行业调整 |
| 决策流水线 `process_event` 4 步 + `run_risk_check` 7 步 | **完全复用** |
| 引擎 `decision.py / rule.py / ml_model.py` | **完全复用** |
| 核心契约 `RiskCheckRequest(event_type, source_id, user_id, event_data) → RiskCheckResponse` | **不能改** |
| 行业业务表 `app/models_business.py`（7 张） | **自研** |
| 行业特征 `app/engine/feature.py`（25 维） | **自研** |
| 业务校验 `app/service/validator.py` 派发表 | **自研** |
| 黑名单类型 / 事件类型 / 规则 | **自研** |
| 数据生成 `scripts/gen_business_data.py` 等 | **自研** |

## 3. 行业业务设计

### 3.1 7 张业务表

| 表名 | 核心字段 | 与电商差异 |
|---|---|---|
| `user_info` | 实名状态 / VIP / 账号年龄 / 手机号 | 加“实名状态” |
| `order_info` | 订单类型 / 金额 / 目的地国家 / 出行日期 / 乘客数 | 加“目的地/出行日期/乘客数” |
| `passenger_info` | 证件类型 / 证件号 / 国籍 / 年龄 | 1 订单 N 乘客 |
| `visa_application` | 申请国家 / 拒签历史 / 状态 | 全新表（电商无签证） |
| `booking_flight` | 航班号 / 起降机场 / 舱位 | 全新表 |
| `booking_hotel` | 酒店 / 入住 / 离店 / 可退 | 全新表 |
| `blacklist_extra` | 类型 / 值 / 原因 / 过期时间 | 护照号/签证号/设备指纹 |

### 3.2 业务事件类型（4 种）

```text
预订 / 支付 / 签证申请 / 退改签
```

### 3.3 黑名单类型（7 种）

```text
用户 / 护照号 / 身份证号 / 手机号 / 设备指纹 / IP / 签证号
```

## 4. 特征工程（25 维）

| 特征族 | 数量 | 代表特征 |
|---|---|---|
| 用户 `user_*` | 14 | 历史订单数、退改签次数、近90天拒签次数、30天签证国家数、实名状态、账号年龄 |
| 订单 `order_*` | 7 | 金额、乘客数、出行天数、是否凌晨下单、是否紧急行程、目的地国家数、航班数 |
| 乘客 `pax_*` | 4 | 证件一致性、证件撞黑次数、外籍乘客数、平均年龄 |

特征顺序固定于 `app/engine/ml_model.py::FEATURE_COLUMNS`，训练/推理共用。

## 5. 业务规则（11 条）

| 编号 | 规则 | 等级/动作 |
|---|---|---|
| R001 | 拒签历史拦截（90 天拒签 ≥ 2） | 极高 / 拒绝 |
| R002 | 短期多国签证（30 天 ≥ 3 国） | 高 / 人工审核 |
| R005 | 大额跨境游（> 5 万） | 高 / 人工审核 |
| R008 | 黄牛囤票（订单关联 ≥ 5 航班） | 极高 / 拒绝 |
| R012 | 0 点突击下单（凌晨 + 行程 < 7 天） | 中 / 标记 |
| R018 | 乘客信息不一致（匹配率 < 30%） | 中 / 标记 |
| R020 | 高频退订（退改签 ≥ 3 次） | 高 / 人工审核 |
| R025 | 新用户大单（注册 < 7 天 + 订单 > 1 万） | 中 / 标记 |
| R030 | 黑护照拦截（证件撞黑） | 极高 / 拒绝 |
| R035 | 多人跟团大单（≥ 8 人 + > 2 万） | 高 / 人工审核 |
| R040 | 深夜大额支付（凌晨 + > 3 万） | 高 / 人工审核 |

## 6. 快速开始

### 环境要求

- Python 3.11+（建议 3.12）
- MySQL 8.0（本地或 Docker）
- 依赖：`pip install -r requirements.txt`

### 1) 配置数据库

复制 `.env` 检查：`DB_USER / DB_PASSWORD / DB_NAME=travel_risk`。

### 2) 一键初始化

```bash
python scripts/init_db.py --reset --yes
# 建库建表 + 772 条业务数据 + 11 条规则 + 黑名单种子
```

或手动跑（见 `sql/init_all.sql`）。

### 3) 造评估数据 + 训练模型

```bash
# 方案 A：一条龙（推荐）
python scripts/one_command.py

# 方案 B：分步
python scripts/gen_business_data.py --count 40     # 业务数据（含 7 个 RISK 用户）
python scripts/gen_risk_data.py --count 150 --balance-pos --target-pos-ratio 0.30
python scripts/train_xgb_model.py                  # 输出 val_auc / val_f1 / 特征重要性
python scripts/gen_risk_data_with_dates.py --days 7 --per-day 20
python scripts/gen_risk_data_with_dates.py --days 1 --per-day 50 --live
```

### 4) 启动服务

```bash
python run_app.py
# 浏览器访问 http://localhost:8000
```

### 5) 演示风控检查

```bash
curl -X POST http://localhost:8000/api/risk/check \
  -H "Content-Type: application/json" \
  -d '{"event_type":"预订","source_id":"ORD00001","user_id":"U0001","order_id":"ORD00001"}'
```

高风险用户演示：

| 用户 | 场景 | 期望结果 |
|---|---|---|
| `RISK001` + 大额订单 | 新用户大单 | 命中 R025（标记） |
| `RISK002` + 签证申请 | 拒签刷签 | 命中 R001/R002（拒绝/审核） |
| `RISK003` + 机票订单 | 黄牛囤票 | 命中 R008（拒绝） |
| `RISK004` + 紧急订单 | 0 点突击 | 命中 R012（标记） |
| `RISK005` + 订单 | 证件不一致 | 命中 R018（标记） |
| `RISK006` + 退改签 | 高频退订 | 命中 R020（人工审核） |
| `RISK007` + 订单 | 黑护照 | 前置黑名单拦截（拒绝） |

## 7. XGBoost 训练与评估

```bash
python scripts/train_xgb_model.py
```

验收指标（任务书要求）：

| 指标 | 达标线 |
|---|---|
| val_auc | ≥ 0.70 |
| val_f1 | ≥ 0.50 |
| best_iteration | > 30（防假收敛） |
| acc | > baseline + 2% |

训练数据正例比例建议 25%–35%（`gen_risk_data.py --balance-pos --target-pos-ratio 0.30`）。

## 8. 目录结构

```text
app/
  models_business.py    # 7 张旅游业务表
  models_risk.py        # 9 张风控核心表（枚举按行业调整）
  engine/feature.py     # 25 维行业特征
  engine/decision.py    # 7 步决策流水线（复用）
  engine/rule.py        # JSON 规则引擎（复用）
  engine/ml_model.py    # XGBoost 加载/推理/训练
  service/validator.py  # 事件类型派发表
  service/event.py      # 黑名单前置拦截 + 事件补全
  routers/              # 10 个 API router
  agent/                # 8 个 AI 工具
sql/                    # DDL + 业务数据 + 11 条规则
scripts/                # 初始化 / 造数 / 训练 / 一条龙
templates/ static/      # Web 界面
```

## 9. 测试

```bash
pip install pytest pytest-asyncio httpx
pytest tests/ -q
```

## 10. Vibe Coding 复盘（agent_design.md）

本项目所有业务层代码均由 LLM 协作产出，人工负责：行业判断、schema 评审、规则阈值定夺、跑通验证。
提示词模板与协作流程见 `agent_design.md`。
