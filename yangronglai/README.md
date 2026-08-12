# BankRisk-AI 银行智能风控平台

面向信用卡、贷款、转账、登录四场景的完整教学/原型项目：

```text
规则兜底 + 模型提准 + 图谱挖团 + Agent 辅助
```

当前版本 `1.0.0`，四层均已接入真实执行链路，不返回伪造分数。

## 能力总览

- 8 张银行业务表、10 张风控审计与运营表。
- 8 条必备银行规则，支持多规则加权聚合、强规则越级和 100 分封顶。
- 5 个 XGBoost 模型：CARD、TRANSFER、LOAN_DEFAULT、LOAN_FRAUD、LOGIN。
- 时间顺序训练/校准/测试切分，使用 Platt 概率校准并保存模型登记信息。
- NetworkX 本地关系图谱开箱即用，支持设备、IP、银行卡、资金网络和欺诈邻居；可同步 Neo4j。
- 规则、模型、图谱三层融合评分，分量结果写入特征审计快照。
- 风控总览、风险检查、规则中心、评估历史、案件工作台、关系图谱、AI 助手页面。
- 8 个 Agent 工具；查询工具直接执行，改变案件状态的请求必须提供人工审批令牌。
- SQLite/MySQL、NetworkX/Neo4j、本地 Agent/外部 LLM 三组双模式。

## 核心流程

```text
业务事件
  → 业务表补全与用户归属校验
  → 场景特征计算
  → 规则层评分
  → 场景模型概率评分
  → 关系图谱团伙评分
  → 三层融合、等级与策略
  → 事件/特征/命中/评估/案件审计
```

## 数据层

| 分层 | 表 |
|---|---|
| 业务表 | `user_info`、`bank_card`、`bank_transaction`、`loan_application`、`login_log`、`device_fingerprint`、`ip_geo_location`、`blacklist_extra` |
| 风控表 | `risk_rule`、`risk_event`、`risk_feature_snapshot`、`risk_rule_hit`、`risk_assessment`、`risk_label`、`risk_case`、`risk_appeal`、`risk_appeal_evidence`、`risk_action_log` |

`risk_label` 只接收人工核验、贷后表现或独立模拟真值，不从规则决策反推。

## 规则评分

规则：R001 异地大额、R002 凌晨密集、R005 新设备大额、R008 多卡归集、R012 信贷申请突击、R018 设备多人共用、R025 IP 代理/Tor、R030 黑卡拦截。

多规则聚合：

```text
规则原始分 = 最高规则分 + 其余规则分数合计 × RULE_ADDITIONAL_WEIGHT
规则最终分 = min(100, 四舍五入后的规则原始分)
```

默认附加权重为 `0.2`。

## 模型层

已生成模型位于 `artifacts/models/`，登记文件为 `registry.json`。当前独立合成测试集指标：

| 模型 | ROC-AUC | PR-AUC | Brier |
|---|---:|---:|---:|
| CARD | 0.735 | 0.376 | 0.103 |
| TRANSFER | 0.816 | 0.476 | 0.077 |
| LOAN_DEFAULT | 0.837 | 0.638 | 0.140 |
| LOAN_FRAUD | 0.762 | 0.439 | 0.081 |
| LOGIN | 0.810 | 0.386 | 0.077 |

贷款场景同时调用违约模型和申请欺诈模型，取较高概率。训练数据由独立潜变量与随机噪声生成，仅用于演示管线；生产前必须替换为经过治理、时间穿越检查和脱敏处理的银行标签数据。

重新训练：

```powershell
.\.venv\Scripts\python.exe -m scripts.train_models --size 3000
```

## 图谱层

默认 `GRAPH_BACKEND=local`，从关系库构建 NetworkX 图，无需 Neo4j。可查询用户 1—3 度关系、连通社区和设备/卡片/资金关系，并产生图谱风险分。

生产部署可设置 `GRAPH_BACKEND=neo4j`，然后调用：

```text
POST /api/graph/sync
```

同步操作只有通过显式 API 请求才执行，不会在启动时清空外部图数据库。

## 三层融合

```text
融合原始分 = 三层最高分 + 其他层分数合计 × FUSION_ADDITIONAL_WEIGHT
最终分 = min(100, 四舍五入后的融合原始分)
```

默认融合附加权重为 `0.15`。强规则的等级和决策只能向上覆盖，不会被模型或图谱降级。

| 最终分 | 等级 | 策略 |
|---:|---|---|
| 0—29 | 低 | 通过 |
| 30—49 | 中 | 标记 |
| 50—79 | 高 | 人工审核并自动建案 |
| 80—100 | 极高 | 拒绝 |

## Agent

默认 `AGENT_MODE=local`，本地工具编排立即可用。支持：风险检查、评估解释、案件查询、客户360、图谱查询、仪表盘统计、规则效果分析、提交审核请求。

切换外部模型：

```text
AGENT_MODE=llm
LLM_API_KEY=...
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
```

