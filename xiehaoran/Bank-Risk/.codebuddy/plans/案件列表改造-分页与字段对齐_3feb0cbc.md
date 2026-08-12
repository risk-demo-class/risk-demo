---
name: 案件列表改造-分页与字段对齐
overview: 按图示改造案件列表：表格列改为 案件ID/用户ID/分类/评分/等级/状态/创建时间/操作（含详情与重做检查）；分页改为底部居中页码 + 顶部左侧每页条数与总数；重做检查调用后端新增接口重新跑风控并生成新评估/案件。
todos:
  - id: backend-recheck
    content: 后端新增 POST /cases/{case_id}/recheck 与 recheck_case 服务（含 event_data 取数）
    status: completed
  - id: api-recheck
    content: 前端 api.ts 增加 recheckCase 封装并确认 CaseDetail 字段
    status: completed
    dependencies:
      - backend-recheck
  - id: columns-align
    content: 重写 CaseBoard 表格 8 列（含创建时间格式化、操作列按钮）
    status: completed
    dependencies:
      - api-recheck
  - id: pagination-ui
    content: 分页改为顶部工具栏（筛选+每页条数+总数）与底部居中页码
    status: completed
    dependencies:
      - columns-align
  - id: recheck-action
    content: 接入重做检查按钮 loading/成功提示/刷新列表
    status: completed
    dependencies:
      - pagination-ui
  - id: build-verify
    content: 构建前端并重启后端验证字段、分页与重做接口
    status: completed
    dependencies:
      - recheck-action
---

## 用户需求

按图示改造案件列表页面（CaseBoard），使表格列、分页布局与图示完全一致，并新增「重做检查」操作。

## 产品概述

银行风控系统的案件看板页面，展示案件列表并提供审核、重做检查能力。本次调整仅涉及前端表格列定义、分页布局，以及后端新增「重做检查」接口（生成新评估/案件记录）。

## 核心功能

- 表格字段严格按图示：案件ID、用户ID、分类、评分、等级、状态、创建时间、操作
- 操作列包含「详情」（打开审核弹窗）与「重做检查」（发起一次新风控检查，生成新评估/案件）
- 分页布局按图示：表格底部居中显示页码与快速跳页；表格上方左侧显示筛选下拉、「每页 X 条」下拉、「共 X 条，当前 a-b 条/页」总数提示
- 后端新增 `POST /api/cases/{case_id}/recheck`，使用案件原始事件数据重新调用风控引擎，生成新 event/assessment，并在决策为 reject/freeze 时生成新案件，返回新检查结果

## 技术栈

- 前端：React + TypeScript + Ant Design（现有项目 web 目录，已用 antd Table/Card/Select/Modal）
- 后端：FastAPI + SQLAlchemy（async），现有 app 目录，已具备 process_event 风控管道
- 复用现有：`api.cases / caseDetail / reviewCase`、后端 `process_event(db, RiskCheckRequest)`、`get_case_detail`

## 实现方案

### 策略

1. 后端新增「重做检查」端点：在 `routers/case.py` 增加 `POST /{case_id}/recheck`，经 `service/case.py` 的 `recheck_case` 取案件的 event_type/user_id/source_id 及关联 RiskEvent.event_data，组装 `RiskCheckRequest` 调用 `process_event`，返回 `RiskCheckResponse`。该路径完全复用既有风控管道，不新增业务分支，保证评分/决策/建案逻辑一致。
2. 前端 `CaseBoard.tsx` 重写 Table 列与分页：列对齐图示（含创建时间格式化、操作列按钮）；分页拆分为顶部工具栏（筛选 + 每页条数 + 总数）与底部居中页码（`position: ['bottomCenter']`，仅页码 + 快速跳页）。
3. 前端 `api.ts` 增加 `recheckCase(case_id)` 封装，并在 `CaseItem` 确保 `create_time` 可用（已有）。

### 关键技术决策

- 重做检查生成新记录而非更新原案件：符合用户澄清，且 `process_event` 对 reject/freeze 会自动建案（`_maybe_create_case` 按 source_id+event_type 去重，仅当无在办案件时才建，避免重复建案）。
- 为构造重做请求，后端 `get_case_detail` 需要返回关联 event_data；计划确认 `CaseDetailResponse`/schema 是否已含，若缺则补充 event_data 字段（仅透传，不破坏现有详情弹窗）。
- 分页采用「顶部自定义工具栏 + 底部居中页码」而非 Table 内置双 position：图示顶部仅显示每页条数与总数、无页码，内置 `position:['topLeft','bottomCenter']` 会在顶部也渲染页码，不符合图示，故用自定义工具栏控制。

## 实现注意事项

- 后端 `recheck_case` 需 join `RiskAssessment`→`RiskEvent` 取得 `event_data`；若 `event_data` 为 NULL，用空对象 `{}` 兜底，避免 `process_event` 报空。
- 前端创建时间格式化：`create_time` 为字符串/Date，需格式化为 `YYYY/M/D HH:mm:ss`（与图示一致），空值显示「-」。
- 案件ID 渲染：长 ID 截断（CSS `max-width` + `ellipsis`）并加 `title` 完整值 tooltip，与图示一致。
- 重做检查按钮需 `loading` 态防重复点击；成功后 `message.success` 并 `load(filter, 1, pageSize)` 刷新（回到第 1 页避免越界）。
- 移除原「事件」列，不改变统计卡片与详情弹窗结构，控制改动面。

## 架构设计

数据流：用户点击「重做检查」→ `api.recheckCase(case_id)` → `POST /api/cases/{case_id}/recheck` → `recheck_case` → 组装请求 → `process_event`（新建 event/assessment/可能建案）→ 返回结果 → 前端 toast + 刷新列表。
列表渲染：筛选/每页条数变化 → `load()` → `api.cases(params)` + `api.caseStatistics()` → Table 受控分页底部居中。

## 目录结构

```
app/
├── routers/case.py        # [MODIFY] 新增 POST /{case_id}/recheck 路由，调用 recheck_case
├── service/case.py        # [MODIFY] 新增 recheck_case：取案件关联 event 数据并调用 process_event 返回 RiskCheckResponse；确认 get_case_detail 透传 event_data
└── schemas.py             # [MODIFY] 如 CaseDetailResponse 缺少 event_data 则补充该字段（供重做检查使用，不影响现有详情）

web/src/
├── api.ts                 # [MODIFY] 新增 recheckCase(case_id) 封装（POST /api/cases/{case_id}/recheck）
└── pages/CaseBoard.tsx    # [MODIFY] 重写 Table 列（8 列 + 操作）、分页改为顶部工具栏 + 底部居中页码、新增重做检查按钮逻辑
```

## 关键代码结构

```ts
// web/src/api.ts 新增
recheckCase: (caseId: string) => post<RiskCheckResponse>(`/cases/${caseId}/recheck`),

// app/routers/case.py 新增
@case_router.post("/{case_id}/recheck", response_model=RiskCheckResponse)
async def api_recheck_case(case_id: str, db: AsyncSession = Depends(get_db_async)):
    return await recheck_case(db, case_id)
```

## Agent Extensions

### Skill

- brainstorming
- Purpose: 在动手实现前再次确认改造要点（列定义、分页布局、重做检查行为）已与用户意图对齐
- Expected outcome: 确保计划覆盖用户图示与澄清结论，避免返工

### SubAgent

- code-explorer
- Purpose: 深入确认 `schemas.py` 中 `CaseDetailResponse` 是否已含 event_data，以及 `RiskEvent` 关联路径，避免后端改动遗漏
- Expected outcome: 明确 schema 改动范围与 recheck_case 取数 SQL 写法