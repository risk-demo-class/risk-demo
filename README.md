# 医疗风控系统 AI_Risk_Medical — 项目启动文档

> 场景 F：医保结算 / 处方审核 / 挂号 / 药品代购 4 大风险场景
> 规则引擎 + XGBoost 双轨融合 · 8 张业务表 · 25 维医疗特征 · 11 条规则 · 414 个测试全绿
> 基线：尚硅谷 AI_Risk 电商风控版（风控核心 9 张表 + 决策流水线复用，业务层全量重写）

---

## 目录

1. [项目简介](#1-项目简介)
2. [环境准备](#2-环境准备)
3. [数据库初始化](#3-数据库初始化)
4. [造数（风险种子 + 训练数据）](#4-造数)
5. [XGBoost 训练](#5-xgboost-训练)
6. [回填 ML 评分](#6-回填-ml-评分)
7. [启动服务](#7-启动服务)
8. [跑测试](#8-跑测试)
9. [训练指标](#9-训练指标)
10. [生产部署（Docker）](#10-生产部署-docker)
11. [常见问题 FAQ](#11-常见问题-faq)

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
- 11 条规则 + 黑名单机制（医保卡/身份证/执业证/医院编码/用户）

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

## 3. 数据库初始化

```bash
python scripts/init_db.py --reset --yes
```

- 用 ORM metadata 建 17 张表（8 业务 + 9 风控）
- 导入 11 条医疗规则 + 黑名单种子
- 导入基础数据：4 家医院 / 8 名医生 / 5 名参保人 + 业务样例

## 4. 造数

```bash
# 100 个高风险种子参保人（8 种风险模式轮换）
python scripts/gen_risky_users.py --count 100 --reset

# 强标注训练数据（ml_score 强制 NULL，正例约 56%）
python scripts/gen_train_dataset.py --n-risk 100 --n-normal 5 --per-user 25 --reset

# 演示评估数据（万级可选，正例比例可用 --balance-pos 拉高）
python scripts/gen_risk_data.py --count 5000 --balance-pos
```

8 种风险模式：医保卡盗刷 / 医生统方 / 挂号黄牛 / 处方超量 / 虚假病历 / 药品代购 / 异地集中结算 / 黑医保卡。

## 5. XGBoost 训练

```bash
python scripts/train_xgb_model.py
```

- 数据源：risk_assessment（`ml_score IS NULL` 干净数据）+ risk_feature 25 维快照
- 输出：val_auc / val_f1 / val_accuracy / best_iteration / 假收敛检测
- 产物：`app/engine/xgb_model.json`

## 6. 回填 ML 评分

```bash
python scripts/backfill_ml_score.py
```

给历史评估回填 `ml_score / ml_decision`（前端 ML 评分小节的来源，忘了跑前端恒 0）。

## 7. 启动服务

```bash
python run_app.py                      # 含 6 步启动自检（交互确认）
# 或跳过自检直接起：
python -m uvicorn scripts.main:app --host 0.0.0.0 --port 8000
```

打开 http://localhost:8000 ：

- 规则管理：11 条规则可视化（R001 医保卡盗刷 / R002 医生统方 / R004 处方超量 …）
- 风险检查：按 4 大场景触发，返回规则命中 + ML 评分 + 拒绝原因
- 案件工作台：拒绝/审核案件列表 + 证据链 + 复核
- AI 稽核助手：风控检查 / 案件查询 / 用户画像 / 黑名单 / 业务数据查询

## 8. 跑测试

```bash
pytest tests/ -k "not scheduler"
# 414 passed
```

## 9. 训练指标

训练时间：2026-08-11（教学强标注数据）

| 指标 | 值 | 任务书要求 |
|---|---|---|
| 训练样本 | 2500（正例 54.5%） | ≥500，正例 ≥15% |
| val_auc | 1.0000 | ≥0.7 |
| val_f1 | 1.0000 | ≥0.5 |
| val_accuracy | 1.0000 | - |
| best_iteration | 50（早停 + warmup 50 防假收敛） | 不假收敛 |
| scale_pos_weight | 0.84 | - |

> 说明：教学数据为强标注构造（RISK 用户特征与标签强相关），指标饱和属预期；真实场景需人工稽核标注回流，指标会回归合理区间。

## 10. 生产部署（Docker）

```bash
cd docker
cp .env.example .env   # 填 MYSQL_ROOT_PASSWORD + LLM_API_KEY
docker compose up -d   # MySQL + app + nginx 3 个容器
docker compose exec app python scripts/init_db.py --yes
```

详见 `docker/README.md`。

## 11. 常见问题 FAQ

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