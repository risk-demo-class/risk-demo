# Spec：在线教育风控系统（一期）

## Objective

在独立目录 `education_risk/` 中实现一个可运行的在线教育风控项目。它参考旧 `AI_Risk` 的分层和七步决策思路，但不导入、不修改其源码或数据库。

一期用户是风控运营人员。系统必须能对课程报名、退费申请、学历认证三个业务事件做风险检查，返回规则命中、风险分、决策，并在高风险时创建案件。

第一实现切片只交付“课程报名”端到端闭环；退费与认证按既有任务清单逐步加入。

## Assumptions

1. 新项目使用 Python、FastAPI、SQLAlchemy 和 SQLite；SQLite 让课堂演示无需 MySQL 服务。
2. 首期使用规则引擎；XGBoost、LLM Agent、页面仪表盘均在规则闭环稳定后再加入。
3. 所有数据为模拟数据，学号、身份证和设备值只使用哈希或脱敏值。
4. 当前运行环境未安装 FastAPI 等依赖，但参考项目的 `.venv` 可用于开发验证；独立项目仍会提供自己的 `requirements.txt`。

## Tech Stack

- Python 3.12+（当前系统为 3.14）
- FastAPI：HTTP API 与自动 Swagger 文档
- SQLAlchemy：数据库访问与参数化查询
- SQLite：本地演示数据库 `education_risk.db`
- pytest：单元和 API 集成测试

## Commands

```powershell
# 创建项目虚拟环境并安装依赖（首次）
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 初始化模拟教育数据
.\.venv\Scripts\python -m app.seed

# 运行测试
.\.venv\Scripts\python -m pytest

# 启动服务
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

开发期可用参考项目的解释器验证：

```powershell
D:\PythonProject\AI_Risk\.venv\Scripts\python.exe -m pytest
```

## Project Structure

```text
education_risk/
  app/
    main.py             FastAPI 应用装配（跨层入口）
    api.py              Router re-export hub
    database.py         SQLite engine、session 与 Base（跨层基础设施）
    schemas.py          API 输入/输出契约
    models_business.py  教育业务 ORM：学员、课程、报名、进度、退费、认证、设备
    models_risk.py      风控 ORM：规则、事件、特征、评估、案件、黑名单、画像
    models.py           Model 层唯一导入入口，重导出业务与风控模型
    routers/            第 1 层：HTTP 路由，只处理请求/响应
      risk.py            POST /api/risk/check → service.process_event
    service/            第 2 层：业务编排与安全校验
      event.py           4 步 process_event 统一入口
      validator.py       事件来源存在性与归属校验
      case.py            黑名单、案件和画像服务
    engine/             第 3 层：可复用风控引擎
      feature.py         教育特征计算
      rule.py            JSON 条件规则匹配
      decision.py        7 步风险决策、评分和持久化
    seed.py             可重复执行的模拟数据初始化
  sql/
    init_business_tables.sql
    init_business_data.sql
    init_risk_tables.sql
    init_risk_data.sql
  tests/
    test_enrollment_flow.py
    test_rule_engine.py
  requirements.txt
  README.md
  .gitignore
```

## Four-Layer Architecture and Decision Flow

本项目必须沿用参考源码的四层职责，不让 Router 直接查询数据库，也不让 Engine 处理 HTTP 细节：

```text
Router 层  →  Service 层  →  Engine 层  →  Model 层
HTTP 请求      业务编排        风控计算       数据实体/持久化
```

### Service 层：4 步 `process_event`

1. `validator` 校验请求、来源存在性与用户归属。
2. `event` 补全报名/设备等关联业务上下文。
3. `case` 前置检查用户、学号、身份证哈希、设备指纹黑名单；命中即短路拒绝。
4. 调用 Engine 的 `run_risk_check`，不在 Service 重复执行评分逻辑。

### Engine 层：7 步 `run_risk_check`

1. 由请求构造风险检查上下文。
2. 写入教育风险事件快照。
3. 计算用户、报名、设备三类教育特征。
4. 写入特征快照。
5. 加载并匹配当前事件适用的教育规则。
6. 汇总规则分数，得到“通过 / 标记 / 人工审核 / 拒绝”。
7. 保存评估，更新用户画像；人工审核或拒绝时创建风险案件。

## API Contract

### `POST /api/risk/check`

请求：

```json
{
  "event_type": "课程报名",
  "source_id": "ENR-RISK-001",
  "user_id": "STU-RISK-01"
}
```

成功响应：

```json
{
  "event_id": "evt_xxx",
  "assessment_id": "asm_xxx",
  "user_id": "STU-RISK-01",
  "final_score": 85,
  "risk_level": "高",
  "decision": "人工审核",
  "triggered_rules": [
    {"rule_id": "EDU-R003", "rule_name": "同课程集中报名", "risk_score": 65}
  ]
}
```

错误统一使用 `{ "detail": "..." }`，其中 404 表示来源不存在，403 表示来源不属于该用户，422 表示输入格式不正确。

## Code Style

- Python 使用类型注解、`snake_case`、小而明确的函数。
- Pydantic 在 API 边界校验输入；内部服务使用已验证对象。
- 数据库访问通过 SQLAlchemy ORM 或参数化语句，禁止字符串拼接 SQL。
- 模型和 API 响应不返回身份证、学号、设备指纹原值。

```python
async def process_event(session: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse:
    await validate_source_ownership(session, request)
    blocked_by = await check_blacklists(session, request)
    if blocked_by:
        return blacklist_reject(request, blocked_by)
    return await run_risk_check(session, request)
```

## Testing Strategy

- 单元测试：规则条件求值、评分映射、黑名单优先级。
- 集成测试：SQLite 测试库上的报名 API、来源归属校验、案件创建。
- 每个新增规则至少有“会命中”和“不会命中”两类测试。
- 首个切片的最低验收：正常报名通过、高风险共享设备报名进入审核、黑名单学号被拒绝。

## Boundaries

- **Always**：每个行为先写测试；输入在 API 边界校验；敏感标识哈希化；运行测试后再提交。
- **Ask first**：新增第三方依赖、切换到 MySQL、接入真实认证/支付/LLM、创建真实用户数据。
- **Never**：修改 `D:\PythonProject\AI_Risk`；提交 `.env` 或真实敏感数据；在 SQL 中拼接请求参数；移除失败测试以使测试通过。

## Success Criteria

1. 独立项目能用 SQLite 初始化教育模拟数据。
2. `/docs` 能调用课程报名风控检查。
3. 正常报名返回“通过”；共享设备批量账号返回“人工审核”或“拒绝”；黑名单返回“拒绝”。
4. 高风险结果保存评估并生成案件。
5. `pytest` 全部通过。

## Out of Scope

首个切片不实现退费、学历认证、XGBoost、LLM Agent、前端页面、登录鉴权和生产部署；它们会在报名闭环验证后逐项加入。
