# 规则引擎详细说明 — `app/engine/rule.py`

## 文件定位

> **5 层架构的 Engine 层，决策流水线的 Step 5。**

```
run_risk_check()  ← decision.py 的 7 步流水线
  │
  ├─ Step 3: feature.compute_all_features()  → 算出 25 个特征
  │
  ├─ Step 5: _evaluate_rules()              → ★ 这里调用 rule.py
  │      │
  │      ├─ load_enabled_rules()   → 从数据库加载启用的规则
  │      └─ match_rules()          → 用特征值匹配每条规则的条件
  │
  ├─ Step 6: _calculate_decision()  → 用命中结果算分
```

---

## 1. 业务层面

### 1.1 业务目的是什么？

一句话：**拿之前算好的 25 个特征值，跟数据库里配置的每一条规则的条件做对比，判断哪些规则"命中"了。**

核心逻辑：

```
规则 R005 的条件: {"field": "order_is_night", "op": "==", "value": 1}
特征: {"order_is_night": 1, "order_total_amount": 588, ...}
→ 命中！→ 记录这条规则，供 Step 6 算分用

规则 R001 的条件: {"field": "order_total_amount", "op": ">=", "value": 10000}
特征: {"order_total_amount": 588, ...}
→ 没命中（588 < 10000）
```

规则引擎本身不做评分决策，它只回答一个问题：**"当前这笔请求的特征，触发了哪些规则？"** 至于触发了之后怎么算总分、怎么决策，那是 `decision.py` Step 6 的事。

### 1.2 谁在调用它？在什么场景下调用？

有两个调用入口：

**① `load_enabled_rules()` — 从数据库加载规则**

被 `decision.py` 的 Step 5 `_evaluate_rules()` 调用：

```python
# decision.py:229-234
async def _evaluate_rules(db, ctx, features):
    rules = await load_enabled_rules(db, event_type=ctx.request.event_type)
    return match_rules(rules, features)
```

调用链路：`run_risk_check()` → `_evaluate_rules()` → `load_enabled_rules()` + `match_rules()`

**场景：** 每次风控检查请求的 Step 5。

**② `match_rules()` + `evaluate_condition()`**

在测试文件（`tests/test_rule_engine.py`）和 rule.py 自己的 `__main__` demo 中直接调用。

### 1.3 如果这个函数返回空结果，业务上意味着什么？

分两种情况：

**情况 1：`load_enabled_rules()` 返回空列表**

意味着数据库里**没有启用的规则**（所有规则的 `is_enabled=0` 或全部被软删）。业务影响：

- Step 6 的 `calculate_final_score([])` 返回 **0 分**
- `check_veto([])` 返回 `False`（没有一票否决）
- 最终决策极大概率是 **"通过"**
- 这相当于 **风控系统形同虚设**，所有请求都会放行

> 如果忽然发现所有请求都变成了"通过"，第一反应就该去查 `risk_rule` 表是不是被人把规则全禁了。

**情况 2：`match_rules()` 返回空列表**

数据库里有规则，但**当前这笔请求的特征不满足任何一条规则的条件**。业务影响：

- 同样得 0 分，决策为"通过"
- 但这**不一定有问题** — 正常用户的正常订单本来就应该 0 分

**区分这两种情况很重要：** 情况 1 是系统故障，情况 2 是正常业务。

---

## 2. 技术层面

### 2.1 为什么用这种方式实现？有没有其他选择？

当前方案是 **自研的 JSON 条件表达式引擎**，递归求值。

| 方案 | 优点 | 缺点 |
|------|------|------|
| ✅ **当前方案：JSON 条件表达式** | ① 存在数据库里，运行时加载，**不需要重启服务就能改规则**<br>② 支持嵌套 AND/OR，表达能力够用<br>③ 零依赖，就一个 Python 文件 | 复杂逻辑（比如跨特征运算、正则匹配）需要拆多条规则 |
| ❌ 硬编码 if/else | 性能最好 | 改了规则要改代码、重启服务、重新部署 |
| ❌ Drools 等规则引擎 | 功能强大 | 太重了，Java 生态，跟 Python 项目不搭 |
| ❌ 自己写 AST 解析器 | 灵活 | 过度设计，当前需求 JSON 就够了 |

**关键决策：规则存在数据库里而不是代码里。** 这是最重要的设计决策：

- 业务人员可以通过 API 或 SQL 直接加规则，不需要开发改代码
- 规则可以热加载（不用重启服务）
- 每条规则有 `is_enabled` 开关，可以随时关掉某条规则而不用删数据

