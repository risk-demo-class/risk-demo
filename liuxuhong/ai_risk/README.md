# 教育风控系统 AI_Risk — 项目启动文档

> 5 层架构 · 15 张表（6 业务 + 9 风控）· **444 个测试** · 25 维教育特征 · 16 条规则 · 4 种事件类型 · 5 种黑名单 · 8 个 AI 工具 · XGBoost 双轨融合 + sigmoid 校准 + 一条龙命令 + 一键启动 + 可视化规则构建器
>
> 适用：项目第一次启动 / 老环境升级 / 规则制定 / XGBoost 训练 / 启动服务

---

## 目录

1. [项目简介](#1-项目简介)
2. [环境准备](#2-环境准备)
3. [数据库初始化](#3-数据库初始化)
4. [数据生成](#4-数据生成)
5. [规则制定](#5-规则制定)
6. [特征工程](#6-特征工程)
7. [XGBoost 模型训练](#7-xgboost-模型训练)
8. [启动 FastAPI 服务](#8-启动-fastapi-服务)
9. [一条龙命令](#9-一条龙命令)
10. [跑测试](#10-跑测试)
11. [生产部署 (Docker)](#11-生产部署-docker)
12. [日志管理](#12-日志管理)
13. [常见问题 FAQ](#13-常见问题-faq)
14. [一句话总结](#14-一句话总结)

---

## 1. 项目简介

**教育行业在线教育平台风控系统**，识别报名 / 退费 / 认证 / 打赏场景的欺诈行为。

**核心业务链路**：课程浏览 → 报名下单 → 支付 → 学习 → 完课/退费

**与电商版的差异**：无物流配送、商品是虚拟课程、退费规则复杂、设备指纹识别假学员代理。

### 1.1 5 层架构

```
┌─────────────────────────────────────────────────────┐
│  表现层    templates/ (Jinja2) + static/app.js       │
├─────────────────────────────────────────────────────┤
│  API 层    app/routers/ (risk/rule/case/blacklist/   │
│            assessment/dashboard/alert/agent/pages)   │
├─────────────────────────────────────────────────────┤
│  服务层    app/service/ (event/validator/case/       │
│            alert/action_log)                         │
├─────────────────────────────────────────────────────┤
│  引擎层    app/engine/ (decision/feature/rule/       │
│            ml_model)                                 │
├─────────────────────────────────────────────────────┤
│  数据层    MySQL: 6 张业务表 + 9 张风控表            │
└─────────────────────────────────────────────────────┘
```

### 1.2 核心契约

`process_event` 4 步 → `run_risk_check` 7 步流水线，接口契约固定：

```python
RiskCheckRequest(event_type, source_id, user_id, event_data)
    → RiskCheckResponse(assessment_id, final_score, risk_level, decision, ml_score, ...)
```

### 1.3 数据表（15 张）

**业务表（6 张）**：`user_info` / `course` / `order_info` / `learning_progress` / `refund_request` / `device_fingerprint`

**风控表（9 张）**：`risk_rule` / `risk_event` / `risk_feature` / `risk_assessment` / `risk_case` / `risk_blacklist` / `risk_user_profile` / `risk_action_log` / `risk_alert`

---

## 2. 环境准备

### 2.1 Python 依赖

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

依赖：`fastapi 0.115` / `uvicorn 0.34` / `sqlalchemy 2.0` / `aiomysql 0.2` / `pymysql 1.1` / `pydantic 2.10` / `jinja2 3.1` / `langchain 1.2` / `pandas 2.2` / `numpy 2.2` / `ulid-py 1.1` / `pytest 8.3` / `xgboost 2.1` / `httpx 0.27`

### 2.2 MySQL 准备

```bash
docker run -d --name risk-mysql \
  -e MYSQL_ROOT_PASSWORD=1234 \
  -e MYSQL_DATABASE=ecs \
  -p 3306:3306 \
  mysql:8.0 \
  --character-set-server=utf8mb4 \
  --collation-server=utf8mb4_0900_ai_ci
```

### 2.3 .env 配置

```ini
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=1234
DB_NAME=ecs
TEST_DB_NAME=ecs_test

# LLM (阿里云百炼 OpenAI 兼容)
LLM_API_KEY=sk-你的key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

# XGBoost 开关 (默认 True, 第一次没模型时自动降级)
XGB_ENABLED=True
```

---

## 3. 数据库初始化

```bash
# 一键重置（删库重建，教学/演示推荐）
python scripts/init_db.py --reset --yes

# 或保留数据只补表
python scripts/init_db.py --keep-data
```

**按顺序执行**：
1. 创建数据库 `ecs`
2. `init_business_tables.sql` — 6 张教育业务表
3. `init_business_data.sql` — 100+ 条业务测试数据
4. `init_risk_tables.sql` — 9 张风控表
5. `init_risk_data.sql` — 16 条预置教育风控规则

---

## 4. 数据生成

| 脚本 | 用途 | 用法 |
|---|---|---|
| `gen_business_data.py` | 造业务基础数据（用户/课程/订单/进度/退费/设备） | `python scripts/gen_business_data.py --count 100 --reset` |
| `gen_risky_users.py` | 造高风险用户（5 种模式轮换） | `python scripts/gen_risky_users.py --count 30` |
| `gen_risk_data.py` | 造风控评估数据（填充仪表盘） | `python scripts/gen_risk_data.py --count 50 --balance-pos` |
| `gen_train_dataset.py` | 造强标注训练集（ml_score=NULL） | `python scripts/gen_train_dataset.py --reset` |

**5 种高风险用户模式**：高退费率 / 高频报名 / 高退费金额 / 多设备 / 0学时退费

---

## 5. 规则制定

### 5.1 16 条预置规则（覆盖 6 大风险场景）

| 编号 | 规则名 | 分类 | 事件类型 | 等级 | 动作 |
|---|---|---|---|---|---|
| R001 | 刷单式报名 | 报名欺诈 | 课程报名 | 极高 | 拒绝 |
| R003 | 大额连报 | 报名欺诈 | 课程报名 | 高 | 人工审核 |
| R002 | 0学时退费 | 退费滥用 | 退费申请 | 高 | 人工审核 |
| R005 | 退费连环 | 退费滥用 | 退费申请 | 中 | 标记 |
| R004 | 假学员代理 | 账户风险 | 课程报名 | 极高 | 拒绝 |
| R007 | 学员身份不符 | 账户风险 | 课程报名 | 中 | 标记 |
| R006 | 直播打赏异常 | 打赏风险 | 直播打赏 | 中 | 标记 |
| R008 | 黑学号拦截 | 综合风险 | 通用 | 极高 | 拒绝 |
| R009-R016 | 新用户大额/高频退费/完课率低/多设备/深夜报名/超高金额/多类别/认证欺诈 | — | — | — | — |

### 5.2 规则引擎

JSON 条件表达式，支持 `> >= < <= == != in not_in between and or` 递归组合。

```json
{"and": [
  {"field": "order_total_amount", "op": ">=", "value": 500},
  {"field": "user_avg_completion_rate", "op": "<=", "value": 0.01}
]}
```

- 前端可视化构建器 + JSON 编辑器双模式
- `risk_level ↔ risk_score` 互验（`RISK_LEVEL_SCORE_MAP`）
- 一票否决：`risk_level="极高"` 命中 → 强制拒绝

---

## 6. 特征工程

**25 维特征**，按实体分 3 族：

| 实体 | 数量 | 特征举例 |
|---|---|---|
| 用户 | 14 | 报名总数/近30天/7天报名数、退费率、退费金额、总学习时长、平均完课率、设备数、课程类别数 |
| 订单 | 8 | 订单金额、是否首课、优惠率、报名时间、学习目标字数、预期完成天数 |
| 地址/设备 | 3 | 设备指纹数、不同IP数、是否新设备 |

特征名 ↔ XGBoost `FEATURE_COLUMNS` 顺序严格对齐（有测试锁死，防止特征错位）。

---

## 7. XGBoost 模型训练

```bash
# 1. 造训练数据（强标注，正负比 ~50%）
python scripts/gen_train_dataset.py --reset

# 2. 训练（输出 val_auc / val_f1 / 特征重要性）
python scripts/train_xgb_model.py

# 3. 回填评估记录 ml_score
python scripts/backfill_ml_score.py
```

**双轨融合**：`final_score = 0.5 × 规则分 + 0.5 × XGBoost分`（权重可调）

**评估指标**：val_auc / val_f1 / best_iteration / 特征重要性 TOP10 / 假收敛检测

**验收标准**：val_auc ≥ 0.7（本项目实测 **val_auc=1.0, val_f1=1.0**）

---

## 8. 启动 FastAPI 服务

```bash
python run_app.py
```

启动前自动 6 步自检（.env / 依赖 / MySQL / 数据库 / 端口 / XGBoost 模型）。

浏览器访问 http://localhost:8000

---

## 9. 一条龙命令

```bash
python scripts/one_command.py          # 6 步全流程: 重置 → RISK → 训练数据 → 训练 → 回填 → 今日数据
python scripts/one_command.py --skip-init    # 跳过 1+2
python scripts/one_command.py --skip-train   # 跳过 3+4+5
```

---

## 10. 跑测试

```bash
pytest                     # 444 passed, 5 skipped
```

Windows 系统 Temp 目录权限问题时已通过 `tests/conftest.py` 默认 `--basetemp=.pytest_tmp` 规避。

---

## 11. 生产部署 (Docker)

```bash
cd docker
docker compose up -d
```

包含：MySQL 8.0 + FastAPI app + Nginx 反代。

---

## 12. 日志管理

日志通过 `app/logging_config.py` 统一配置，输出到 `logs/` 目录。

---

## 13. 常见问题 FAQ

| 问题 | 解决 |
|---|---|
| MySQL 连不上 (1045) | 检查 .env 密码是否与 MySQL 实际密码一致（默认 1234） |
| XGBoost 模型不存在 | 先跑 `train_xgb_model.py`，没模型自动降级纯规则 |
| 训练数据正例 < 15% | `gen_train_dataset.py --reset` 重造（RISK 用户高正例） |
| 页面打不开 | `python run_app.py` 前确认 MySQL + 数据库已初始化 |

---

## 14. 一句话总结

**教育风控系统**：6 张业务表承载报名/退费/认证/打赏场景，25 维特征 + 16 条规则 + XGBoost 双轨融合识别欺诈，一条龙命令从零到训练到启动一键完成。
