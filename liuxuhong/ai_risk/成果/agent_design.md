# agent_design.md — 用 LLM 协作完成教育风控系统改造

> 本文件记录：如何用 LLM（Claude Code）以 vibe coding 节奏，把电商风控系统完整改造成教育风控系统。包含协作流程、提示词模板、迭代过程与关键决策。

---

## 1. 协作模式总览

**不是手写所有代码，而是：LLM 产出 → 人审验 → 跑通验证 → 迭代修正。**

改造在**复用边界**约束下进行：

| 模块 | 处理方式 |
|---|---|
| 风控核心 9 张表 schema | **完全复用**，一行不改 |
| 风控引擎 4 个核心 | **框架复用**（decision/rule/ml_model 逻辑不动），只换业务内容 |
| 决策流水线（7 步） | **完全复用** |
| 业务表 / 特征 / 规则 / 数据 | **LLM 全部重写**（教育行业） |
| 前端 / 文档 / Docker | 部分复用，业务字段改 |

**核心契约**（不可改）：
```python
process_event(RiskCheckRequest(event_type, source_id, user_id, event_data)) → RiskCheckResponse
```

---

## 2. 使用的 LLM 协作流程（5 步循环）

```
① 探索理解  →  ② LLM 生成  →  ③ 跑通验证  →  ④ 发现问题  →  ⑤ LLM 修复  → 循环
```

### 第 ① 步：探索理解（人 + LLM 一起）
- 人：说明任务书要求（C 教育行业、6 张表、8 条规则、val_auc≥0.7）
- LLM：读现有电商代码，画复用边界表，明确"哪些复用、哪些重写"

### 第 ② 步：LLM 生成（vibe coding 核心）
按依赖顺序批量产出：
1. `sql/init_business_tables.sql` — 6 张教育表 DDL
2. `app/models_business.py` — SQLAlchemy ORM（与 DDL 一致）
3. `app/engine/feature.py` — 25 维教育特征
4. `sql/init_risk_data.sql` — 16 条教育规则
5. 3 个造数脚本 + 1 个训练脚本
6. 前端模板 / 文档

### 第 ③ 步：跑通验证（必须，防止 LLM 幻觉）
```bash
python scripts/init_db.py --reset --yes        # 建表 + 数据 + 规则
python scripts/gen_business_data.py            # 造业务数据
python scripts/gen_risky_users.py --count 30   # 造高风险用户
python scripts/gen_train_dataset.py --reset    # 造训练集
python scripts/train_xgb_model.py              # 训练 + val_auc
python run_app.py                              # 启动验证页面/API
```

### 第 ④ 步：发现问题（LLM 自查 + 测试锁死）
真实遇到的问题（见第 4 节），逐个交给 LLM 定位根因。

### 第 ⑤ 步：LLM 修复 → 回归验证
每修一个 bug，跑一次全量测试 + 关键链路验证，防止改坏别处。

---

## 3. 提示词模板（可直接复用）

### 3.1 业务理解（任务 1）
```
我要做一个 教育行业的风控系统，业务层跟电商完全不同。
请帮我调研这个行业的典型欺诈场景、关键业务字段、事件类型，
输出 1 页纸业务说明。注意要符合国内监管要求。
```

### 3.2 业务表设计（任务 2）
```
这是我的业务说明: <粘贴任务1产出>。
请帮我设计 6 张教育业务表 schema，写 SQLAlchemy 模型 + DDL，
设计字段/关联/索引时要考虑后续风控特征计算的便利。
同时写一个 Python 造数脚本，至少造 100 条业务数据。
```

### 3.3 特征 + 规则 + 训练（任务 3）
```
这是我的业务表 + 数据: <粘贴 schema + 样例数据>。
请帮我设计 3 大特征族（用户/订单/地址），字段映射到教育行业，
写 compute_*_features 函数。同时调研教育行业典型欺诈套路，
设计 8 条业务规则，跑通 XGBoost 训练。训练后用 val_auc 和 val_f1 评估。
```

### 3.4 约束类提示词（贯穿全程）
```
风控核心 9 张表 schema 不许改；决策流水线 7 步不许改流程；
RiskCheckRequest/RiskCheckResponse 契约不能改；
业务表/特征/规则/数据生成全部按教育行业重写。
```

---

## 4. 真实迭代过程（关键决策 + 踩坑记录）

### 4.1 复用边界确认（最重要决策）
**问题**：电商 17 张业务表 vs 教育 6 张，差异巨大；但风控 9 张表是通用审计/规则表。
**决策**：风控表 schema 完全复用（只改 enum 枚举值），业务表全部重写。
**理由**：风控引擎/流水线/训练都依赖这 9 张表的结构，改了要连带改几十个文件。

