# 制造业风控系统（Manufacturing Risk Control）

> 行业实战任务书：场景 D「制造业风控」· 基于尚硅谷 `AI_Risk`（电商版）风控内核的业务扩展
> 业务边界：经销商订货 / 设备保修 / 采购订单 / 售后维修
> 核心能力：把风控抽象迁移到陌生行业 + Vibe Coding 高效产出代码

本项目是完整可运行的 Git 仓库：**风控内核 100% 复用电商版，业务层 100% 按制造业重写**，并跑通「数据初始化 → 造数 → 特征/规则 → XGBoost 训练 → Web 演示」全链路。

---

## 一、任务书对照验收表

| 任务 | 交付物（文档要求） | 本项目文件 | 完成情况 |
|---|---|---|---|
| **任务1 业务理解** | `1-业务说明.md`：欺诈场景≥3、业务字段≥10、事件类型≥3、术语≥5 | [1-业务说明.md](1-业务说明.md) | ✅ 5 类欺诈场景 / 14 字段 / 3 事件 / 6 术语 |
| **任务2 数据层** | `models_business.py`、业务表 DDL、业务数据≥100条、造数脚本、validator 派发表、config 枚举 | [app/models_business.py](app/models_business.py) · [sql/init_business_tables.sql](sql/init_business_tables.sql) · [sql/init_business_data.sql](sql/init_business_data.sql) · [scripts/gen_business_data.py](scripts/gen_business_data.py) · [app/service/validator.py](app/service/validator.py) · [app/config.py](app/config.py) | ✅ 7 张业务表 / 300+ 订单 / 一键可重复造数 |
| **任务3 pipeline+训练** | `compute_*_features` 重写、`process_event` 分支、规则≥5、`train_xgb_model.py` 跑通（val_auc≥0.7） | [app/engine/feature.py](app/engine/feature.py) · [app/service/event.py](app/service/event.py) · [sql/init_risk_data.sql](sql/init_risk_data.sql) · [scripts/train_xgb_model.py](scripts/train_xgb_model.py) | ✅ 25 维特征 / 16 条规则 / **val_auc=0.9228** / 高风险用户可被识别 |
| **任务4 演示+文档** | 可运行 Git 仓库、README 完整说明、`agent_design.md` | 本文件 · [agent_design.md](agent_design.md) | ✅ 一条龙命令 + 讲解大纲见第十节 |

---

## 二、复用边界（任务书核心契约）

### 完全复用（不允许改）

- **风控核心 9 张表**：`risk_rule / risk_event / risk_feature / risk_assessment / risk_case / risk_blacklist / risk_user_profile / risk_action_log / risk_alert`（结构不变，仅按行业替换枚举取值）
- **风控引擎 4 个核心**：`app/engine/{decision, feature, rule, ml_model}.py` 的 schema 与流程不变
- **决策流水线**：`process_event` 4 步 + `run_risk_check` 7 步不改流程
- **核心契约**：`process_event(RiskCheckRequest(event_type, source_id, user_id, event_data)) → RiskCheckResponse` 不改变

### 必须自研（本项目的行业差异点）

| 模块 | 制造业实现 |
|---|---|
| 业务表（7 张） | 经销商档案 / 产品（MSRP+保修期）/ 经销订货 / 设备保修 / 跨区串货举报 / 业务黑名单扩展 |
| 三大特征族（25 维） | 经销商用户 13 + 订货/保修事件 9 + 发货区域 3 |
| 业务校验派发 | `validator.py::_EVENT_SOURCE_VALIDATORS` 覆盖 3 种事件 |
| 黑名单类型 | 经销商 / 设备SN / 维修工（含 用户/手机号/地址 兼容） |
| 事件类型 | 经销商订货 / 设备保修 / 跨区串货举报 |
| 业务规则 | 16 条（R001-R030，覆盖 6 大风险场景） |
| 造数脚本 | 业务数据 / 高风险经销商 / 训练数据 / 评估数据 4 类脚本 |

---

## 三、架构总览

```
前端 (Jinja2 + Bootstrap 工业风主题)
   │  /api/risk/check 等 REST 接口
FastAPI 路由层 (app/routers + app/api.py)
   │
AI Agent (LangChain/DeepAgents, 8 个工具)
   │
服务层 (app/service)
   ├─ event.py      process_event 4 步: 校验 → 补全 → 黑名单前置 → run_risk_check
   ├─ validator.py  业务实体存在性 / 事件匹配 / 订单归属校验
   └─ case.py       案件 / 黑名单 / 画像 / 评估历史
   │
引擎层 (app/engine)
   ├─ feature.py    25 维制造业特征
   ├─ rule.py       JSON 规则引擎 (14 运算符 + and/or)
   ├─ decision.py   7 步流水线 + 一票否决 + 双轨融合
   └─ ml_model.py   XGBoost 加载/推理/训练
   │
MySQL 8.0 (mfg_risk 库: 7 业务表 + 9 风控表)
```

### 数据模型（16 张表）