### 2.2 设计考虑

#### 可扩展性（首要）

```python
def _compare(actual: float, op: str, value: Any) -> bool:
    if op == ">":     return actual > float(value)
    elif op == ">=":  return actual >= float(value)
    elif op == "<":   return actual < float(value)
    elif op == "<=":  return actual <= float(value)
    elif op == "==":  return actual == float(value)
    elif op == "!=":  return actual != float(value)
    elif op == "in":  return actual in [float(v) for v in value]
    elif op == "not_in": return actual not in [float(v) for v in value]
    elif op == "between":
        low, high = float(value[0]), float(value[1])
        return low <= actual <= high
```

要加一个新运算符（比如 `regex`、`startswith`），只改 `_compare` 一个函数，加一行即可。

#### 容错性

整个文件到处是 try/except，**任何一条规则坏了都不影响其他规则**：

```python
# 情况 A：规则 JSON 解析失败 → 跳过这条规则，不影响其他规则
try:
    condition = rule.condition_dict
except (json.JSONDecodeError, TypeError):
    continue

# 情况 B：特征不存在（比如某条规则引用了不存在的特征名）
actual = features.get(field)
if actual is None:
    return False    # 算"没命中"，不抛异常

# 情况 C：比较运算异常（比如 value 不是数字）
try:
    return _compare(actual, op, value)
except Exception as e:
    return False    # 算"没命中"，不影响流程
```

三种容错分别对应：**数据坏了** / **配置错了** / **类型不对**，各自有独立的 logger 级别（WARNING / DEBUG / WARNING），方便排查。

#### 性能

当前规则数量很少（30 条），每次请求循环 30 次做条件求值，**性能可以忽略不计**。

如果以后规则涨到几千条，才需要考虑优化：
- 加缓存：规则变动很少，可以缓存起来不用每次都查 DB
- `load_enabled_rules()` 已经按 `event_type` 过滤，只加载匹配当前事件类型的规则

### 2.3 隐患和坑

#### 隐患 1：`load_enabled_rules()` 每次请求都查数据库

```python
async def load_enabled_rules(db, event_type=None):
    stmt = select(RiskRule).where(
        RiskRule.is_enabled == 1,
        RiskRule.deleted_at.is_(None),
    )
    if event_type:
        stmt = stmt.where(RiskRule.event_type.in_([event_type, "通用"]))
    stmt = stmt.order_by(RiskRule.priority.desc())
    return list((await db.execute(stmt)).scalars().all())
```

规则平时基本不变，但每次请求都去数据库查一次。如果请求量很大（QPS > 1000），这是一个不必要的数据库压力。

**建议优化方案：** 加一个本地缓存（比如 `functools.lru_cache` 或 `dict`），设置过期时间 60 秒。规则变动时由 API 主动失效缓存。

#### 隐患 2：`RuleHitResult` 从 ORM 对象拷字段

```python
class RuleHitResult:
    def __init__(self, rule: RiskRule):
        self.rule_id = rule.rule_id       # 拷出 7 个字段
        self.rule_name = rule.rule_name
        self.rule_category = rule.rule_category
        self.risk_level = rule.risk_level
        self.risk_score = rule.risk_score
        self.action = rule.action
        self.description = rule.description
```

这是**故意设计的**。ORM 对象 `RiskRule` 在 `db.commit()` 之后可能变成 `detached` 状态（脱离 session），但 `RuleHitResult` 是普通 Python 对象，不受 session 影响。后续的评分、落库、响应都用 `RuleHitResult` 而不是 ORM 对象。

**反过来说：** 如果要在 `RuleHitResult` 里加一个新字段（比如 `rule_tag`），需要同步改 4 个地方：`__init__`、`to_dict()`、`_save_assessment()` 的 JSON 序列化、`_build_response()` 的 `RuleHitInfo` 构造。

#### 隐患 3：`evaluate_condition()` 的类型转换

```python
# _compare 里把所有 value 转成 float：
return actual > float(value)
```

- JSON 里的 `10000` 被 `json.loads` 解析成 `int`，`float(10000)` 没问题
- 如果在 JSON 里写了字符串 `"10000"`，`float("10000")` 也能转
- 如果写了 `"abc"`，`float("abc")` 会抛异常，但被 try/except 兜底成 `False`

**注意：** `in` 和 `not_in` 操作符里的列表元素也会被 `float()` 转换。如果规则条件是 `{"op": "in", "value": ["a", "b"]}`，`float("a")` 会报错，整条规则变成 False。

