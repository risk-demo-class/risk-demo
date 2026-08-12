# Medical Risk AI · 医疗智能风控系统

本项目是本地运行的教学型医疗行业风控系统，复用参考项目的技术组织方式，使用 Python 3.11、uv、FastAPI、SQLAlchemy Async、MySQL、Jinja2 与 XGBoost。系统覆盖挂号、退号、处方和医保结算四类事件，提供规则决策、模型融合、案件审核、医疗黑名单、只读 AI 助手、告警与审计。

> 重要声明：本系统仅用于教学、演示和医疗风控辅助，不提供诊断、治疗或用药建议，不替代医生、药师、医保审核人员作出最终决定。项目数据全部为固定种子生成的合成数据，不得导入真实个人医疗信息。

## 已实现能力

- 8 张合成医疗业务表 + 9 张风控核心表，异步 MySQL 数据层。
- 4 类医疗事件、25 维同源训练/推理特征、MR001–MR016 医疗规则。
- 四档决策：通过、标记、人工审核、拒绝；极高风险一票否决。
- 7 类医疗主体黑名单，命中时以 MR016 进入完整审计链路。
- XGBoost 二分类、分层训练/校准/验证、Platt 概率校准、规则模型融合。
- 仪表盘、风险检查、规则、案件、评估、黑名单、AI 助手、告警审计页面。
- 只读 AI 助手；无 LLM Key 时仍可查询本地聚合数据。
- 案件积压、风险命中率、医生处方金额、医院申报金额聚合告警。
- 规则、案件和黑名单变更审计；幂等初始化、启动自检和测试。
- 登录、注册、退出、修改密码和签名会话；密码使用 Argon2 摘要保存。
- admin/reviewer/analyst/viewer 四类角色，以及用户新增、角色调整、启停和密码重置。
- 规则人工新增/软删除、案件指派/重新审核、评估证据详情和患者管理。

## 技术结构

```text
AI_Medical_Risk/
├── app/
│   ├── agent/                 # 只读 AI 风控助手
│   ├── engine/                # 25 维特征、规则、决策、XGBoost、训练采集
│   ├── routers/               # REST API 与 Jinja2 页面
│   ├── service/               # 事件校验、编排、告警
│   ├── models_business.py     # 8 张医疗业务表
│   └── models_risk.py         # 9 张风控核心表
├── scripts/                   # 初始化、造数、训练、告警、自检、启动、演示
├── sql/                       # MySQL 8 DDL
├── templates/                 # 医疗管理端页面
├── static/                    # 原生 CSS / JavaScript
├── tests/
├── 1-医疗风控产品需求.md
├── P0-实施报告.md
├── P2-实施报告.md
├── P3-交付报告.md
└── P4-升级报告.md
```

分层保持为 `Router → Service → Engine → Model`。事件、25 维特征快照、规则命中、模型概率、最终评估、案件和画像在同一决策事务内处理；异常时回滚。

## 从零启动

环境要求：Python 3.11、uv、本地 MySQL 8.x。

```powershell
# 1. 安装锁定依赖
uv sync

# 2. 准备本地配置；只在 .env 中填写密码或 Key
Copy-Item .env.example .env

# 3. 幂等创建 ai_risk_medical 和 18 张表（不会删除已有库/表）
#    同时创建默认超级用户 admin / admin，数据库只保存密码摘要
uv run python scripts/init_db.py --yes

# 4. 初始化 15 条数据库规则；MR016 为运行时黑名单规则
uv run python scripts/init_rules.py

# 5. 生成固定种子的完全合成数据
uv run python scripts/gen_business_data.py

# 6. 从业务表实时计算 25 维特征并训练模型
uv run python scripts/train_xgb_model.py

# 7. 启动前只读自检并启动服务
uv run python scripts/start.py
```

浏览器打开：

- 管理端：<http://127.0.0.1:8000/dashboard>
- 登录：<http://127.0.0.1:8000/login>
- 患者管理：<http://127.0.0.1:8000/patients>
- 风险检查：<http://127.0.0.1:8000/risk-check>
- AI 助手：<http://127.0.0.1:8000/assistant>
- 告警与审计：<http://127.0.0.1:8000/system>
- OpenAPI：<http://127.0.0.1:8000/docs>

默认首次登录账户为 `admin / admin`。这是本地初始化账户，建议登录后在“用户与账户”页面修改密码。新注册账户默认是 `viewer` 只读角色。

从 P3 版本的 17 张表现有数据库升级时，先运行非破坏性迁移：

```powershell
uv run python scripts/migrate_p4_auth.py
```

迁移只新增用户表并扩展审计枚举，不删除业务数据，且会拒绝作用于参考项目的 `ecs` 数据库。

若仅需检查环境，运行：

```powershell
uv run python scripts/startup_check.py
```

模型文件与元数据保存在 `app/engine/xgb_model.json`、`app/engine/xgb_model.meta.json`，属于本地生成物并被 `.gitignore` 忽略。没有模型或模型损坏时，系统自动使用纯规则决策。

