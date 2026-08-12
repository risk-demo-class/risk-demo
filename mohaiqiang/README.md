# 物流风控系统 AI_Risk

面向快递/快运/跨境物流企业的风控系统：以“寄件人-运单-地址”为核心，覆盖寄件、揽收、中转、派送、签收、投诉、理赔、代收货款、跨境报关全链路，采用“规则引擎 + XGBoost 双轨融合”完成风险识别、决策、案件处置、审计与告警。

## 技术栈

- Python 3.11
- FastAPI + Uvicorn
- SQLAlchemy 2.0（异步）+ aiomysql + MySQL 8
- XGBoost + scikit-learn
- LangChain / DeepAgents（AI Agent）
- Pydantic 2 + Jinja2 + Bootstrap 5 + Chart.js
- pytest

## 目录结构

```text
app/
  engine/         规则引擎、特征工程、XGBoost、决策流水线
  service/        事件编排、校验、案件、黑名单、告警、审计
  routers/        API 路由
  agent/          AI Agent 工具集
  models_logistics.py   12 张物流业务表 ORM
  models_risk.py         9 张风控表 ORM
  schemas.py             请求/响应模型
scripts/          数据库初始化、造数、训练、回填、一条龙
sql/              DDL 与预置规则
templates/        前端页面
static/           前端静态资源
tests/            测试
docker/           生产部署（Docker Compose + nginx）
uv/               uv 依赖锁定与复现
学习/             物流风控讲解说明、业务说明等文档
```

## 核心能力

- 12 张物流业务表 + 9 张风控表
- 30 维物流特征（寄件人 20 + 运单 6 + 地址 4）
- 24 条预置业务规则（R001-R024）
- 规则 + XGBoost 双轨融合，含一票否决与 sigmoid 校准
- 案件状态机、审核拉黑、操作审计、告警监控
- 后台调度：案件超时自动关闭 + 告警周期检查（asyncio，无需额外中间件）
- 启动前 6 项自检：.env / 依赖 / MySQL / 建库 / 端口 / XGBoost 模型
- AI Agent 8 个工具，支持自然语言查询
- 完整造数链路：业务数据 → 高风险样本 → 评估数据 → 训练集 → 模型训练

## 数据库

### 物流业务表（12 张）

| 表 | 说明 |
|---|---|
| logistics_customer_account | 月结客户/结算账户 |
| logistics_sender | 寄件人（实名） |
| logistics_recipient | 收件人（实名） |
| logistics_address | 收件地址（偏远/临时/共用） |
| logistics_operator | 网点/快递员 |
| logistics_waybill | 运单主表 |
| logistics_event_record | 物流事件流水 |
| logistics_customs_info | 跨境报关 |
| logistics_cod_settlement | 代收货款结算 |
| logistics_claim | 理赔 |
| logistics_complaint_record | 投诉 |
| logistics_abnormal_record | 异常件 |

### 风控表（9 张）

| 表 | 说明 |
|---|---|
| risk_rule | 规则配置 |
| risk_event | 风控事件审计 |
| risk_feature | 特征快照 |
| risk_assessment | 评估结果 |
| risk_case | 风险案件 |
| risk_blacklist | 黑名单 |
| risk_user_profile | 寄件人风险画像 |
| risk_action_log | 操作审计 |
| risk_alert | 风控告警 |

## 特征体系（30 维）

代码位于 `app/engine/feature.py`：

- `compute_sender_features`：寄件人 20 维（寄件量、凌晨揽收、危险品、COD、实名、投诉/理赔/异常、跨境、地址异常、账户风险）
- `compute_waybill_features`：运单 6 维（申报价值、重量、价值重量比、危险品、跨境、状态风险）
- `compute_address_features`：地址 4 维（偏远、临时、共用数、使用次数）
- `compute_all_features`：合并为 30 维，顺序与 `ml_model.FEATURE_COLUMNS` 一致

完整 30 维清单与逐项含义见 [学习/物流风控讲解说明.md](学习/物流风控讲解说明.md) 的 3.3 节。

## 规则体系（24 条）

规则存储在 `risk_rule`，JSON 条件表达式支持 `> >= < <= == != in not_in between` 及 `and/or` 嵌套。

| 类别 | 规则 |
|---|---|
| 实名风险 | R001 未实名、R002 核验多次失败 |
| 寄件行为风险 | R003 近30天高频、R004 近7天高频、R005 凌晨揽收、R006 累计寄件量极大、R017 投诉多、R018 理赔多、R019 异常件多、R022 保价占比高 |
| 危险品风险 | R007 危险品件数偏多、R008 危险品件数极高、R024 危险品+跨境 |
| 跨境风险 | R009 跨境寄件偏多、R010 价值重量比异常、R021 高价值占比高 |
| 代收货款风险 | R011 COD总额偏大、R012 COD拒收率偏高、R013 COD拒收率极高、R020 账户高风险、R023 高频+COD拒收 |
| 地址风险 | R014 偏远地址多、R015 临时地址多、R016 共用地址多 |

评分公式：

```text
rule_score = max(命中规则分) + 3 × (额外命中数)
final_score = 0.5 × rule_score + 0.5 × ml_score(sigmoid 校准)
极高规则命中 → 一票否决，强制拒绝
```

## 快速开始

### 1. 环境准备

```bash
cp docker/.env.example .env
# 修改 .env：DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME、LLM_API_KEY
pip install -r requirements.txt
# 或用 uv 精确复现：uv pip install -r uv/requirements-uv.txt
```

### 2. 初始化数据库

```bash
python scripts/init_db.py --reset --yes
```

自动创建 9 张风控表、12 张物流业务表，并加载 24 条规则。

### 3. 生成数据

