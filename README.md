# 医疗风控系统 AI_Risk_Medical — 项目启动文档

> 场景 F：医保结算 / 处方审核 / 挂号 / 药品代购 4 大风险场景
> 规则引擎 + XGBoost 双轨融合 · 8 张业务表 · 25 维医疗特征 · 19 条规则 · 412 个测试全绿
> 基线：尚硅谷 AI_Risk 电商风控版（风控核心 9 张表 + 决策流水线复用，业务层全量重写）

---

## 目录

1. [项目简介](#1-项目简介)
2. [环境准备](#2-环境准备)
3. [数据库初始化](#3-数据库初始化)
5. [造数（风险种子 + 训练数据）](#4-造数)
6. [XGBoost 训练](#5-xgboost-训练)
7. [回填 ML 评分](#6-回填-ml-评分)
8. [启动服务](#7-启动服务)
9. [跑测试](#8-跑测试)
10. [训练指标](#9-训练指标)
11. [生产部署（Docker）](#10-生产部署-docker)
12. [常见问题 FAQ](#11-常见问题-faq)

---

## 1. 项目简介

基于 AI_Risk 电商版迁移的**医疗风控教学项目**，验证"风控抽象跨行业复用"：

**复用不动**（任务书硬边界）：

- 风控核心 9 张表：risk_rule / risk_event / risk_feature / risk_assessment / risk_case / risk_blacklist / risk_user_profile / risk_action_log / risk_alert
- 引擎 4 核心：decision / feature / rule / ml_model（只改特征计算函数）
- 决策流水线：process_event 4 步 + run_risk_check 7 步，契约 RiskCheckRequest → RiskCheckResponse 不变

**医疗业务层重写**：

- 8 张业务表：UserInfo / Hospital / Doctor / Appointment（挂号）/ Prescription（处方）/ InsuranceClaim（医保结算）/ DrugOrder（药品订单）/ BlacklistExtra
- 4 大风险场景：医保结算 / 处方审核 / 挂号 / 药品代购
- 25 维医疗特征：用户 17（就诊/结算/取消挂号/跨院/异地等）+ 业务单 8（金额/报销率/药品量/医生行为等）
- 19 条规则 + 黑名单机制（医保卡/身份证/执业证/医院编码/用户）

## 2. 环境准备

```bash
cd AI_Risk_Medical
uv sync --extra test        # 或 pip install -r requirements.txt
```

MySQL 8.0（Docker 推荐）：

```bash
docker run -d --name risk-mysql \
  -e MYSQL_ROOT_PASSWORD=123321 \
  -e MYSQL_DATABASE=ecs \
  -p 3306:3306 \
  mysql:8.0 --character-set-server=utf8mb4
```

`.env` 配置：`DB_HOST / DB_PORT / DB_USER / DB_PASSWORD / DB_NAME / LLM_API_KEY` 等。

## 3. 新环境迁移（一条命令初始化）

换机器 / 换环境部署时，拿到代码后按顺序：

```bash
# 1. 装依赖
uv sync --extra test

# 2. 配置 .env（DB_HOST / DB_PASSWORD / LLM_API_KEY，见 §2）

# 3. 起 MySQL 8.0（见 §2 的 docker 命令）

# 4. 一条命令从零到可用：
#    建库(init_db) → 30 个风险用户 → 训练数据 → 训练模型 → 回填 ML 评分 → 今日演示数据
python scripts/one_command.py

# 5. 启动服务
python run_app.py
```

`one_command.py` 内置 6 步：`init_db --reset` → `gen_risky_users --count 30` → `gen_train_dataset --reset` → `train_xgb_model` → `backfill_ml_score` → `gen_risk_data_with_dates --live`（已完整验证，约 5 分钟）。

> 注意：one_command 默认是演示规模（30 个风险用户）。需要加大数据量时用下面的分步命令（§4-§6）。

## 4. 数据库初始化


```bash
python scripts/init_db.py --reset --yes
```

- 用 ORM metadata 建 17 张表（8 业务 + 9 风控）
- 导入 19 条医疗规则 + 黑名单种子
- 导入基础数据：4 家医院 / 8 名医生 / 5 名参保人 + 业务样例

## 5. 造数

```bash
# 100 个高风险种子参保人（16 种风险模式轮换）
python scripts/gen_risky_users.py --count 100 --reset

# 强标注训练数据（ml_score 强制 NULL，正例约 56%）
python scripts/gen_train_dataset.py --n-risk 100 --n-normal 5 --per-user 25 --reset

# 演示评估数据（万级可选，正例比例可用 --balance-pos 拉高）
python scripts/gen_risk_data.py --count 5000 --balance-pos
```

16 种风险模式：医保卡盗刷 / 医生统方 / 挂号黄牛 / 处方超量 / 虚假病历 / 药品代购 / 异地集中结算 / 黑医保卡 / 无诊断开药 / 医师跨院高频 / 夜间结算异常 / 慢病频繁购药 / 分解住院结算 / 重复购药回流 / 串换药品嫌疑 / 异常高额报销。

## 6. XGBoost 训练

```bash
python scripts/train_xgb_model.py
```

- 数据源：risk_assessment（`ml_score IS NULL` 干净数据）+ risk_feature 25 维快照
- 输出：val_auc / val_f1 / val_accuracy / best_iteration / 假收敛检测
- 产物：`app/engine/xgb_model.json`

## 7. 回填 ML 评分

```bash
python scripts/backfill_ml_score.py
```

给历史评估回填 `ml_score / ml_decision`（前端 ML 评分小节的来源，忘了跑前端恒 0）。

## 8. 启动服务

```bash
python run_app.py                      # 含 6 步启动自检（交互确认）
# 或跳过自检直接起：
python -m uvicorn scripts.main:app --host 0.0.0.0 --port 8000
```

打开 http://localhost:8000 ：

- 规则管理：19 条规则可视化（R001 医保卡盗刷 / R002 医生统方 / R004 处方超量 … R013-R020 监管扩展）
- 风险检查：按 4 大场景触发，返回规则命中 + ML 评分 + 拒绝原因
- 案件工作台：拒绝/审核案件列表 + 证据链 + 复核
- AI 稽核助手：风控检查 / 案件查询 / 用户画像 / 黑名单 / 业务数据查询

## 9. 跑测试

```bash
pytest tests/ -k "not scheduler"
# 412 passed
```

## 10. 训练指标

训练时间：2026-08-11（教学强标注数据）

| 指标 | 值 | 任务书要求 |
|---|---|---|
| 训练样本 | 700（正例 42.9%） | ≥500，正例 ≥15% |
| val_auc | 1.0000 | ≥0.7 |
| val_f1 | 1.0000 | ≥0.5 |
| val_accuracy | 1.0000 | - |
| best_iteration | 50（早停 + warmup 50 防假收敛） | 不假收敛 |
| scale_pos_weight | 1.33 | - |

> 说明：教学数据为强标注构造（RISK 用户特征与标签强相关），指标饱和属预期；真实场景需人工稽核标注回流，指标会回归合理区间。2026-08-11 规则扩至 19 条后重训：新规则相关特征（跨院/诊断/处方量/药品订单）进入模型重要性 TOP，各规则均可在演示数据上命中。

## 11. 生产部署（Docker）

```bash
cd docker
cp .env.example .env   # 填 MYSQL_ROOT_PASSWORD + LLM_API_KEY
docker compose up -d   # MySQL + app + nginx 3 个容器
docker compose exec app python scripts/init_db.py --yes
```

详见 `docker/README.md`。

## 12. 常见问题 FAQ

**Q: 前端 ML 评分恒 0？**
A: 先训练再 `python scripts/backfill_ml_score.py` 回填。

**Q: 模型加载失败？**
A: `app/engine/xgb_model.json` 不存在 → 先跑 `train_xgb_model.py`；特征名不匹配 → 检查 FEATURE_COLUMNS 与 feature.py 对齐（test_xgboost.py 有守护测试）。

**Q: 规则不生效？**
A: 检查规则 `is_enabled=1`（init_risk_data.sql 默认启用）；条件里的特征名必须与 FEATURE_COLUMNS 一致。

**Q: 训练假收敛（val_auc≈0.5）？**
A: 正例比例不足 → `gen_train_dataset.py --per-user` 加大，或 `gen_risk_data.py --balance-pos`；数据太少 → 加大造数。

**Q: 数据库重置？**
A: `python scripts/init_db.py --reset --yes`（会删库重建，含规则与基础数据）。

**Q: 造数脚本报 "A value is required for bind parameter '14'"？**
A: SQL 里 JSON 字段 `"qty":14` 冒号后无空格会被 SQLAlchemy `text()` 误判为命名绑定参数，统一写成 `"qty": 14`（冒号后带空格）即可。
