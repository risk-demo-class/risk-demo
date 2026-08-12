# 制造业设备经销商智能风控平台

AI_Risk 是一个制造业风险系统工程 Demo，面向设备制造商的经销商采购、设备保修、跨区域串货和经销商主体风险。项目展示从业务建模到规则、特征、XGBoost、案件与 Agent 解释的完整风控链路。

当前数据为合成制造业业务数据，训练标签为 JSON 规则产生的弱监督标签。模型指标表示“模型模仿当前规则标签”的能力，不代表真实制造企业欺诈识别效果，也不应直接用于生产决策。

## 技术架构

```text
FastAPI / Jinja2 页面与 API
        ↓
RiskCheckRequest → validator → process_event
        ↓
制造业六表 → 25维 Feature → JSON Rule Engine → XGBoost
        ↓
RiskAssessment / RiskCase / RiskAlert / Agent 证据解释
        ↓
SQLAlchemy Async + MySQL
```

主要组件：FastAPI、SQLAlchemy Async、MySQL、JSON Rule Engine、Feature Engineering、XGBoost、LangChain/DeepAgents Agent。

## 数据模型

制造业业务层严格使用 6 张表：

- `dealer`：经销商主体、等级、授权区域与合作期限
- `device`：设备、SN、型号、批次、出厂与保修期限
- `purchase_order`：采购单、金额、设备明细、交付区域与付款条件
- `warranty_claim`：设备保修申请、故障、金额与材料
- `cross_region_report`：授权区域与实际区域的串货报告
- `blacklist_extra`：统一社会信用代码、证照、银行账户、联系方式等扩展标识

通用风控核心层固定为 9 张表：

- `risk_rule`
- `risk_event`
- `risk_feature`
- `risk_assessment`
- `risk_case`
- `risk_blacklist`
- `risk_user_profile`
- `risk_action_log`
- `risk_alert`

这些核心表的字段、类型、ENUM、索引和约束是迁移兼容基线。

## 内部兼容码

为保持核心 schema 和历史算法稳定，数据库仍保存以下内部码；页面、API 文档和 Agent 会翻译成制造业名称。

| 内部事件码 | 制造业展示 | source_id |
|---|---|---|
| `下单` | 经销商采购提交 | `purchase_order.po_id` |
| `支付` | 采购付款/确认 | `purchase_order.po_id` |
| `售后申请` | 设备保修申请 | `warranty_claim.claim_id` |
| `物流投诉` | 串货举报/跨区域检查 | `cross_region_report.report_id` |

`user_id` 在制造业入口中表示 `dealer_id`。25维特征仍保留冻结的名称和顺序：14 个 `user_*` 表示经销商画像，8 个 `order_*` 表示当前采购/保修/串货对象，3 个 `addr_*` 表示授权、交付与实际区域风险。这些兼容名不表示项目仍是电商系统。

## 规则与决策链路

第一版初始化 7 条制造业 JSON 规则：跨区域串货、短期大量保修、新经销商大额采购、老旧设备高额保修、异常区域集中、设备/SN异常重复、保修材料异常。黑经销商不伪装成 JSON 规则，而是在 `process_event` 第 3 步通过核心 `risk_blacklist` 前置拦截。

固定流程：

```text
process_event: 校验 → 关联补全 → 黑名单 → run_risk_check
run_risk_check: 上下文 → RiskEvent → Feature → RiskFeature → Rule → Decision → Persistence
```

## 环境与安装

推荐 Python 3.11/3.12、MySQL 8，并在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

复制或编辑 `.env`，至少配置数据库和 LLM：

```dotenv
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=ecs

LLM_API_KEY=your_key
LLM_BASE_URL=your_openai_compatible_endpoint
LLM_MODEL_NAME=your_model
```

Agent 使用 OpenAI 兼容协议的模型服务。没有可用 LLM 配置时，规则、Feature、XGBoost、API 和页面仍可运行，但自然语言 Agent 对话不能调用外部模型。

## 数据库初始化

初始化脚本默认会删除目标数据库。开发和验收必须显式使用独立数据库，避免向默认 `ecs` 写入模拟数据：

```powershell
python scripts/init_db.py --db ai_risk_demo --reset --yes
```

该命令创建 6 张制造业业务表、9 张核心风控表，插入小规模基础业务数据和 7 条规则。若要保留目标库现有数据，使用 `--keep-data`。

## 制造业模拟数据与训练

下面所有命令都建议使用独立数据库：