#### 隐患 4：`match_rules` 输出顺序

返回的命中列表**保持加载时的顺序**（按 `priority DESC`）。但后续 `calculate_final_score()` 只取 `max(risk_score)`，**不依赖顺序**。

如果以后有"优先级高的规则覆盖优先级低的规则"的需求（比如 R001 和 R002 都命中时只记 R002），需要在这里加去重逻辑。

#### 隐患 5：`load_enabled_rules` 没有超时保护

如果数据库连接出现问题，`await db.execute(stmt)` 可能挂住。虽然 `db` 是外部传进来的 session，但 `load_enabled_rules` 自己没有加超时。如果数据库慢查询导致整个请求卡住，会影响所有请求。

---

## 3. 上下游关联

### 3.1 调用链路总图

```
run_risk_check()  ← decision.py
  │
  ├─ Step 3: features = await compute_all_features(...)
  │     输出: dict[str, float]  (25 个特征)
  │
  ├─ Step 5: rules = await _evaluate_rules(db, ctx, features)
  │     │
  │     ├─ load_enabled_rules(event_type)  → 从 DB 加载启用的规则
  │     │    返回: list[RiskRule]
  │     │
  │     └─ match_rules(rules, features)   → 逐条匹配
  │          返回: list[RuleHitResult]
  │
  ├─ Step 6: _calculate_decision(rules, features)
  │     ├─ calculate_final_score(hits)     → int 分数
  │     ├─ check_veto(hits)                → bool
  │     └─ ml_model.predict(features)      → XGBoost 评分
  │
  └─ Step 7: 落库
        ├─ _save_assessment()    → rule_results (JSON), rule_count
        ├─ _maybe_create_case()  → risk_detail (JSON), case_category
        └─ _build_response()     → triggered_rules (前端展示)
```

### 3.2 调用之前需要准备什么

| 前置条件 | 由谁保证 | 为什么 |
|----------|---------|--------|
| `features` 必须有 25 个特征 | Step 3 `feature.compute_all_features()` | 规则条件是针对特征写的，特征不全会导致某些规则永远不命中 |
| `event_type` 必须是合法值 | Step 0 Pydantic 校验 + Step 1 Validator | 如果传了不存在的 event_type，`load_enabled_rules` 只查"通用"规则，可能漏掉事件特定的规则 |
| DB 里必须有启用的规则 | `init_db.py` 初始化时插入了 30 条 | 如果规则表是空的，`load_enabled_rules` 返回空列表，所有请求都通过 |
| 规则不能是软删状态 | `load_enabled_rules` 自己加了 `WHERE deleted_at IS NULL` | 软删的规则不会被加载，也不会参与匹配 |
| `db` session 必须有效 | `get_db_async()` 依赖注入 | 如果 session 已关闭或连接断开，查询会抛异常 |

### 3.3 调用后数据流向哪里

```
match_rules() 返回 [RuleHitResult, ...]
      │
      ▼
_calculate_decision(rules, features)    ← decision.py Step 6
      │
      ├─ calculate_final_score(hits)     ← 取 max(每条 risk_score) + 3×额外命中数
      │     → 返回 0-100 的整数分数
      │     → 传给 _build_response() 作为 final_score
      │
      ├─ check_veto(hits)                ← 检查是否含"极高"级别规则
      │     → 返回 True/False
      │     → True 时强制决策为"拒绝"，分数抬到 ≥90
      │
      ├─ _save_assessment()              ← Step 7a 写 risk_assessment 表
      │     → rule_results: JSON 字符串，存每条命中规则的完整详情
      │     → rule_count: 命中条数（给 SQL 聚合用）
      │
      ├─ _maybe_create_case()            ← Step 7b 条件建案
      │     → risk_detail: JSON 字符串，存命中规则（用于案件详情展示）
      │     → case_category: 命中最多的规则分类（订单欺诈/支付风险/...）
      │
      └─ _build_response()               ← Step 7d 返回前端
            → triggered_rules: 每条命中规则的 ID/名称/分类/级别/分值/动作
```

### 3.4 下游消费者汇总

