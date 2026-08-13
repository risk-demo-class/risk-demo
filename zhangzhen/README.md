# Bank_Risk：银行业智能风控系统

这是一个用于课程演示和答辩的银行业风控原型。项目复用老师电商风控项目的
“事件 → 特征 → 规则/模型 → 决策 → 案件 → 审计”平台骨架，并把行业层改造为
登录、转账、信用卡交易和贷款申请四类银行事件。

> 本项目仅使用虚构、哈希或脱敏数据，不用于真实银行生产决策。

## 当前里程碑

第一阶段“业务与数据骨架”、第二阶段“主决策链路”、第三阶段“管理闭环与页面”
和第四阶段“批量数据、XGBoost 与 AI Agent”已经完成：

- Python 3.11 + uv 项目配置；
- FastAPI 应用工厂和 `/health`、`/healthz`、`/readyz`；
- SQLAlchemy 2.0 全异步数据库连接；
- 8 张银行业务表和 9 张风控核心表 ORM；
- MySQL 初始化脚本与基础自动化测试；
- `.env.example` 与安全的 `.gitignore`。
- `event_type + source_id + user_id` 业务实体、归属和状态校验；
- 八类黑名单前置短路；
- 固定顺序的 25 维银行风险特征；
- 20 条银行 JSON 规则和递归规则引擎；
- 规则评分、XGBoost 可选推理、模型缺失自动降级和一票否决；
- `event → feature → assessment → case/profile` 完整审计链；
- `POST /api/risk/check` 实时风险检查接口；
- 可重复执行的规则与四类业务演示数据初始化脚本。
- 规则 CRUD、启停、条件校验和软删除；
- 案件分页、详情、状态机、人工审核及拒绝时原子加黑；
- 八类黑名单新增、脱敏列表和软删除；
- 评估历史、25维特征详情、客户画像和仪表盘聚合 API；
- 规则、案件和黑名单写操作审计；
- 仪表盘、规则、案件、评估、风险检查、AI助手和黑名单 7 个管理页面；
- 前端统一处理 HTTP 状态与 Content-Type，避免把 500 文本强制解析成 JSON。
- 固定随机种子和截止时间的参数化银行批量数据生成器；
- 异地大额、凌晨密集、新设备大额、多账户归集、多头借贷、共享设备、代理/Tor、正常对照 8 类场景；
- 按业务发生时间调用真实 `process_event` 的历史回放，训练样本仍来自 25 维决策时快照；
- 训练前样本量、正例比例、日期跨度、特征完整性和标签纯度校验；
- XGBoost 时间切分、用户净化、AUC/F1/Precision/Recall、模型保存/加载与缺失降级；
- 实时检查页展示规则分、模型概率、模型换算分、融合权重、融合分和一票否决；
- 8 个带 Pydantic 参数的 Agent 工具、同会话串行锁、查询脱敏和 LLM 故障降级；
- AI 黑名单写操作由后端固定拒绝，风险检查写记录前由工具说明副作用。

后续第五阶段将在此基础上加入告警调度、Docker Compose、部署验收和答辩材料。

完整需求基线见 [docs/银行内风控项目-任务书.md](docs/银行内风控项目-任务书.md)。

## 目录结构

