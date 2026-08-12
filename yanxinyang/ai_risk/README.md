# 智学安·教育风控平台（教学版）v3.0

一套**零第三方依赖**的完整教育风控系统，严格按《教学宝典_AI_Risk完整架构与模块设计》实现，面向**在线学习与考试平台**。只要有 Python 3.10+ 就能跑：Web 框架、模板引擎、XGBoost、前端图表全部手写，`pip install` 一次都不需要。

> 场景定位：考试 / 作业 / 选课 / 成绩申诉四类学习事件的全链路风险识别（学术诚信、刷课、代考、账号盗用、成绩申诉欺诈等）。

---

## 快速开始

```bash
cd ai_risk
python scripts/init_db.py          # ① 建 25 张表 + 灌 30 条预置规则（教育场景）
python scripts/gen_risk_data.py    # ② 生成演示数据（用户/学习记录/事件/案件）
python scripts/train_xgb_model.py  # ③ 训练 XGBoost（纯 Python 实现）
python _run.py                     # ④ 启动
```

打开 <http://127.0.0.1:8000/> 即是控制台，<http://127.0.0.1:8000/docs> 是 API 目录。

> 用 PyCharm 的话：直接右键 `_run.py` → Run 即可，无需配置解释器参数。

---

## 五层架构

```
L1 Routers   app/routers/*.py      10 个 router / 30 个 API 端点
L2 Service   app/service/*.py      流水线编排、事务边界、校验
L3 Engine    app/engine/*.py       特征计算、规则引擎、双轨融合、XGBoost
L4 Models    app/models.py         25 张表 DDL + 数据字典
L5 Agent     app/agent/*.py        8 个工具的智能助手（SSE 流式）
```

支撑设施同样是手写的：

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| Web 框架 | `app/framework.py` | 类 FastAPI 的路由/依赖/异常体系，底层 `http.server` |
| 模板引擎 | `app/template.py` | 迷你 Jinja2（`{{ }}` / `{% for %}` / `{% if %}`） |
| 数据库 | `app/database.py` | SQLite + 连接池 + 事务上下文 |
| XGBoost | `app/engine/xgboost_mini.py` | 纯 Python 同构 GBDT，可加载官方原生 JSON |
| 前端框架 | `web/static/js/core.js` | 683 行 hyperscript + 组件库，无 React/Vue |
| 前端图表 | `web/static/js/charts.js` | 纯 SVG 折线/柱状/条形/环形/迷你线/评分表盘 |

---

## 7 步流水线

`POST /api/risk/check` 在**单个事务**内跑完 7 步，任一步失败整体回滚：

```
① 请求校验（6 个 ensure_*）   → 事件类型 / 用户存在 / 单号匹配 / 归属 / 关联账号 / 金额防篡改
② 构造上下文 ctx              → 一次性把用户、学习记录、关联账号捞齐，后面不再查库
③ 补全关联账号
④ INSERT risk_event
⑤ 计算 25 维特征              → 14 用户 + 8 学习 + 3 账号，落 risk_feature 快照
⑥ 规则引擎匹配                → 30 条规则 / 14 个算子 / 逐节点求值轨迹
⑦ 双轨融合 + 一票否决         → final = α×规则分 + β×模型分，极高 → max(final, 90)
```

响应里带齐教学材料：`timeline`（每步耗时）、`validate_checks`（6 项校验明细）、
`fusion_steps`（4 步融合公式）、`features` + `feature_defs`（25 维值与定义）、`hit_rules`。

### 打分与决策

```
规则分 = 最高分 + 3 × 额外命中数（上限 100）      例：R001(70) + R003(40) → 73
模型分 = XGBoost 概率 × 100
融合分 = α × 规则分 + β × 模型分                （默认 α = β = 0.5）
一票否决：命中"极高"规则 → final = max(final, 90)
```

| 融合分 | 等级 | 决策 | 建案 |
| --- | --- | --- | --- |
| < 30 | 低 | 通过 | — |
| 30 ~ 60 | 中 | 标记 | — |
| 60 ~ 80 | 高 | 人工审核 | ✔ |
| ≥ 80 | 极高 | 拒绝 | ✔ |

**优雅降级**：模型未加载时权重自动归一化为 α=1.0 / β=0.0（纯规则），规则分不会被腰斩，业务永不停。

---

## 规则引擎

- **30 条预置规则**，6 大类：学术诚信 / 学习行为 / 账号安全 / 成绩异常 / 设备风险 / 身份风险
- **4 条否决规则**（`risk_level = 极高`）：R002、R015、R020、R030
- **14 个算子**：`> >= < <= == != in not_in between not_between exists and or not`
  （`and` / `or` / `not` 递归嵌套，任意深度）
- 未知字段判不命中，绝不抛异常打断流水线
- `POST /api/rules/test` 是规则测试器：给条件 + 特征，返回**逐节点求值轨迹**，新增/改规则前可预演

---

## 案件状态机

5 个状态、7 条边的白名单，非法流转返回 400：

```
待审核 ──┬─→ 审核中 ──┬─→ 已通过（终态）
         │            ├─→ 已拒绝（终态）
         │            └─→ 已关闭（终态）
         ├─→ 已关闭
         ├─→ 已拒绝
         └─→ 已通过
```

