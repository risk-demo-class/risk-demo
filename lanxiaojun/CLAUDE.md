# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

教育风控系统 (AI_Risk) — FastAPI + MySQL + XGBoost + LangChain 构建的实时风控系统。核心是一次请求经历 7 步决策流水线（事件→特征→规则→ML→评分→落库），最终给出"通过/标记/人工审核/拒绝"四档决策。2026-08 从电商风控迁移为教育风控（10 张教育业务表 + 20 维教育特征 + 30 条教育规则）。

## Commands

```bash
# ── Environment ──
conda create -n risk python=3.11 -y && conda activate risk
pip install -r requirements.txt

# ── Database Init (must do first) ──
python scripts/init_db.py                          # 新装（10 教育业务表 + 9 风控表 + 业务测试数据 + 30 条教育规则）
python scripts/init_db.py --drop                   # 重置（先删后建）

# ── Generate Test Data ──
python scripts/gen_10w_data.py                     # 大量随机业务数据（默认 1 万用户）
python scripts/gen_risk_data.py --count 200        # 风控评估数据（训练 XGBoost 前用）
python scripts/gen_risk_data_with_dates.py --days 7 --per-day 20  # 带日期的评估数据（仪表盘趋势用）
python scripts/gen_risky_users.py                  # 5 个高风险用户样本（规则测试用）

# ── Train XGBoost Model ──
python scripts/train_xgb_model.py                  # 从 risk_assessment 拉数据训练，保存到 app/engine/xgb_model.json

# ── Run Server ──
python run_app.py                                  # 推荐：一键启动（含 6 步自检）
python scripts/main.py                             # 直接启动（跳过自检）

# ── Tests ──
pytest tests/ -v                                   # 全部测试
pytest tests/test_risk_decision.py -v              # 单个测试文件
DDL_CHECK_ENABLED=1 pytest tests/test_ddl_sync.py -v  # DDL 同步检查（需要真实 DB）

# ── Docker Deploy ──
cd docker && docker compose up -d                  # MySQL + FastAPI + Nginx
docker compose exec app python scripts/init_db.py --yes
```

## Architecture (6 Layers)

```
scripts/main.py  ── FastAPI app entry (registers 10 routers + lifespan scheduler)
                    │
     ┌──────────────┼──────────────────┐
     │              │                   │
  pages          api               agent/chat.py
  (Jinja2)    (10 routers)     (LangChain + qwen-plus)
                 │                    │
          service/event.py        agent/tools.py (8 tools)
                 │                    │
          engine/decision.py          │
          (7-step pipeline)           │
     ┌──────┼──────┐                  │
     │      │      │                  │
  feature rule  ml_model              │
  (20维)  (条件求值) (XGBoost)          │
     │      │      │                  │
     └──────┴──────┴──────────────────┘
                 │
          database.py (async SQLAlchemy + MySQL)
                 │
          19 tables (10 education + 9 risk)
```

### Layer Responsibilities

| Layer | Directory | Role |
|-------|-----------|------|
| Entry | `scripts/main.py` | FastAPI app creation, router registration, lifespan |
| Router | `app/routers/` (10 modules) | HTTP endpoints, Pydantic validation, no business logic |
| Service | `app/service/` (5 modules) | Orchestration: validate → enrich → blacklist → engine |
| Engine | `app/engine/` (4 modules) | Core logic: 20-dim education features, rule matching, XGBoost, 7-step pipeline |
| Agent | `app/agent/` (2 modules) | LangChain agent + 8 tools wrapping service layer |
| Data | `app/database.py` + models | Async SQLAlchemy, 19 ORM tables (10 education + 9 risk) |

### Core Data Flow (Risk Check)

```
POST /api/risk/check
  → routers/risk.py::api_risk_check()
    → service/event.py::process_event()
      1. validator.validate_risk_check_request()  [entity check + anti-fraud]
      2. _enrich_request()                        [auto-fill course_id/device_id]
      3. _check_all_blacklists()                  [user>student_id>id_card>device>payment>phone, 6-level]
      4. engine/decision.py::run_risk_check()
         Step 1: _build_context()                 [Context Object pattern]
         Step 2: _create_event_record()           [INSERT risk_event]
         Step 3: feature.compute_all_features()   [20 dims from 10 education tables]
         Step 4: _save_feature_snapshot()         [INSERT risk_feature × 20 rows]
         Step 5: rule.load_enabled_rules()+match_rules()  [JSON condition eval]
         Step 6: _calculate_decision()            [score = max+bonus, veto, XGBoost fusion]
         Step 7: persist (assessment/case/profile) + commit
```