```bash
# 基础业务数据（120 张运单及寄件人/收件人/地址/事件等）
python scripts/gen_logistics_data.py --count 120

# 高风险寄件人（30 个，5 种风险模式）
python scripts/gen_logistics_risky_senders.py --count 30

# 风控评估数据（随机抽样跑完整流水线）
python scripts/gen_logistics_risk_data.py --count 200 --balance-pos --clean-ml

# 或按日期范围造评估数据
python scripts/gen_logistics_risk_data_dates.py --days 7 --per-day 20
```

### 4. 训练 XGBoost

```bash
# 造严格训练集（ml_score=NULL）
python scripts/gen_logistics_train_dataset.py --reset

# 训练
python scripts/train_xgb_model.py

# 回填 ml_score
python scripts/backfill_ml_score.py
```

也可用无 DB 的演示训练：

```bash
python scripts/train_demo_model.py --n 2000
```

### 5. 启动服务

```bash
python run_app.py
```

`run_app.py` 启动前自动做 6 项自检（.env / 依赖 / MySQL / 建库 / 端口 / XGBoost 模型）。

访问 `http://localhost:8000`，接口文档见 `http://localhost:8000/docs`。

### 一条龙

```bash
python scripts/one_command.py

# 可选参数
python scripts/one_command.py --skip-init    # 跳过 DB 重置 + 业务数据
python scripts/one_command.py --skip-train   # 跳过评估 + 训练 + 回填
python scripts/one_command.py --only-start   # 只补充近期评估数据
```

## 脚本清单

| 脚本 | 作用 |
|---|---|
| init_db.py | 初始化数据库 |
| main.py | FastAPI 应用入口（由 run_app.py 加载启动） |
| gen_logistics_data.py | 生成基础物流业务数据 |
| gen_logistics_risky_senders.py | 生成高风险寄件人样本 |
| gen_logistics_risk_data.py | 生成随机评估数据 |
| gen_logistics_risk_data_dates.py | 按日期范围生成评估数据 |
| gen_logistics_train_dataset.py | 生成严格训练集 |
| train_xgb_model.py | 训练正式模型 |
| train_demo_model.py | 无 DB 合成数据演示训练 |
| backfill_ml_score.py | 回填 ml_score |
| one_command.py | 一条龙初始化+训练 |

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/risk/check | 风控检查（规则 + XGBoost 双轨） |
| GET | /api/dashboard/overview | 仪表盘汇总 |
| GET | /api/rules | 规则列表 |
| GET | /api/rules/{rule_id} | 规则详情 |
| POST | /api/rules | 新增规则 |
| PUT | /api/rules/{rule_id} | 更新规则 |
| PUT | /api/rules/{rule_id}/toggle | 启停规则 |
| DELETE | /api/rules/{rule_id} | 软删除规则 |
| GET | /api/cases | 案件列表 |
| GET | /api/cases/statistics | 案件统计 |
| GET | /api/cases/{case_id} | 案件详情 |
| POST | /api/cases/{case_id}/review | 案件审核 |
| GET | /api/assessments | 评估历史列表 |
| GET | /api/assessments/{assessment_id} | 评估详情 |
| GET | /api/blacklist | 黑名单列表 |
| POST | /api/blacklist | 新增黑名单 |
| DELETE | /api/blacklist/{blacklist_id} | 删除黑名单 |
| GET | /api/profile/{user_id} | 寄件人画像 |
| POST | /api/agent/chat | AI 助手对话 |
| POST | /api/agent/clear | 清空会话 |
| GET | /api/alerts | 告警列表 |
| POST | /api/alerts/check | 手动触发告警检查 |
| POST | /api/alerts/{alert_id}/resolve | 处理告警 |

## 后台调度

- 案件超时自动关闭：`CASE_TIMEOUT_HOURS`（默认 24 小时，0 关闭）
- 告警周期检查：`ALERT_SCHEDULER_INTERVAL_MIN`（默认 15 分钟，0 关闭）

服务启动时由 `scripts/main.py` 的 lifespan 自动拉起，优雅停机时会等待当前轮次结束。

## 页面

- `/` 仪表盘（今日指标、7 天趋势、规则 TOP5）
- `/rules` 规则管理
- `/cases` 案件管理
- `/assessments` 评估历史
- `/risk-check` 风险检查
- `/chat` AI 助手
- `/blacklist` 黑名单
- `/docs` FastAPI 接口文档（Swagger）

## 验收结果

- 风控检查：RISK003（跨境异常）按“报关清关”事件 → 人工审核，命中 R009/R010/R021/R022
- 规则：24 条启用，样例命中 >= 3
- XGBoost：n=1643，正例 576（35.1%），val_auc=0.9710，val_f1=0.8688
- 核心测试：21 个测试文件、216 个用例（pytest）

## 常见问题

### MySQL 连不上

检查 `.env` 中 `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME`，确认 MySQL 已启动。

### 训练时没有数据

训练脚本只取 `ml_score IS NULL` 的评估；生成评估数据时使用 `--clean-ml`。

### 旧模型特征报错

如果 `app/engine/xgb_model.json` 是旧版 25 维电商模型，删除后重新训练：

```bash
rm app/engine/xgb_model.json
python scripts/train_xgb_model.py
```

### 正例比例太低

使用 `--balance-pos` 优先挑高风险寄件人，或先用 `gen_logistics_train_dataset.py` 生成严格训练集。

### 前端图表重叠

仪表盘已通过 `.dashboard-stat-row` / `.dashboard-chart-row` 和固定图表容器解决，刷新浏览器即可。

### 物流表名冲突

投诉表统一使用 `logistics_complaint_record`，避免与旧电商 `logistics_complaint` 冲突。