| 业务表（7） | 说明 | 风控表（9） | 说明 |
|---|---|---|---|
| `user_info` | 经销商/终端用户/内部员工 | `risk_rule` | 规则配置 |
| `product` | 产品 + MSRP + 保修期 | `risk_event` | 事件审计 |
| `dealer_info` | 经销商档案 + 合同 | `risk_feature` | 特征快照 |
| `order_info` | 经销订货订单 | `risk_assessment` | 评估结果 |
| `warranty_record` | 设备保修记录 | `risk_case` | 案件管理 |
| `cross_region_report` | 跨区串货举报 | `risk_blacklist` | 黑名单 |
| `blacklist_extra` | 业务黑名单扩展 | `risk_user_profile` / `risk_action_log` / `risk_alert` | 画像 / 审计 / 告警 |

---

## 四、业务说明摘要（详见 [1-业务说明.md](1-业务说明.md)）

- **五大欺诈场景**：跨区串货 / 套保骗保 / 大额囤货倒卖 / 维修费用虚高 / 资质过期仍订货
- **关键字段**：`dealer_id / region / ship_to_region / contract_start / contract_end / msrp / warranty_months / quantity / total_amount / product_sn / repair_cost / technician_id` 等
- **事件类型**：经销商订货（source=order_id）、设备保修（source=warranty_id）、跨区串货举报（source=report_id）
- **行业术语**：串货 / 套保 / MSRP / 产品SN / 渠道体系 / 囤货

---

## 五、风控规则（16 条，按任务书 8 条核心 + 扩展）

| 规则 | 名称 | 触发条件 | 等级 | 动作 |
|---|---|---|---|---|
| R001 | 跨区串货举报拦截 | 同一订单被举报≥2 次 | 极高 | 拒绝 |
| R002 | 保修期外高频保修 | 过保 + 30 天同SN保修≥2 | 高 | 人工审核 |
| R003 | 夜间批量订货 | 凌晨 + 数量≥50 | 中 | 标记 |
| R004 | 跨区发货大额订单 | 跨区 + 金额≥500万 | 高 | 人工审核 |
| R005 | 大额经销商囤货 | 单笔数量>100 台 | 高 | 人工审核 |
| R006 | 高保修率经销商 | 保修率≥50% + 订货≥3 | 高 | 人工审核 |
| R007 | 累计维修费用过高 | 累计≥50万 | 高 | 人工审核 |
| R008 | 套保嫌疑 | 90 天同SN保修≥2 | 极高 | 拒绝 |
| R010 | 多区域发货 | 发货区域≥5 | 中 | 标记 |
| R012 | 新经销商大单 | 签约<30天 + 数量>50 | 中 | 标记 |
| R015 | 新区域首单大额 | 新区域 + 金额≥300万 | 高 | 人工审核 |
| R018 | 维修费用异常 | 维修费>MSRP 60% | 中 | 标记 |
| R020 | 高均价异常 | 平均订货≥1200万 | 中 | 标记 |
| R025 | 资质过期仍订货 | 合同过期 | 中 | 标记 |
| R029 | 新经销商首单大额 | 首单 + 金额≥300万 | 高 | 人工审核 |
| R030 | 黑经销商特征综合 | 举报≥4 + 订货≥3 | 极高 | 拒绝 |

黑名单前置拦截：**用户 > 经销商 > 设备SN > 维修工**，撞黑直接拒绝，不跑 7 步。

---

## 六、25 维特征（跟 XGBoost `FEATURE_COLUMNS` 一一对应）

| 特征族 | 数量 | 内容 |
|---|---|---|
| 经销商用户 `user_*` | 13 | 订货单数/近7-30天单数/总金额/均值/最大单/保修次数/保修率/维修费总额/均值/保修期外次数/串货举报数/合同年龄 |
| 订货保修事件 `order_*` | 9 | 金额/数量/单价/夜间/跨区/合同过期/30天同SN保修/90天同SN保修/维修费MSRP占比 |
| 发货区域 `addr_*` | 3 | 历史发货区域数/授权区域数/本次是否新区域 |

---

## 七、XGBoost 双轨融合

```
rule_score = max(命中规则分) + 3 × (额外命中数)，封顶 100
ml_score   = sigmoid 校准 P(拒绝) → 0-100
final      = 0.5 × rule_score + 0.5 × ml_score
一票否决   = 命中"极高"规则 → 强制拒绝，分数抬到 ≥90
```

**实测训练指标**（`python scripts/train_xgb_model.py`，n=1062）：

| 指标 | 值 | 任务书要求 |
|---|---|---|
| 验证集 AUC | **0.9893** | ≥0.7 ✅ |
| 验证集 F1 | 0.9231 | - |
| 准确率 | 0.9671 | - |

---

## 八、快速开始

### 0. 环境要求

- Python 3.11-3.12（本机 3.12.8 已测）
- MySQL 8.0（localhost:3306）
- 可选：阿里云百炼 API Key（AI 助手功能，不填自动降级）

### 1. 创建环境并安装依赖

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