```powershell
# 1. 生成合成制造业主体、采购、设备、保修、串货与黑名单数据
python scripts/gen_risky_users.py --db ai_risk_ml --count 180 --reset

# 2. 每个真实业务 source 只执行一次 process_event，产生25维快照和弱标签
python scripts/gen_risk_data.py --db ai_risk_ml --reset

# 3. 从 risk_feature 事件快照只读导出训练集
python scripts/gen_train_dataset.py --db ai_risk_ml

# 4. 按 dealer_id 分组切分并训练标准制造业模型
python scripts/train_xgb_model.py

# 5. 先只读审计，再基于历史快照回填 ml_score
python scripts/backfill_ml_score.py --db ai_risk_ml --dry-run
python scripts/backfill_ml_score.py --db ai_risk_ml

# 6. 验证真实推理和在线 run_risk_check
python scripts/verify_ml_pipeline.py --db ai_risk_ml
```

标签定义：`人工审核/拒绝 → label=1`，`通过/标记 → label=0`。这是规则弱监督标签，不是真实欺诈标签。训练集与验证集按 `dealer_id` 分组，检查 dealer、source 和完全相同特征向量的交叉泄漏。

## 当前标准模型指标

标准模型位于 `app/engine/xgb_model.json`，输入维度固定为 25。最近一次合成弱监督训练记录：

| 指标 | 结果 |
|---|---:|
| 训练 / 验证样本 | 842 / 198 |
| Accuracy | 0.989899 |
| Precision | 0.982143 |
| Recall | 1.000000 |
| F1 | 0.990991 |
| ROC-AUC | 0.999587 |
| Confusion Matrix | `[[86, 2], [0, 110]]` |
| dealer/source/重复向量交叉泄漏 | `0 / 0 / 0` |

参数包括 `binary:logistic`、`max_depth=6`、`eta=0.1`、`min_child_weight=3`、`subsample=0.8`、`colsample_bytree=0.8`、L1 `0.1`、L2 `1.0`。指标接近 1.0 的主要原因是合成场景与规则弱监督标签可分，不能宣传为真实工业欺诈检测能力。完整记录见 `app/engine/xgb_model.json.metrics.json`。

## 启动

```powershell
python run_app.py
```

或者直接运行：

```powershell
python -m uvicorn scripts.main:app --host 0.0.0.0 --port 8000
```

页面入口：

- `http://localhost:8000/`：制造业风险驾驶舱
- `/risk-check`：采购、付款、保修、串货风险检查
- `/rules`：制造业规则管理（展示名与内部类别映射）
- `/cases`：经销商风险案件
- `/assessments`：完整评估证据
- `/blacklist`：经销商/区域黑名单
- `/chat`：制造业 Agent
- `/docs`：FastAPI OpenAPI 文档

## Agent 查询能力

Agent 保留 8 个通用 Tool，没有为每种业务无意义地扩张 Tool 数量。`query_business_data` 支持：

- `dealer_info`
- `dealer_purchase_orders`
- `device_history`
- `warranty_claims`
- `cross_region_reports`
- `high_value_purchase_orders`
- `blacklist_extra`
- `risk_assessment_evidence`

Agent 从真实 `RiskAssessment`、`RiskEvent`、`RiskFeature`、命中规则和业务表解释结果，不自行修改 `risk_level/action/final_score/ml_score`，也不重新创造风险结论。

## 端到端 Demo

最终验收脚本使用独立数据库，并输出业务输入、内部事件码、25维关键特征、命中规则、规则分证据、XGBoost 概率、最终分、决策、Case/Alert 和 Agent 解释：

```powershell
python scripts/final_e2e_demo.py --db ai_risk_ml
```

场景覆盖：

- A：长期经销商正常采购
- B：新经销商大额采购
- C：正常设备保修
- D：高频、高金额且材料缺失的异常保修
- E：跨区域串货
- F：黑名单经销商（第3步短路，不产生 Feature/ML/Assessment）

页面截图建议放在 `docs/screenshots/`：`dashboard.png`、`risk-check.png`、`assessment-evidence.png`、`agent-chat.png`。截图应分别展示驾驶舱、制造业事件表单、完整证据链和 Agent 解释；不要在截图中暴露数据库密码或 LLM Key。

## 测试

全项目测试：

```powershell
python -m pytest
```

需要真实数据库的 Step 2–5 契约测试可显式指向独立验收库：

```powershell
$env:STEP2_DB_NAME="step2_contract_test"
$env:STEP3_DB_NAME="step345_contract_test"
$env:STEP4_DB_NAME="step345_contract_test"
$env:STEP5_DB_NAME="step345_contract_test"
python -m pytest
```

## 已知限制

- 合成数据和规则弱监督不能替代真实制造企业标签、漂移监控与人工复核反馈闭环。
- Agent 会话保存在进程内存，重启后丢失；外部 LLM 的可用性取决于实际配置与网络。
- `risk_alert` 是系统聚合监控告警，不是每个风险事件必然生成一条 Alert。
- 第一版只使用 6 张制造业表，采购明细保存在 JSON 中；未引入 EquipmentModel、PurchaseOrderDetail、DealerTerritory。
- 内部 ENUM、`user_id` 和 `user_/order_/addr_` 是冻结兼容契约，页面和 Agent 负责制造业语义翻译。