## Key Design Patterns

### 1. 7-Step Pipeline (`app/engine/decision.py`)
Scoring formula: `final_score = max(hit_scores) + BONUS(3) × extra_hits`, capped at 100.  
Dual-track fusion: `final = 0.5 × rule_score + 0.5 × ML_score` (weights from config).  
Veto: any "极高" rule hit → force reject (ML cannot override).

### 2. Dual-Track Fusion
- Rule score: deterministic, human-readable, 0-100  
- ML score: XGBoost P(reject) → sigmoid calibration `100 × (1 - e^(-3 × prob))`  
- Config: `ML_WEIGHT_RULE` / `ML_WEIGHT_XGB` in `.env`

### 3. Blacklist Short-Circuit (6-level)
Priority: user > student_id > id_card > device_fingerprint > payment_account > phone. Hit any → immediate reject (no engine, no DB write).

### 4. Conditional Case Creation
Only "人工审核" or "拒绝" → `risk_case` record. "通过"/"标记" → assessment only.

### 5. Transaction Boundary
`run_risk_check()` writes 4-5 tables then `db.commit()` atomically. Any failure → rollback.

### 6. Context Object Pattern
`_RiskCheckContext` carries shared state across all 7 steps (request, user_id, course_id, device_id, event_id).

## Key Files Reference

| Priority | File | Why |
|----------|------|-----|
| 🔴 Core | `app/engine/decision.py` | 7-step pipeline, scoring, veto, fusion |
| 🔴 Core | `app/engine/feature.py` | 20-dim education feature computation |
| 🔴 Core | `app/engine/rule.py` | JSON condition matching engine |
| 🔴 Core | `app/engine/ml_model.py` | XGBoost load/predict/train |
| 🔴 Core | `app/service/event.py` | Unified event pipeline orchestrator |
| 🔴 Core | `app/config.py` | All thresholds, ML params, DB/LLM config |
| 🔴 Core | `app/schemas.py` | Pydantic request/response models |
| 🟡 Important | `app/service/validator.py` | Entity validation + anti-horizontal-privilege-escalation |
| 🟡 Important | `app/service/case.py` | Case/blacklist/profile CRUD |
| 🟡 Important | `app/database.py` | Async engine + session factory + DI |
| 🟡 Important | `app/agent/chat.py` | LangChain agent setup |
| 🟡 Important | `app/agent/tools.py` | 8 agent tools |
| 🟡 Important | `app/scheduler.py` | Background asyncio loop (case timeout + alerts) |

## Risk Tables (9)

| Table | Purpose |
|-------|---------|
| `risk_rule` | 30 pre-configured rules (JSON conditions) |
| `risk_event` | Event audit trail |
| `risk_feature` | 20-dim education feature snapshots (1 row per dimension) |
| `risk_assessment` | Assessment results (final_score, decision, ML score, hit details) |
| `risk_case` | Cases for manual review (created only for "人工审核"/"拒绝") |
| `risk_blacklist` | Blacklist (user/student_id/id_card/device/payment/phone 6 types) |
| `risk_user_profile` | User risk profile (upsert per assessment) |
| `risk_action_log` | Audit log for all CRUD operations |
| `risk_alert` | System alerts (case backlog / hit rate drop / rejection spike) |

## Business Tables (10)

Education business tables (ORM read-only mirror): `UserInfo` (expanded), `StudentProfile`, `TeacherInfo`, `Course`, `OrderInfo` (refactored), `LearningProgress`, `RefundRequest`, `Complaint`, `PaymentAccount`, `DeviceFingerprint`.

## ML Training Config (`app/config.py`)

```python
XGB_TEST_SIZE = 0.2           # validation split (stratify)
XGB_EARLY_STOPPING_ROUNDS = 10
XGB_MIN_SAMPLES = 1000         # 20 dims × 50
XGB_MAX_SCALE_POS_WEIGHT = 10.0
ML_WEIGHT_RULE = 0.5           # α
ML_WEIGHT_XGB = 0.5            # β  (α + β = 1)
```

Thresholds: PASS=30, MARK=60, REVIEW=80 (configurable via `.env`).

## AI Agent

- Model: Alibaba Cloud Bailian `qwen-plus` (OpenAI-compatible API)
- Framework: LangChain + DeepAgents
- 8 tools: risk_check, query_case, query_user_profile, manage_blacklist, query_dashboard_stats, query_trend, query_rule_effect, query_business_data
- Session management: server-side session_id (ulid), timeout via `asyncio.wait_for`