```text
zhangzhen/
├─ app/
│  ├─ routers/             # HTTP 路由
│  ├─ service/             # 校验、上下文补全和黑名单服务
│  ├─ engine/              # 特征、规则、评分、决策、训练和模型加载
│  ├─ agent/               # 8 个受控工具、LLM 编排和会话锁
│  ├─ data_generation.py   # 可复现银行批量数据与八类场景
│  ├─ api.py               # FastAPI 应用工厂
│  ├─ config.py            # 环境变量配置
│  ├─ database.py          # 异步引擎和 Session
│  ├─ models.py            # ORM Base 与公共枚举
│  ├─ models_business.py   # 8 张银行业务表
│  ├─ models_risk.py       # 9 张风控核心表
│  └─ schemas.py           # Pydantic 契约
├─ templates/              # 7 个 Jinja2 管理页面与公共布局
├─ static/                 # 公共 CSS 和 JavaScript
├─ docs/                   # 任务书和设计文档
├─ scripts/
│  ├─ init_db.py           # 初始化 17 张表
│  ├─ init_demo.py         # 初始化规则与小规模演示数据
│  ├─ seed_rules.py        # 幂等写入 20 条银行规则
│  ├─ seed_demo_data.py    # 幂等写入虚构业务样本
│  ├─ gen_bank_data.py     # 参数化生成银行业务事实
│  ├─ gen_risk_data_with_dates.py # 真实跨日期评估回放
│  ├─ gen_train_dataset.py # 训练集纯度校验和 CSV 导出
│  ├─ train_xgb_model.py   # 从数据库快照训练模型
│  ├─ train_demo_model.py  # 无数据库教学兜底模型
│  ├─ backfill_ml_score.py # 可选补充历史 ML 分，不改最终决策
│  ├─ one_command.py       # 非破坏性串联第四阶段流水线
│  └─ main.py              # 本地启动入口
├─ sql/                    # MySQL DDL
├─ tests/                  # 自动化测试
├─ .env.example
├─ pyproject.toml
└─ requirements.txt
```

## 本地环境

在本目录执行：

```powershell
uv python install 3.11
uv sync --extra ml --extra agent --group dev
Copy-Item .env.example .env
```

修改 `.env` 中的本地 MySQL 连接信息。真实密码和 API Key 禁止提交到 Git。

初始化数据库：

```powershell
uv run python scripts/init_db.py
```

如果确定要删除并重建本项目的 17 张表：

```powershell
uv run python scripts/init_db.py --reset --yes
```

第一次运行时，再初始化 20 条规则和演示数据：

```powershell
uv run python scripts/init_demo.py
```

以上初始化脚本可以重复执行；相同主键的数据会被更新，不会无限重复插入。

启动 FastAPI：

```powershell
uv run python scripts/main.py
```

访问：

- 银行风控仪表盘：<http://127.0.0.1:8000/>
- 规则管理：<http://127.0.0.1:8000/rules>
- 案件管理：<http://127.0.0.1:8000/cases>
- 评估历史：<http://127.0.0.1:8000/assessments>
- 实时风险检查：<http://127.0.0.1:8000/risk-check>
- AI 风控助手：<http://127.0.0.1:8000/chat>
- 黑名单：<http://127.0.0.1:8000/blacklist>
- API 文档：<http://127.0.0.1:8000/docs>
- 服务信息：<http://127.0.0.1:8000/health>
- 存活检查：<http://127.0.0.1:8000/healthz>
- 数据库就绪检查：<http://127.0.0.1:8000/readyz>

### 与老师电商项目同时运行时的端口

老师项目的 Docker `ai_risk_app` 也会占用主机 `8000` 端口。如果访问银行项目时
仍看到电商页面，可任选一种方式：

1. 保留共用的 MySQL，只停止老师项目的应用与 Nginx：

   ```powershell
   docker stop ai_risk_app ai_risk_nginx
   uv run python scripts/main.py
   ```

2. 在银行项目 `.env` 中把 `PORT=8000` 改为 `PORT=8010`，然后访问
   <http://127.0.0.1:8010/>。MySQL 仍使用 `127.0.0.1:3306`。

### 在 Swagger 中体验一次风险检查

打开 <http://127.0.0.1:8000/docs>，展开 `POST /api/risk/check`，点击
`Try it out`。正常转账示例：

```json
{
  "event_type": "转账",
  "source_id": "T10001",
  "user_id": "U10001",
  "event_data": {"request_id": "REQ-NORMAL-001"}
}
```

一票否决转账示例：

```json
{
  "event_type": "转账",
  "source_id": "T90001",
  "user_id": "U90001",
  "event_data": {"request_id": "REQ-RISK-001"}
}
```

黑名单收款人示例：

```json
{
  "event_type": "转账",
  "source_id": "T10003",
  "user_id": "U10001",
  "event_data": {"request_id": "REQ-BLACKLIST-001"}
}
```

前两个请求会形成可追溯的事件、特征与评估记录；黑名单请求在特征计算前直接
拒绝，因此不会写入事件和评估表。

## 第四阶段：批量数据与 XGBoost

这一条链路分成两层，不能混为一谈：