| 下游 | 消费什么字段 | 用途 |
|------|------------|------|
| `decision.py` 评分公式 | `risk_score` | 算总分 `max + 3 × (规则数-1)` |
| `decision.py` 一票否决 | `risk_level` | 检查是否包含"极高"级别 |
| `risk_assessment.rule_results` | 全部 7 个字段 (JSON) | 审计回溯，事后查"当时命中了哪些规则" |
| `risk_assessment.rule_count` | 列表长度 | SQL 聚合统计（平均命中数/分布） |
| `risk_case.risk_detail` | 全部 7 个字段 (JSON) | 案件详情页展示 |
| `risk_case.case_category` | `rule_category` | 案件归类（取命中最多的分类） |
| 前端 `triggered_rules` | 全部 7 个字段 | 风控检查结果页展示 |
| 仪表盘聚合查询 | `rule_count` + `rule_category` | 命中率统计、规则效果评估 |

### 3.5 修改影响范围

| 改什么 | 影响范围 | 严重程度 |
|--------|---------|---------|
| **加新运算符**（如 `regex`、`contains`） | 只改 `_compare()`，加一行代码 | ⚪ 低风险 |
| **改 `RuleHitResult` 字段**（加新字段） | ① `__init__` 拷字段<br>② `to_dict()`<br>③ `_save_assessment()` JSON<br>④ `_build_response()` `RuleHitInfo`<br>⑤ `_maybe_create_case()` risk_detail | 🟡 中风险（改 5 个地方） |
| **改 `load_enabled_rules()` 逻辑**（加缓存） | 只改这一个函数，返回值不变，下游不受影响 | ⚪ 低风险 |
| **改 `evaluate_condition()` 求值逻辑** | 影响**所有**规则的命中结果 → 影响评分 → 影响决策 → 影响训练数据标签 | 🔴 **高风险！** |
| **改规则条件格式**（比如改 JSON schema） | ① `evaluate_condition()` 解析逻辑<br>② 数据库里所有已有规则的条件 JSON 要迁移<br>③ Rule API 的创建/更新接口要改<br>④ `init_risk_data.sql` 里的 30 条预置规则要改 | 🔴 **高风险！** |

**最重要的影响关系：**

规则引擎的输出直接决定 **XGBoost 训练数据的标签**（规则判定为"人工审核"/"拒绝"的算正例，"通过"/"标记"的算负例）。如果改了规则匹配逻辑：

1. 以前打好的标签就变了（同一个请求，旧规则判"通过"，新规则可能判"拒绝"）
2. 以前训好的 XGBoost 模型跟新的规则体系不匹配
3. 必须用新的规则体系**重新生成训练数据** → **重新训练模型**

这是整个系统里最需要注意的上下游关联。

---

## 附录：支持的条件运算符

| 运算符 | 示例 | 含义 |
|--------|------|------|
| `>` | `{"field": "score", "op": ">", "value": 80}` | 大于 |
| `>=` | `{"field": "amount", "op": ">=", "value": 5000}` | 大于等于 |
| `<` | `{"field": "score", "op": "<", "value": 30}` | 小于 |
| `<=` | `{"field": "orders", "op": "<=", "value": 1}` | 小于等于 |
| `==` | `{"field": "is_night", "op": "==", "value": 1}` | 等于 |
| `!=` | `{"field": "is_new", "op": "!=", "value": 0}` | 不等于 |
| `in` | `{"field": "category", "op": "in", "value": [3, 5, 7]}` | 在列表里 |
| `not_in` | `{"field": "status", "op": "not_in", "value": [0, 1]}` | 不在列表里 |
| `between` | `{"field": "amount", "op": "between", "value": [3000, 8000]}` | 在闭区间内 |

**逻辑组合：**

```json
{"and": [条件1, 条件2, ...]}   → 全部满足才命中
{"or":  [条件1, 条件2, ...]}   → 任一满足即命中
```

支持无限嵌套：

```json
{"and": [
    {"or": [
        {"field": "a", "op": ">", "value": 10},
        {"field": "b", "op": ">", "value": 20}
    ]},
    {"field": "c", "op": "==", "value": 1}
]}
```

---

## 附录：数据库预置规则（30 条）

| 类别 | 数量 | 典型规则 |
|------|:----:|---------|
| 订单欺诈 | 5 | R001 (≥5000 标记) / R002 (≥10000 拒绝, 极高) / R003-005 |
| 支付风险 | 4 | R006 (7 天 10 单) / R007 (30 天 30 单, 极高) / R008-009 |
| 账户风险 | 4 | R010 (退款率 ≥30%) / R015 (≥80%, 极高) / R011-014 |
| 售后滥用 | 3 | R012 (退款次数 ≥5) / R016-017 |
| 地址风险 | 4 | R018 (多省份) / R019-021 |
| 物流风险 | 3 | R022 (投诉 ≥3) / R023-024 |
| 通用规则 | 7 | R025-R030 (跨事件类型) |