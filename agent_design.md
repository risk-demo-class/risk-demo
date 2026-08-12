# Agent Design — Vibe Coding 协作设计

> 任务书要求: 用 LLM (Claude / GPT / Cursor / Trae) 协作产出代码, 不是手写。
> 本文件记录本次制造业风控改写的 AI 协作方式、节奏与复盘。

## 一、协作原则

1. **契约优先**: 先读任务书和基线代码, 锁定不可改的契约
   (`RiskCheckRequest → RiskCheckResponse`、`process_event` 4 步、`run_risk_check` 7 步、9 张核心表),
   再让 AI 在业务层自由发挥。
2. **一次只改一个行业层**: 数据层 → 校验层 → 特征层 → 规则层 → 训练层 → 前端, 每层跑通再进下一层。
3. **验证闭环**: 每层改完立即跑通 (init_db / verify_mfg / pytest / train), 不让错误累积。
4. **统一业务常量**: 事件类型 / 规则分类 / 黑名单类型集中到 `app/config.py`,
   schema / ORM / SQL / 前端 / 测试共用一份语义, 避免"改一处漏三处"。

## 二、四轮迭代 (对应任务书 4 个递进任务)

### 任务 1: 业务理解 (输出 `1-业务说明.md`)

**给 AI 的提示词 (骨架)**:

> 我要做一个制造业风控系统, 业务层跟电商完全不同。请调研经销商订货/设备保修/售后维修的典型欺诈
> 场景、关键业务字段、事件类型, 输出 1 页纸业务说明, 注意符合国内监管要求 (反不正当竞争法/三包规定)。

**AI 产出**: 6 种欺诈场景、16 个关键字段、5 种事件类型、8 个术语 (串货/套保/SN/MSRP/三包…)。

### 任务 2: 数据层 (表 / 造数 / 校验 / 枚举)

**给 AI 的提示词 (骨架)**:

> 这是我的业务说明: <1-业务说明.md>。请设计 7 张业务表 schema (UserInfo/Product/DealerInfo/
> OrderInfo/WarrantyRecord/CrossRegionReport/BlacklistExtra), 写 SQLAlchemy 模型 + DDL,
> 字段/索引要考虑后续特征计算的便利; 同时写一个可重复运行的造数脚本, 至少 100 条业务数据,
> 并且让 13 条规则在样例数据上都能命中。

**关键决策 (人机协同)**:
- 事件类型定为 5 种, 直接映射 `validator.py` 的派发表 (1 张字典表)。
- 黑名单走"核心表用户级 + 行业表业务级"双表设计, 核心 9 表 0 改动。
- 造数脚本支持 `--emit-sql`, 由同一份数据源生成 `sql/init_business_data.sql`, 保证 SQL 与脚本不漂移。

### 任务 3: Pipeline + 训练 (特征 / 规则 / XGBoost)

**给 AI 的提示词 (骨架)**:

> 这是我的业务表和样例数据: <schema + 样例>。请把 3 大特征族 (用户/订单/地址) 映射到制造业,
> 写 compute_*_features; 设计 13 条规则 (任务书 D.2 的 8 条必选 + 5 条补充);
> 跑通 XGBoost 训练, 用 val_auc / val_f1 评估。

**关键决策**:
- 保持 25 维特征总数, 与 `ml_model.FEATURE_COLUMNS` 一一对齐 (训练/推理不错位)。
- 套保识别以"订单最近工单的 SN"做 90 天聚合, 兼顾实现简单与业务可解释。
- 训练数据由规则真实打出 (强标注), val_auc=1.0 属于"规则泄露"的教学产物, README 已注明。

### 任务 4: 演示 + 文档

- `verify_mfg.py` 一键演示 10 个场景 (6 高风险 + 2 黑名单 + 1 大额采购 + 1 正常对照)。
- `gen_risk_data_with_dates.py --days 14` 造跨天趋势数据; `backfill_ml_score.py` 回填 ML 评分。
- README / agent_design 复盘。

## 三、AI 工具使用清单

| 任务 | 用 AI 做什么 | 人工/工具做什么 |
|---|---|---|
| 业务调研 | 输出行业欺诈清单/术语表 | 核对任务书 D 场景与监管边界 |
| Schema 设计 | 生成 ORM + DDL + 索引 | 确认外键依赖顺序、与 9 核心表解耦 |
| 造数 | 生成幂等造数脚本 | 设计"规则必命中"的 RISK 模式数据 |
| 特征 | 生成 25 维特征函数 | 锁特征名与 FEATURE_COLUMNS 对齐 |
| 规则 | 生成 13 条 JSON 规则 | 校准分数/等级/事件类型映射 |
| 前端 | 改事件/黑名单/规则下拉与文案 | 验证页面数据流 |
| 测试 | 重写 12 个行业相关测试 | pytest 全绿 (315 passed) |

## 四、复盘 (经验与坑)

1. **契约先行的价值**: 全程没有碰 `process_event` / `run_risk_check` 的流程,
   迁移成本主要在业务层, 验证回归非常快。
2. **枚举值域是"隐藏 schema"**: event_type / blacklist_type 散在 Pydantic Literal、
   SQLAlchemy Enum、MySQL DDL 三处, 必须集中常量 + 三处同步, 否则 API 校验与 DB 约束打架。
3. **旧模型文件会"静默误导"**: 行业改写后旧 `xgb_model.json` 特征名不匹配,
   加载时校验特征名并判未加载, 避免每条推理刷异常。
4. **Windows 中文编码**: 脚本统一 `sys.stdout.reconfigure(encoding="utf-8")`,
   SQL 文件由生成器 `--emit-sql --out` 直写 UTF-8, 避免控制台管道乱码。
5. **"AI 造的 100%"也要验收**: 每个生成物 (表/规则/数据) 都必须跑通链路再进入下一层,
   验收脚本 `verify_mfg.py` 就是这层保险。