1. `gen_bank_data.py` 只写客户、账户、卡、交易、登录、设备、IP、贷款等业务事实；
2. `gen_risk_data_with_dates.py` 读取候选清单，逐条调用真实 `process_event`，由系统生成
   `risk_event → risk_feature → risk_assessment → risk_case/profile`。

默认生成规模是 1,000 客户、20,000 笔目标交易量、500 笔基础贷款和 2,000 个待回放
候选事件；复杂风险场景还会追加构造时间窗口所需的历史行。所有身份信息均为虚构哈希。
同一 `prefix` 已存在时脚本会停止，不会自动删除或覆盖数据。

逐步执行：

```powershell
uv run python scripts/gen_bank_data.py
uv run python scripts/gen_risky_users.py
uv run python scripts/gen_risk_data_with_dates.py
uv run python scripts/gen_train_dataset.py
uv run python scripts/train_xgb_model.py
```

也可以在确认数据库已初始化、20 条规则已写入后执行：

```powershell
uv run python scripts/one_command.py
```

第一次熟悉流程时可先用小规模参数：

```powershell
uv run python scripts/gen_bank_data.py --users 100 --transactions 1000 --candidates 200 --loans 50 --prefix TRY1
uv run python scripts/gen_risk_data_with_dates.py --limit 200
uv run python scripts/gen_train_dataset.py --min-samples 100 --min-span-days 7
uv run python scripts/train_xgb_model.py --min-samples 100 --min-span-days 7
```

默认训练验收要求不少于 1,250 条样本、15%–60% 正例、至少 30 天日期跨度。模型保存为
`app/engine/xgb_model.json`，指标保存为 `app/engine/xgb_model.metrics.json`，两者都属于运行产物，
不会提交 Git。训练后若 Web 服务已经启动，需要重启服务让它加载新模型。删除模型文件后，
系统会自动回到纯规则模式，`POST /api/risk/check` 仍然可用。

教学标签定义：`通过/标记 → 0`，`人工审核/拒绝 → 1`。这些标签来自规则和合成风险模式，
模型主要是在学习教学规则，不代表真实欺诈识别效果。真实银行模型应使用人工审核结论、
欺诈确认、拒付、逾期等事后标签。

## 第四阶段：AI 风控助手

在未提交的 `.env` 中填写大模型配置：

```env
LLM_API_KEY=你的有效Key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
AI_AGENT_TIMEOUT_SECONDS=60
```

重启服务后访问 <http://127.0.0.1:8000/chat>。Agent 提供 8 个工具：

- `risk_check`：执行真实风险检查，会写事件、特征和评估；
- `query_cases`、`query_user_profile`、`query_dashboard_stats`：只读管理查询；
- `analyze_risk_trend`、`analyze_rule_effectiveness`：只读统计分析；
- `query_banking_data`：只读查询，结果先脱敏且不把身份哈希交给模型；
- `manage_blacklist`：只允许 `list/check`，`add/remove` 在后端固定拒绝。

会话只保存在当前进程内，服务重启后丢失。同一会话的并发消息会串行处理，防止历史串话。
LLM Key 缺失、Key 错误、超时或供应商故障时，页面会明确降级，核心风控不受影响。AI 回复
只用于教学辅助分析，不作为真实银行最终决策。

## 测试

```powershell
uv run pytest
```

测试使用独立的 SQLite 内存数据库，不会修改本地 MySQL 数据。当前 51 个测试覆盖表结构、
实体归属、25 维特征、规则运算符、计分、一票否决、黑名单短路、规则软删除、案件
状态机、黑名单脱敏与软删、操作审计、7 个页面、静态资源、管理 HTTP 接口、八类数据模式、
跨日期真实回放、训练纯度、XGBoost 保存加载、8 个 Agent 工具、写权限和会话锁。

## 数据模型边界

银行业务表负责保存决策前的权威事实：客户、账户、卡、交易、贷款、登录、设备和
IP。风控表负责保存规则配置、事件快照、特征快照、评估、案件、黑名单、画像、
操作审计和告警。

核心原则是：请求中的 `event_data` 只能作为补充信息，金额、归属关系、设备和 IP
必须依据 `event_type + source_id + user_id` 从业务表中查询并校验。