## 配置

所有配置集中在 `app/config.py`，由 `.env` 覆盖。`.env`、密码和 LLM Key 不进入源码或文档。

常用配置：

```dotenv
DB_NAME=ai_risk_medical
APP_HOST=127.0.0.1
APP_PORT=8000
ALERT_SCHEDULER_ENABLED=true
ALERT_INTERVAL_SECONDS=300
LLM_API_KEY=
```

`LLM_API_KEY` 为空时，规则、XGBoost、告警和全部业务页面照常运行；助手使用本地只读模板回答。配置 OpenAI 兼容接口后，助手只把当前问题所需的脱敏聚合上下文交给模型，并保留安全声明。

## 模型说明

训练样本来自本地合成医疗业务表，每条样本都调用线上同一份 `compute_all_features`。标签是“需人工审核或拒绝规则命中”的教学型规则弱监督标签。最终标签、规则 ID、规则命中结果均不进入 25 维模型特征。

默认拆分：60% 训练、20% 独立概率校准、20% 最终验证，全部使用 stratified split。当前合成数据验收结果：

- 样本 975，正例 324，负例 651，正例比例 33.23%。
- 验证 AUC 1.000，验证 F1 1.000，最佳阈值 0.35。
- 指标达到 PRD 的 AUC ≥ 0.70、F1 ≥ 0.50。

高分源自可重复的合成风险模式和规则弱监督标签，不代表模型已经具备真实医疗场景泛化能力。真实项目需要独立人工标签、时间外验证、漂移监控、公平性评估和合规审查。

## 决策与安全边界

模型可用时，规则分与校准后的模型概率按配置权重融合。系统另外保留两道安全保护：

1. 规则动作下限：模型低概率不能把明确的“标记/人工审核/拒绝”规则降到更低动作。
2. 一票否决：任何极高风险规则在融合后仍强制为极高风险、拒绝，最低 90 分。

AI 助手只读，主动拦截凭据/敏感原文请求、系统写操作请求以及诊断/治疗/用药建议。它不能修改规则、案件、黑名单、处方或结算。

## 告警、审计与手工任务

服务启动后按 `.env` 间隔执行聚合告警，也可手工执行：

```powershell
uv run python scripts/run_alert_checks.py
```

同一指标存在待处理告警时只更新数值，不重复创建；恢复正常后自动标记解决。规则启停、案件审核、黑名单新增/恢复/软删除均写 `risk_action_log`，日志不记录黑名单值原文。

## 5–8 分钟演示建议

1. 使用 `admin / admin` 登录，打开仪表盘，说明 18 张表、25 维特征与规则/模型双轨状态。
2. 在风险检查选择 `医保结算 / CLM0000001`，展示 MR001、MR002、模型概率和拒绝结果。
3. 切换到评估历史与案件审核，说明同事务审计和未结案件去重。
4. 展示规则页中的 MR016 运行时规则与医疗黑名单掩码。
5. 在 AI 助手询问“PAT000001 近期风险摘要”，再尝试医疗建议问题展示安全拦截。
6. 打开告警与审计，展示聚合告警和变更追踪。

服务已启动时，可运行只读烟雾演示；加参数才会新增一次评估：

```powershell
uv run python scripts/demo_smoke.py
uv run python scripts/demo_smoke.py --with-risk-check
```

## 测试

```powershell
# 单元与无数据库回归；真实 MySQL 测试默认明确跳过
uv run pytest -q

# 显式执行真实 MySQL 集成测试
$env:RUN_MYSQL_TESTS="1"
uv run pytest tests/test_mysql_integration.py -q
```

当前验收：`37 passed, 6 skipped`；显式 MySQL 集成测试 `6 passed`。浏览器验收覆盖登录、仪表盘跳转、患者、规则新增入口、案件指派/重审、评估详情、AI 思考状态和用户管理，控制台无错误。

## 登录与角色权限

| 角色 | 主要权限 |
|---|---|
| `admin` | 全部功能、规则管理、用户管理 |
| `reviewer` | 查看数据、风险检查、案件指派与审核 |
| `analyst` | 查看数据、风险检查、黑名单和告警处理 |
| `viewer` | 只读查询、评估详情和 AI 助手 |

所有 API 除健康检查、登录和注册外都要求有效会话。规则、案件、黑名单和用户写操作由后端再次校验角色，不能只靠隐藏页面按钮绕过权限。

## 数据与合规声明

- 姓名仅为合成掩码；身份证、医保卡、手机号和设备仅保存 SHA-256 合成摘要。
- API、页面和审计日志不还原敏感标识原文；黑名单值仅展示掩码。
- SQL 使用 ORM/参数化查询，数据库名称接受白名单校验。
- 项目仅在教学层面对齐《个人信息保护法》《数据安全法》《网络安全法》和医疗数据管理原则，不声称通过正式认证。
- 初始化脚本不提供删库能力，也不会修改参考项目的 `ecs` 数据库。