超过 `CASE_TIMEOUT_HOURS`（默认 24h）的案件可由 `POST /api/cases/auto-close` 自动关闭，
支持 `dry_run` 预演。审核结论会回写 `label`，作为模型下一轮训练的标注来源。

---

## 前端控制台（12 个页面）

SPA + hash 路由，零第三方库、零 CDN。

| 分组 | 页面 | 内容 |
| --- | --- | --- |
| 监控 | 风控大盘 | 20 项指标 + 4 个分布图 + 趋势折线 + 告警清单 + TOP 规则/用户 |
| | 实时检测 | 触发一次检查，可视化 7 步流水线、6 项校验、4 步融合、25 维特征、命中规则 |
| | 评估历史 | 1400+ 条记录检索，详情含特征快照与关联案件 |
| 处置 | 案件中心 | 工作台 + 状态机图 + 合法流转按钮 + 操作日志 |
| | 规则引擎 | 30 条规则管理 + 14 算子文档 + 规则测试器（求值轨迹） |
| | 黑名单 | 5 类名单增删、命中统计、过期标识 |
| 洞察 | 用户画像 | 画像列表 + 业务统计 + 事件时间线 + 决策分布 |
| | 业务数据 | 25 张表数据字典 + 原始数据浏览（白名单保护） |
| | AI 助手 | SSE 流式对话，8 个工具，展示思考/调用/结果 |
| 系统 | 模型中心 | 模型状态 + 3 种特征重要性 + 热加载/卸载 |
| | 配置中心 | 5 组配置只读展示（决策阈值/融合参数/告警阈值等） |
| | 审计日志 | 2000+ 条操作留痕 + 变更前后对比 |

---

## 测试

```bash
python tests/run_all.py                      # 一键跑全部（推荐）
python -m unittest tests.test_core -v        # 34 例单元测试，不需要启服务
python -m unittest tests.test_api -v         # 24 例 API 集成测试，需先 python _run.py
node tests/smoke_pages.js                    # 12 页前端渲染冒烟，需先启服务
```

覆盖范围：

- `tests/test_core.py` — 14 算子与递归逻辑、融合公式与降级归一化、一票否决、
  4 档决策阈值、5 态 7 边状态机、25 维特征定义自洽、6 个 ensure_* 校验
- `tests/test_api.py` — 30 端点连通、7 步流水线字段完整性、非法入参拒绝、
  规则测试器 13 组算子断言、状态机流转与终态拦截、SSE 事件序列
- `tests/smoke_pages.js` — Node 手写最小 DOM 桩加载全部 7 个前端 JS，
  逐页调用 `window.Pages[key](view)` 抓运行时错误（不需要浏览器）

当前状态：**34 + 24 + 12 全部通过**，`GET /api/system/health` 自检 10/10。

---

## 配置

改项目根目录 `.env` 后重启即可（不改代码），全部项见 `GET /api/system/config`：

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `RISK_PASS_THRESHOLD` | 30 | 低 / 通过的上界 |
| `RISK_MARK_THRESHOLD` | 60 | 中 / 标记的上界 |
| `RISK_REVIEW_THRESHOLD` | 80 | 高 / 人工审核的上界 |
| `RISK_VETO_MIN_SCORE` | 90 | 一票否决的保底分 |
| `ML_WEIGHT_RULE` / `ML_WEIGHT_XGB` | 0.5 / 0.5 | 双轨权重 α / β |
| `CASE_TIMEOUT_HOURS` | 24 | 案件超时自动关闭 |
| `XGB_ENABLED` | true | 关掉即降级为纯规则 |

AI 助手默认走**本地意图路由**（无需任何密钥即可演示 8 个工具）。
若要接真实大模型（如硅基流动 Qwen/Qwen3-8B），在 `.env` 配 `LLM_API_KEY` 即可切换。

---

## 目录结构

```
ai_risk/
├── _run.py                 启动引导（sys.path / 控制台编码 / 日志）
├── app/
│   ├── api.py              10 个 router 的 re-export 中心
│   ├── config.py           配置 + 分组文档
│   ├── database.py         SQLite 连接池 + 事务
│   ├── framework.py        手写 Web 框架
│   ├── models.py           25 张表 DDL + 数据字典
│   ├── template.py         迷你模板引擎
│   ├── agent/              L5：8 个工具 + SSE 对话
│   ├── engine/             L3：特征 / 规则 / 融合 / XGBoost
│   ├── routers/            L1：10 个 router
│   └── service/            L2：流水线 / 校验 / 案件 / 审计
├── scripts/
│   ├── init_db.py          建表 + 灌 30 条规则
│   ├── gen_risk_data.py    演示数据生成
│   ├── train_xgb_model.py  模型训练
│   └── main.py             应用装配 + 前端页面路由
├── tests/                  单元 / 集成 / 前端渲染测试
├── web/
│   ├── static/css/         base.css（设计系统） + pages.css（页面样式）
│   ├── static/js/          core / charts / pages-* / app
│   └── templates/          index.html（SPA 外壳）
├── data/ai_risk.db         SQLite
├── models/xgb_model.json   模型（官方原生 JSON 格式）
└── logs/server.log         轮转日志
```