LLM 模式使用 OpenAI 兼容的 `/chat/completions` 工具调用协议。`submit_review_request` 的 `approval_token` 必须与密钥系统注入的 `AGENT_APPROVAL_TOKEN` 一致，否则只返回“需要审批”，不会修改案件。

## 本地启动

默认使用 SQLite 和本地图谱：

```powershell
cd D:\projects\bankrisk
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scripts.init_db
.\.venv\Scripts\python.exe run_app.py --check
.\.venv\Scripts\python.exe run_app.py
```

入口：

- `http://localhost:8000/`：总览
- `http://localhost:8000/risk-check`：三层风险检查
- `http://localhost:8000/rules`：规则中心
- `http://localhost:8000/assessments`：评估历史
- `http://localhost:8000/cases`：案件工作台
- `http://localhost:8000/appeal`：客户申诉入口
- `http://localhost:8000/graph`：关系图谱
- `http://localhost:8000/agent`：AI 助手
- `http://localhost:8000/docs`：Swagger
- `http://localhost:8000/api/readiness`：完整就绪检查

常用运维命令：

```powershell
.\.venv\Scripts\python.exe -m scripts.db_status
.\.venv\Scripts\python.exe -m pytest -q
```

## 日志与审计

平台使用 JSON Lines 结构化日志，并通过同一个 `request_id` 关联访问日志、接口响应、风险事件和决策日志：

- `logs/bankrisk.log`：应用启动、依赖状态和系统异常。
- `logs/access.log`：请求方法、路由模板、HTTP 状态、耗时和结果分类。
- `logs/risk_decision.log`：规则/模型/图谱分数、版本、最终等级与策略结果。
- `logs/alerts.log`：ERROR/CRITICAL 告警；配置 `ALERT_WEBHOOK_URL` 后同步到告警平台。

日志按 UTC 自然日轮转，默认保留 30 天。`user_id`、`source_id`、设备、银行卡和 IP 等标识不记录原值，统一使用 HMAC 伪匿名引用。结果分类明确区分：

- `BUSINESS_PASS`：业务通过。
- `RISK_FLAGGED / RISK_REVIEW_REQUIRED / RISK_POLICY_REJECTED`：风控策略正常执行。
- `VALIDATION_ERROR`：请求参数或业务字段校验失败。
- `SYSTEM_ERROR`：平台异常，进入告警日志和可选 webhook。

生产环境必须通过密钥系统注入随机 `LOG_PSEUDONYM_KEY`，并配置日志采集、访问控制和不可篡改存储。

## 客户申诉与内部复议

当最终决策为“拒绝”时，风险检查响应的 `appeal` 字段会返回申诉期限、客户端页面、提交 API 和限时签名凭证。凭证只绑定 `assessment_id`，不携带客户身份原文。

- `POST /api/client/appeals`：客户端提交申诉；同一评估幂等建单。
- `GET /api/client/appeals/{appeal_id}`：携带 `X-Appeal-Token` 查询进度。
- `POST /api/client/appeals/{appeal_id}/evidence`：携带凭证补充说明或受控文件元数据。
- `GET /api/internal/appeals`：携带 `X-Internal-Approval-Token` 查询内部复议队列。
- `POST /api/internal/appeals/{appeal_id}/review`：执行维持、推翻或要求补充材料。

申诉状态包括 `SUBMITTED`、`NEEDS_INFO`、`DECISION_UPHELD` 和 `DECISION_OVERTURNED`。复议永远不会覆盖原始 `risk_assessment`；推翻拒绝时会追加 `label_source=APPEAL` 的独立纠正标签及操作审计。

当前材料接口只保存文字、文件名和 SHA-256。生产文件必须先经过银行文件服务的病毒扫描、内容安全、加密存储和访问授权。生产环境还必须由密钥系统注入 `APPEAL_SIGNING_KEY`、`APPEAL_REVIEW_TOKEN`。

## Docker / MySQL / Neo4j

复制 `.env.example` 为 `.env`，设置 MySQL 和 Neo4j 密码，从 `docker/` 目录执行：

```powershell
docker compose --env-file ..\.env -f docker-compose.yml up -d --build
```

Compose 包含 MySQL 8.4、Neo4j 5、App、Nginx，并在容器中切换到 MySQL 与 Neo4j 配置。当前开发机未安装 Docker，因此编排文件只进行了 YAML 校验，未在本机实际拉起容器。

## 生产落地前必须补充

- 替换演示数据和合成模型，完成数据授权、脱敏、质量监控和标签成熟期定义。
- 使用 Alembic/企业数据库变更平台管理迁移；禁止生产环境自动 `create_all`。
- 接入统一身份认证、RBAC、密钥管理、API 网关、限流和双人复核。
- 完成模型公平性、稳定性、漂移、拒绝推断、冠军挑战者和监管解释报告。
- 对规则阈值、融合权重和策略进行离线回放、灰度、A/B 与损失函数验证。
- Neo4j 同步由受控任务执行，并配置备份、监控和数据保留策略。