> 说明：`uv/` 目录保留参考项目的 uv 配置；若本机 uv 缓存异常，按上述 venv+pip 方式即可（本项目实测用该方式）。

### 2. 配置 .env（复制以下内容到项目根目录 .env）

```ini
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=123456
DB_NAME=mfg_risk
TEST_DB_NAME=mfg_risk_test
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
```

### 3. 一条龙（重置库 → 造数 → 训练 → 回填 → 今日数据）

```bash
python scripts/one_command.py
```

### 4. 启动 Web 服务

```bash
python run_app.py
```

浏览器访问 http://localhost:8000

### 5. 分步执行（可选，教学演示推荐）

```bash
python scripts/init_db.py --reset --yes                 # 1. 重置数据库（16 表 + 16 规则）
python scripts/gen_business_data.py --emit-sql sql/init_business_data.sql   # 2. 业务数据（300+ 订单）
python scripts/gen_risky_users.py --count 30            # 3. 30 个高风险经销商（8 模式）
python scripts/gen_train_dataset.py --reset             # 4. 训练数据集（约 1000+ 条，ml_score=NULL）
python scripts/train_xgb_model.py                       # 5. 训练 XGBoost（val_auc/val_f1）
python scripts/backfill_ml_score.py                     # 6. 回填 ml_score（正负分离度验证）
python scripts/gen_risk_data_with_dates.py --days 7 --per-day 60   # 7. 近 7 天评估（仪表盘趋势）
python scripts/verify_risk_check.py                     # 8. 冒烟：3 类事件各跑一次真实风控检查
python scripts/api_smoke.py                             # 9. 冒烟：HTTP API（含黑名单拦截）
```

---

## 九、验证与演示

### 9.1 高风险用户可被识别（任务3 验收）

```text
POST /api/risk/check  设备保修(RISK002)      → 拒绝（92分，命中 R008 套保嫌疑，ML=0.90）
POST /api/risk/check  经销商订货(RISK003)    → 标记（38分，命中 R005 大额囤货 + R020）
POST /api/risk/check  黑经销商(RISK008)      → 拒绝（blacklist 前置拦截）
```

### 9.2 测试

```bash
python -m pytest tests -q    # 320 passed, 1 skipped
```

---

## 十、现场讲解大纲（5-8 分钟）

| 分钟 | 环节 | 讲什么 |
|---|---|---|
| 0-1 | 业务说明 | 制造业渠道风控 vs 电商的差异；五大欺诈场景（串货/套保/囤货/维修费/资质） |
| 1-3 | 架构与复用边界 | 9 张风控表 + 7 步流水线完全复用；业务层 7 表 + 25 特征 + 16 规则自研 |
| 3-5 | 跑通演示 | `init_db` → 造数 → `run_risk_check`，现场演示 3 类事件的高风险识别 |
| 5-6 | XGBoost 评估 | 训练日志 val_auc=0.92 / val_f1=0.99；双轨融合与一票否决 |
| 6-7 | 业务规则讲解 | R001 串货拦截 / R005 囤货 / R008 套保 / R025 资质过期 的阈值设计 |
| 7-8 | Vibe Coding 复盘 | [agent_design.md](agent_design.md)：迁移方法论、踩坑（编码/缓存/特征对齐） |

---

## 十一、目录结构

```
├── app/
│   ├── models_business.py     # 7 张制造业业务表
│   ├── models_risk.py         # 9 张风控表（枚举按行业替换）
│   ├── schemas.py             # 请求/响应模型
│   ├── engine/                # feature / rule / decision / ml_model
│   ├── service/               # validator / event / case / alert / action_log
│   ├── routers/               # 10 个路由文件
│   └── agent/                 # LangChain/DeepAgents AI 助手
├── sql/                       # init_business_tables/data + init_risk_tables/data
├── scripts/                   # 初始化/造数/训练/回填/冒烟/一条龙
├── templates/ static/         # 制造业工业风前端
├── tests/                     # 320 个测试
├── 1-业务说明.md               # 任务1 交付物
├── agent_design.md            # 任务4 交付物（Vibe Coding 复盘）
└── docker/ uv/                # 部署与 uv 配置（可选）
```

---

## 十二、常见问题

- **MySQL 连不上 / 自检报错**：确认 MySQL80 服务运行、`.env` 密码正确；`run_app.py` 自检已改为读取 `.env`。
- **端口 8000 被占**：`netstat -ano | findstr :8000` 找 PID 后 `taskkill /PID <pid> /F`，或设置 `APP_PORT`。
- **初始化出现 Unknown table 警告**：`DROP TABLE IF EXISTS` 的正常提示，不影响结果。
- **模型未加载/ML 分数为空**：先跑 `python scripts/train_xgb_model.py`；删除 `app/engine/xgb_model.json` 则走纯规则兜底。
- **训练数据不足**：`gen_train_dataset.py` 会按现有经销商数据量自动跳过，可加大 `--n-risk/--n-normal` 或先造更多业务数据。
- **uv 环境报错**：跳过 uv，使用 `python -m venv .venv && pip install -r requirements.txt`。
