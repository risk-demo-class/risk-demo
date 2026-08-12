# decision.py — 风控决策引擎 模块文档

> 文件路径: `app/engine/decision.py`  
> 职责: 串联 7 步风控流水线，事件 → 特征 → 规则 → 评分 → 决策 → 持久化

---

## 目录

- [1. 模块概述](#1-模块概述)
- [2. 依赖关系](#2-依赖关系)
- [3. 工具函数](#3-工具函数)
- [4. 上下文数据类](#4-上下文数据类)
- [5. 步骤 1：准备上下文](#5-步骤-1准备上下文)
- [6. 步骤 2：创建事件记录](#6-步骤-2创建事件记录)
- [7. 步骤 3-4：特征计算与快照](#7-步骤-3-4特征计算与快照)
- [8. 步骤 5：规则匹配](#8-步骤-5规则匹配)
- [9. 步骤 6：评分与决策（核心）](#9-步骤-6评分与决策核心)
- [10. 步骤 7：落库与响应](#10-步骤-7落库与响应)
- [11. 主函数](#11-主函数)
- [12. Demo 自检](#12-demo-自检)
- [13. 数据流图](#13-数据流图)

---

## 1. 模块概述

整个风控系统核心编排层，把一次风控检查拆为 **7 步流水线**，在单个数据库事务内串行执行。任一步失败 → 事务回滚，不留脏数据。

### 三大核心公式

| 机制 | 公式 | 说明 |
|------|------|------|
| 规则评分 | `min(max(各规则分) + BONUS × (额外命中数), 100)` | 多规则叠加惩罚，上限 100 |
| 双轨融合 | `final_score = α × rule_score + β × ml_score` | α+β=1，.env 可调 |
| 一票否决 | 任意 `risk_level="极高"` → 强制拒绝 | ML 低分也无法推翻 |

---

## 2. 依赖关系

```python
# 配置
from app.config import settings

# 特征引擎 (25 维)
from app.engine.feature import compute_all_features

# ML 模型 (XGBoost)
from app.engine.ml_model import is_model_loaded, predict

# 规则引擎
from app.engine.rule import RuleHitResult, load_enabled_rules, match_rules

# 数据库模型 (5 张表)
from app.models import (
    OrderInfo, RiskAssessment, RiskCase, RiskEvent, RiskFeature, RiskUserProfile,
)

# API Schema
from app.schemas import RiskCheckRequest, RiskCheckResponse, RuleHitInfo

# 第三方
import ulid          # 有序唯一 ID 生成
from sqlalchemy ...  # 异步 ORM
```

---

## 3. 工具函数

> 纯计算，无副作用，无 DB 依赖，可直接单元测试。

### 3.1 `_generate_id(prefix: str = "") -> str`

**作用**: 生成带前缀的有序唯一 ID。

**实现**: `prefix + ulid.new().str.lower()` — ULID 保证时间有序 + 全局唯一。

**用法**:

```python
event_id      = _generate_id("evt")   # → "evt01j...abc123"
assessment_id = _generate_id("ast")   # → "ast01j...def456"
case_id       = _generate_id("cas")   # → "cas01j...ghi789"
```

**前缀约定**:

| 前缀 | 用途 |
|------|------|
| `evt` | 事件记录 (risk_event) |
| `ast` | 评估记录 (risk_assessment) |
| `cas` | 案件记录 (risk_case) |

---

### 3.2 `_score_to_level(score: int) -> str`

**作用**: 评分 → 风险等级（描述性标签，用于展示/审计）。

**映射表**:

| 分数区间 | 返回值 |
|----------|--------|
| `< RISK_PASS_THRESHOLD` (默认 30) | `"低"` |
| `< RISK_MARK_THRESHOLD` (默认 60) | `"中"` |
| `< RISK_REVIEW_THRESHOLD` (默认 80) | `"高"` |
| `≥ 80` | `"极高"` |

**用法**:

```python
level = _score_to_level(75)  # → "高"
level = _score_to_level(85)  # → "极高"
```

---

### 3.3 `_score_to_decision(score: int) -> str`

**作用**: 评分 → 决策动作（操作性标签，决定业务流程）。

**映射表**:

| 分数区间 | 返回值 | 后续动作 |
|----------|--------|----------|
| `< 30` | `"通过"` | 直接放行 |
| `< 60` | `"标记"` | 放行但留底 |
| `< 80` | `"人工审核"` | 建案，人工介入 |
| `≥ 80` | `"拒绝"` | 建案，自动拒绝 |

**用法**:

```python
decision = _score_to_decision(75)  # → "人工审核"
decision = _score_to_decision(85)  # → "拒绝"
```

> **注意**: `_score_to_level` 和 `_score_to_decision` 共用同一组阈值，但语义不同：level 是定性描述，decision 是操作指令。

---

### 3.4 `calculate_final_score(hits: list[RuleHitResult]) -> int`

**作用**: 核心评分公式 — 单条取最高分，多条叠加惩罚。

**公式**: `min(max(各规则分) + BONUS × (额外命中数), 100)`

- `BONUS` = `settings.RISK_MULTI_RULE_BONUS`（默认 3）
- 含义：命中多条规则 → 风险更高 → 在最高分基础上累加

**示例**:

```python
# 1 条命中 [70]              → 70 + 3×0 = 70
# 3 条命中 [70, 40, 20]      → 70 + 3×2 = 76
# 3 条命中 [95, 80, 70]      → 95 + 3×2 = 101 → 上限 100
# 0 条命中 []                → 0
```

**用法**:

```python
score = calculate_final_score(rule_hits)  # → 0-100 的整数
```

---

### 3.5 `check_veto(hits: list[RuleHitResult]) -> bool`

**作用**: 一票否决 — 任意一条规则的 `risk_level == "极高"` 即返回 True。

**当前"极高"级别规则**（3 条）:

| 规则 ID | 触发条件 |
|---------|----------|
| R002 | 单笔订单金额 ≥ 10000 |
| R007 | 30 天内订单 ≥ 30 笔 |
| R015 | 退款率 ≥ 80% |

**用法**:

```python
if check_veto(rule_hits):
    # 强制拒绝逻辑
```

**实现细节**: 使用 `any()` 短路求值，遇到第一个极高就返回，不遍历剩余。

---

## 4. 上下文数据类

### `_RiskCheckContext` (dataclass)

**作用**: 流水线各步骤共用的中间数据容器（Context Object Pattern）。

**字段**:

| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `request` | `RiskCheckRequest` | API 入参 | 原始请求，全程只读 |
| `user_id` | `str` | `request.user_id` | 用户 ID |
| `order_id` | `Optional[str]` | 步骤 1 补全 | 步骤 3-4 需要 |
| `receive_id` | `Optional[str]` | 步骤 1 补全 | 地址 ID |
| `event_id` | `str` | 步骤 2 生成 | 后续 3 张表的 FK |

**用法**: 各步骤读/写 ctx 的字段，避免函数参数爆炸。

---

## 5. 步骤 1：准备上下文

### 5.1 `_build_context(request: RiskCheckRequest) -> _RiskCheckContext`

**作用**: API 请求 → 内部 `_RiskCheckContext`，补全 `order_id`。

**业务规则**:

| event_type | source_id 含义 | order_id 来源 |
|------------|---------------|---------------|
| `"下单"` / `"支付"` | 订单号 | 直接用 `source_id` |
| `"售后申请"` | 售后单号 | 从 `request.order_id` 取 |
| `"物流投诉"` | 投诉单号 | 从 `request.order_id` 取 |

**用法**:

```python
ctx = _build_context(request)
# ctx.order_id 保证不为 None（下单/支付场景）
```

---

### 5.2 `_enrich_receive_id(db, ctx) -> None`

**作用**: 从 `OrderInfo` 表补全 `receive_id`（收货地址 ID）。

**退出条件**（任一满足即跳过）:
- `ctx.receive_id` 已有值
- `ctx.order_id` 为 None（售后/投诉没有订单号）

**用法**:

```python
await _enrich_receive_id(db, ctx)
# ctx.receive_id 已填充（如果可查）
```

---

## 6. 步骤 2：创建事件记录

### `_create_event_record(db, ctx) -> str`

**作用**: 写入 `risk_event` 表，返回 `event_id`。

**写入字段**:

| 字段 | 值 |
|------|-----|
| `event_id` | `"evt" + ULID` |
| `event_type` | `ctx.request.event_type` |
| `event_source_id` | `ctx.request.source_id` |
| `user_id` | `ctx.user_id` |
| `event_data` | `request.event_data` 转 JSON 字符串（含中文） |

**用法**:

```python
event_id = _create_event_record(db, ctx)
# event_id 也被写入 ctx.event_id，后续步骤通过 ctx 引用
```

> **注意**: 此时只 `db.add()` 未 commit，event_id 需等 `db.flush()` 后才对后续 INSERT 可见。

---

## 7. 步骤 3-4：特征计算与快照

### 7.1 `_compute_features(db, ctx) -> dict`

**作用**: 调用 `feature.py` 的 `compute_all_features` 计算 **25 维风控特征**。

**3 类特征**:

| 类别 | 前缀 | 数量 | 说明 |
|------|------|------|------|
| 用户特征 | `user_*` | ~10 维 | 订单总数、退款率、投诉数等 |
| 订单特征 | `order_*` | ~10 维 | 订单金额、商品数量等 |
| 地址特征 | 其他 | ~5 维 | 地址关联订单数、投诉数等 |

**用法**:

```python
features = await _compute_features(db, ctx)
# features = { "user_total_orders": 15, "order_amount": 299.0, ... }
```

---

### 7.2 `_classify_feature_entity(feature_name: str) -> tuple[str, str]`

**作用**: 特征名 → 实体类型分类。

**规则**:

```python
"user_*"   → ("用户", feature_name)
"order_*"  → ("订单", feature_name)
其他        → ("地址", feature_name)
```

**用法**:

```python
entity_type, _ = _classify_feature_entity("user_total_orders")  # → ("用户", "user_total_orders")
entity_type, _ = _classify_feature_entity("address_risk_score") # → ("地址", "address_risk_score")
```

---

### 7.3 `_save_feature_snapshot(db, ctx, features) -> None`

**作用**: 把 25 个特征逐条写入 `risk_feature` 表（审计回溯用）。

**entity_id 填充规则**:

| entity_type | entity_id 取值 |
|-------------|---------------|
| `"用户"` | `ctx.user_id` |
| `"订单"` | `ctx.order_id`，缺失用 `ctx.request.source_id` |
| `"地址"` | `ctx.receive_id`，缺失用 `ctx.user_id` |

**用法**:

```python
_save_feature_snapshot(db, ctx, features)
# risk_feature 表新增 25 行
```

---

## 8. 步骤 5：规则匹配

### `_evaluate_rules(db, ctx, features) -> list[RuleHitResult]`

**作用**: 加载启用规则 + 用特征值匹配，返回命中列表。

**流程**:

1. `load_enabled_rules(db, event_type)` — 从 DB 加载 `is_enabled=True` + event_type 匹配的规则（含"通用"规则）
2. `match_rules(rules, features)` — 逐条对特征的阈值/条件进行判断

**用法**:

```python
hits = await _evaluate_rules(db, ctx, features)
# hits = [RuleHitResult(rule_id="R001", risk_score=70, risk_level="高"), ...]
```

---

## 9. 步骤 6：评分与决策（核心）

### 9.1 `_ml_prob_to_risk_score(prob: float, k: float = 3.0) -> int`

**作用**: XGBoost 的 P(拒绝) 概率 → 0-100 风险分（sigmoid 风格校准）。

**公式**: `risk_score = 100 × (1 - e^(-k × prob))`

**为什么需要校准**: P(拒绝)=0.7 是"拒绝概率 70%"，不能直接当"风险分 70"。必须把概率空间映射到风险分空间，然后才能跟规则分做加权平均。

**校准对照表 (k=3)**:

| P(拒绝) | 校准后风险分 | 含义 |
|---------|-------------|------|
| 0.0 | 0 | 无风险 |
| 0.1 | 26 | 低风险，但有信号 |
| 0.3 | 59 | 中风险 |
| 0.5 | 78 | 中高风险 |
| 0.7 | 90 | 高风险 |
| 0.9 | 97 | 极高风险 |
| 1.0 | 100 | 确信拒绝 |

**特点**: 指数饱和函数 — 低概率被压低（避免误报），高概率被推高（强化高风险信号）。

**用法**:

```python
rule_score = 70
ml_raw = 0.7  # XGBoost 输出
ml_calibrated = _ml_prob_to_risk_score(ml_raw)  # → 90，而非 70
```

---

### 9.2 `_calculate_decision(rules, features) -> tuple[int, str, str, float, str]`

**作用**: **步骤 6 主函数**，组合评分、一票否决、双轨融合、结果映射。

**内部流程 (6 小步)**:

```
规则命中列表 → calculate_final_score() → rule_score (0-100)
                                      ↓
                              check_veto() → has_veto?
                              ↓ (是) rule_score 抬到 ≥ 90
                                      ↓
                              XGBoost predict() → ml_score(raw)
                              ↓ sigmoid 校准 → ml_score_100
                                      ↓
                              双轨融合: α×rule + β×ml → final_score
                                      ↓
                              _score_to_level / _score_to_decision → level / decision
                                      ↓
                              has_veto? → 强制 "拒绝" + "极高" + 抬分 ≥ 90
```

**返回值 (5-tuple)**:

| 序号 | 字段 | 类型 | 说明 |
|------|------|------|------|
| 0 | `final_score` | `int` | 0-100 最终风险分 |
| 1 | `risk_level` | `str` | 低/中/高/极高 |
| 2 | `decision` | `str` | 通过/标记/人工审核/拒绝 |
| 3 | `ml_score` | `float` | XGBoost 原始概率 (0-1) |
| 4 | `ml_decision` | `str` | XGBoost 给出的决策标签 |

**双轨融合公式**:

```python
final_score = α × rule_score + β × ml_score_100
# α = settings.ML_WEIGHT_RULE (默认 0.5)
# β = settings.ML_WEIGHT_XGB  (默认 0.5)
```

**一票否决双保险**:

- **第一道** (融合前): `rule_score = max(rule_score, RISK_VETO_MIN_SCORE)` — 确保极高规则推高规则分
- **第二道** (融合后): 若 `has_veto`，强制 `decision="拒绝"` + `level="极高"` + `final_score ≥ 90` — ML 低分无法推翻

**场景示例**:

```
场景: R002 (单笔 10000+) 命中, rule_score=95, ML 给出 0.05 (极低)
  旧逻辑: 融合后 ≈ 50 → "标记" 放行  ← BUG
  新逻辑: has_veto=True → 强制 "拒绝" + 分数 90  ← 修复
```

**用法**:

```python
final_score, risk_level, decision, ml_score, ml_decision = _calculate_decision(hits, features)
```

---

## 10. 步骤 7：落库与响应

### 10.1 `_save_assessment(db, ctx, rules, final_score, risk_level, decision, ml_score, ml_decision) -> str`

**作用**: 写 `risk_assessment` 表，返回 `assessment_id`。

**关键设计**:

- `rule_results` 存 JSON 字符串（每条命中规则的完整信息），用于审计回溯
- `rule_count` 单独存为整数，方便 SQL 聚合查询（`SELECT AVG(rule_count), SUM(rule_count)...`）

**用法**:

```python
assessment_id = await _save_assessment(db, ctx, rules, 76, "高", "人工审核", ml_score=0.3, ml_decision="通过")
```

---

### 10.2 `_maybe_create_case(db, assessment_id, ctx, rules, final_score, decision) -> None`

**作用**: 条件建案 — 仅在 `decision ∈ {"人工审核", "拒绝"}` 时创建 `risk_case`。

**业务规则**:

| decision | 行为 |
|----------|------|
| `"通过"` / `"标记"` | 不建案（event/feature 已留底可回溯） |
| `"人工审核"` | 建案，`case_status="待审核"` |
| `"拒绝"` | 建案，`case_status="已拒绝"`，自动填充 reviewer/review_time |

**去重逻辑**: 同一 `(source_id, event_type)` + 状态为 `("待审核", "审核中")` → 跳过，防止重复建案。

**自动拒绝时的额外动作**:
- `reviewer = "system"`
- `review_time = datetime.now()` — 立即结案
- `review_comment` = 自动生成摘要
- 写一条 `action_log`（`AUTO_REJECT_CASE`），用于审计

**用法**:

```python
await _maybe_create_case(db, assessment_id, ctx, rules, final_score, decision)
```

---

### 10.3 `_update_user_profile(db, ctx, features, final_score, risk_level) -> None`

**作用**: 更新 `risk_user_profile` 表（upsert 模式：有则更新，无则插入）。

**更新的 9 个字段**:

| 字段 | 来源 | 说明 |
|------|------|------|
| `risk_score` | 参数 `final_score` | 最新风险分 |
| `risk_level` | 参数 `risk_level` | 最新风险等级 |
| `total_orders` | `features["user_total_orders"]` | 累计订单数 |
| `total_refunds` | `features["user_refund_count"]` | 累计退款数 |
| `refund_rate` | 计算值 | 退款数/订单数（防 0 除） |
| `avg_order_amount` | `features["user_avg_order_amount"]` | 平均订单金额 |
| `address_count` | `features["user_address_count"]` | 地址数 |
| `complaint_count` | `features["user_complaint_count"]` | 投诉数 |
| `assessment_count` | 自增 `+1` | 累计评估次数 |
| `last_assessment_time` | `datetime.now()` | 最近评估时间 |

**设计优点**: 9 个字段直接从 features 取，不复查 DB，减少查询开销。

**用法**:

```python
await _update_user_profile(db, ctx, features, final_score, risk_level)
```

---

### 10.4 `_build_response(ctx, features, rules, final_score, risk_level, decision, event_id, assessment_id, ml_score, ml_decision) -> RiskCheckResponse`

**作用**: 把内部数据组装成 API 响应（`RiskCheckResponse` Pydantic 模型）。

**脱敏控制**:

```python
features_out = features if settings.RISK_FEATURES_FULL_RETURN else {}
```

- `RISK_FEATURES_FULL_RETURN=True` → 返回全部 25 维特征
- `RISK_FEATURES_FULL_RETURN=False` → 返回空 dict

> **TODO**: 生产环境建议按角色判断（审核员可见全部，普通用户脱敏）。

**用法**:

```python
response = _build_response(ctx, features, rules, 76, "高", "人工审核", event_id, assessment_id, ml_score=0.3, ml_decision="通过")
```

---

## 11. 主函数

### `run_risk_check(db: AsyncSession, request: RiskCheckRequest) -> RiskCheckResponse`

**作用**: **入口函数**，串联整个 7 步流水线。

**完整流程**:

```
RiskCheckRequest
    │
    ▼
[1] _build_context()          → ctx (补全 order_id)
[1] _enrich_receive_id()      → ctx (补全 receive_id)
    │
    ▼
[2] _create_event_record()    → event_id, 写 risk_event
    │
    ▼
[3] _compute_features()       → features dict (25 维)
[4] _save_feature_snapshot()  → 写 risk_feature (25 行)
    │
    ▼
[5] _evaluate_rules()         → rule_hits
    │
    ▼
[6] _calculate_decision()     → final_score, risk_level, decision
    │
    ▼
    db.flush()                 ← event_id 对其他 INSERT 可见
    │
    ▼
[7a] _save_assessment()       → assessment_id, 写 risk_assessment
[7b] _maybe_create_case()     → 条件写 risk_case
[7c] _update_user_profile()   → upsert risk_user_profile
    │
    ▼
    db.commit()                ← 原子提交 (4-5 张表)
    │
    ▼
[7d] _build_response()        → RiskCheckResponse (JSON)
```

**事务保证**: 从步骤 2 开始所有 `db.add()` 都在同一事务内。`db.flush()` 让 event_id 对 FK 可见但不提交；`db.commit()` 一次性提交 4-5 张表。任一步抛异常 → 全部回滚。

**调用示例**:

```python
# 在 router 中调用
from app.engine.decision import run_risk_check

response = await run_risk_check(db, request)
# response.final_score, response.decision, response.triggered_rules ...
```

---

## 12. Demo 自检

文件末尾 `if __name__ == "__main__"` 可直接运行，验证 4 大核心能力，无需数据库：

```bash
python app/engine/decision.py
```

**验证项**:

| # | 验证内容 | 涉及函数 |
|---|---------|---------|
| 1 | 评分 → 等级/决策映射（8 个分数点） | `_score_to_level`, `_score_to_decision` |
| 2 | 规则评分公式（5 组场景） | `calculate_final_score` |
| 3 | 一票否决（2 组场景） | `check_veto` |
| 4 | 双轨融合 + veto 双保险（3 组场景） | `_calculate_decision` |

**适用场景**: 改了评分公式、阈值配置或 veto 逻辑后，先跑这个 demo 确认核心计算没坏。

---

## 13. 数据流图

```
                    ┌──────────────────────────────────────┐
                    │          RiskCheckRequest             │
                    │  user_id, event_type, source_id, ...  │
                    └──────────────┬───────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────┐
                    │         _RiskCheckContext             │
                    │  (user_id, order_id, receive_id...)   │
                    └──────────────┬───────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
   ┌─────────────┐        ┌──────────────┐        ┌──────────────┐
   │ risk_event  │        │   features   │        │    rules     │
   │  (1 行)     │        │  (25 维)     │        │  (命中列表)   │
   └──────┬──────┘        └──────┬───────┘        └──────┬───────┘
          │                      │                       │
          └──────────────────────┼───────────────────────┘
                                 │
                    ┌────────────▼───────────────────────┐
                    │       _calculate_decision()         │
                    │  rule_score + ml_score → final      │
                    │  veto 双保险                         │
                    └────────────┬───────────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
          ▼                      ▼                      ▼
 ┌─────────────────┐   ┌──────────────┐   ┌────────────────────┐
 │ risk_assessment │   │  risk_case   │   │ risk_user_profile  │
 │  (1 行)          │   │  (条件 1 行) │   │  (upsert 1 行)     │
 └────────┬────────┘   └──────┬───────┘   └─────────┬──────────┘
          │                   │                     │
          └───────────────────┼─────────────────────┘
                              │
                 ┌────────────▼────────────┐
                 │   RiskCheckResponse     │
                 │  (final_score, decision,│
                 │   triggered_rules, ...) │
                 └─────────────────────────┘
```

---

## 附录：相关配置项 (.env)

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `RISK_PASS_THRESHOLD` | 30 | 通过/标记 分界线 |
| `RISK_MARK_THRESHOLD` | 60 | 标记/人工审核 分界线 |
| `RISK_REVIEW_THRESHOLD` | 80 | 人工审核/拒绝 分界线 |
| `RISK_VETO_MIN_SCORE` | 90 | 一票否决推分下限 |
| `RISK_MULTI_RULE_BONUS` | 3 | 多规则命中惩罚系数 |
| `ML_WEIGHT_RULE` | 0.5 | 双轨融合规则权重 |
| `ML_WEIGHT_XGB` | 0.5 | 双轨融合 ML 权重 |
| `RISK_FEATURES_FULL_RETURN` | False | 响应是否返回全量特征 |
