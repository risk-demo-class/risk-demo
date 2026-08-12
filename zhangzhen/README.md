# Bank_Risk：银行业智能风控系统

这是一个用于课程演示和答辩的银行业风控原型。项目复用老师电商风控项目的
“事件 → 特征 → 规则/模型 → 决策 → 案件 → 审计”平台骨架，并把行业层改造为
登录、转账、信用卡交易和贷款申请四类银行事件。

> 本项目仅使用虚构、哈希或脱敏数据，不用于真实银行生产决策。

## 当前里程碑

第一阶段“业务与数据骨架”和第二阶段“主决策链路”已经完成：

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

后续阶段将在此基础上加入案件/黑名单管理闭环、7 个管理页面、模型训练、
AI 助手和 Docker Compose。

完整需求基线见 [docs/银行内风控项目-任务书.md](docs/银行内风控项目-任务书.md)。

## 目录结构

```text
zhangzhen/
├─ app/
│  ├─ routers/             # HTTP 路由
│  ├─ service/             # 校验、上下文补全和黑名单服务
│  ├─ engine/              # 特征、规则、评分和决策引擎
│  ├─ api.py               # FastAPI 应用工厂
│  ├─ config.py            # 环境变量配置
│  ├─ database.py          # 异步引擎和 Session
│  ├─ models.py            # ORM Base 与公共枚举
│  ├─ models_business.py   # 8 张银行业务表
│  ├─ models_risk.py       # 9 张风控核心表
│  └─ schemas.py           # Pydantic 契约
├─ docs/                   # 任务书和设计文档
├─ scripts/
│  ├─ init_db.py           # 初始化 17 张表
│  ├─ init_demo.py         # 初始化规则与小规模演示数据
│  ├─ seed_rules.py        # 幂等写入 20 条银行规则
│  ├─ seed_demo_data.py    # 幂等写入虚构业务样本
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
uv sync --group dev
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

- API 文档：<http://127.0.0.1:8000/docs>
- 服务信息：<http://127.0.0.1:8000/health>
- 存活检查：<http://127.0.0.1:8000/healthz>
- 数据库就绪检查：<http://127.0.0.1:8000/readyz>

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

## 测试

```powershell
uv run pytest
```

测试使用独立的 SQLite 内存数据库，不会修改本地 MySQL 数据。当前测试覆盖表结构、
实体归属、25 维特征、规则运算符、计分、一票否决、黑名单短路、审计链和 HTTP 接口。

## 数据模型边界

银行业务表负责保存决策前的权威事实：客户、账户、卡、交易、贷款、登录、设备和
IP。风控表负责保存规则配置、事件快照、特征快照、评估、案件、黑名单、画像、
操作审计和告警。

核心原则是：请求中的 `event_data` 只能作为补充信息，金额、归属关系、设备和 IP
必须依据 `event_type + source_id + user_id` 从业务表中查询并校验。