### 4.2 事件类型语义设计
**问题**：电商 `下单/支付/售后申请/物流投诉` 与教育业务对不上。
**决策**：教育 4 种事件 `课程报名/退费申请/学历认证/直播打赏`，并重新设计 source_id 语义：
- 课程报名：`source_id = order_id`
- 退费申请：`source_id = refund_id`
- 学历认证/直播打赏：`source_id = user_id`（认证/打赏对象是用户本人）

### 4.3 黑名单类型扩展
**问题**：电商只有 `用户/地址/手机号`，教育需要学号/身份证/设备指纹。
**决策**：5 种类型 `用户/学号/身份证/设备指纹/直播账号`，检查顺序：用户 > 学号 > 设备指纹 > 直播账号（短路）。

### 4.4 特征语义重映射（25 维保持）
**问题**：XGBoost 固定 25 维，如何塞进教育语义？
**决策**：保持维度数，重写每维含义：
- `user_total_orders` → `user_total_enrollments`（报名数）
- `order_is_night` → `order_enroll_hour`（报名时间）
- `addr_is_new` → `addr_is_new_device`（新设备）

**关键**：`ml_model.FEATURE_COLUMNS` 与 `feature.py` 顺序严格对齐，有测试锁死（`test_feature_columns_align`）。

### 4.5 XGBoost 模型特征不匹配
**问题**：旧的 `xgb_model.json` 是电商特征训练的，教育特征推理时报 `feature_names mismatch`。
**决策**：不修代码，直接重造数据 + 重训模型（旧模型是垃圾，重训才对）。

### 4.6 数据生成脚本踩坑
| 问题 | 根因 | 修复 |
|---|---|---|
| `用户ID不存在: ORD_007_22` | 学历认证事件的 source_id 误用 order_id，validator 按 user_id 校验 | 学历认证/打赏 source_id 改为 user_id |
| `Settings has no attribute DB_URL` | backfill 脚本用错配置属性 | 改用 `settings.get_database_url_async()` |
| backfill 查 risk_event 不存在的列 | 脚本按电商 risk_event 结构写 SQL | 改为 `event_source_id/event_type` |
| Windows GBK 编码崩 | 脚本打印 emoji（⚠️） | 脚本开头 `sys.stdout.reconfigure(encoding="utf-8")` |
| pytest Temp 权限 (WinError 5) | 系统 Temp 残留目录被锁 | `tests/conftest.py` 默认 `--basetemp=.pytest_tmp` |

### 4.7 训练集正负比控制
**问题**：随机造数据正例 < 5%，模型假收敛。
**决策**：`gen_train_dataset.py` 用 RISK 用户 → 退费申请（~80% 正例）+ 普通用户 → 课程报名（~3% 正例），混合后正负比 ~50%。
**实测**：1250 条，正例 52.6%，val_auc=1.0。

### 4.8 测试同步更新
**问题**：原 90 个测试锁定电商语义（旧事件类型/特征名/黑名单类型），改造后大量失败。
**决策**：
- 更新锁定通用逻辑的测试（决策公式/规则引擎/特征对齐/XGBoost）
- 更新锁定旧枚举值的测试（schemas/黑名单/事件阈值）
- 整体标记 skip 电商遗留测试（force_picker，引用了已删表）
- 修复硬编码项目路径的测试（`Path(__file__)` 替代旧绝对路径）

---

## 5. 质量保障手段

| 手段 | 说明 |
|---|---|
| 全量测试 | 444 passed，改造后持续回归 |
| 特征对齐测试 | 锁死 `FEATURE_COLUMNS` ↔ `feature.py` 顺序 |
| 假收敛检测 | 训练后检查 best_iter / val_auc / val_f1，防止模型没学到 |
| 正负分离度 | 回填后验证正例 avg ml_score 远大于负例 |
| 端到端验证 | init_db → 造数 → 训练 → 启动 → 页面/API 全链路 |
| 契约测试 | RiskCheckRequest 4 事件类型 + 规则枚举校验 |

---

## 6. 给学生的协作建议

1. **先画复用边界，再让 LLM 动手**——明确"哪些不许动"是 vibe coding 成功的 80%
2. **每轮让 LLM 产出"可跑的最小单元"**，而不是一次性全量（SQL 先跑通，再模型，再特征）
3. **跑通验证不要省**——LLM 幻觉（引用不存在的列/属性）只能靠真跑暴露
4. **测试是锁死契约的工具**——改造后更新测试，防止 LLM 后续改坏
5. **保留每个任务的提示词**——它们是可以复用的 prompt 资产
