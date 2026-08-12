# 前端更新最终交付报告

> 项目：华信银行信贷风控平台（AI_Risk）
> 范围：7 个业务页面更新 + 评审/修复闭环 + 机器验证
> 关联方案：`docs/specs/bank-risk-migration.md`（D7. 前端与 Agent）

---

## 1. 7 个页面改动摘要

| 页面 | 状态 | 改动摘要 |
| --- | --- | --- |
| `dashboard.html` | 已提交（`8a476d6`） | 4 张统计卡改为可点击链接卡（hover 上浮 + 箭头）；初始渲染 shimmer 骨架屏；fetch 失败显示错误横幅（含 detail + 重试）；`window.dashboardChart` 复用前 destroy 防内存泄漏；趋势图 Y 轴 `beginAtZero` + 整数刻度、tooltip 定制、空态占位。 |
| `risk_check.html` | 已修改（未提交） | 业务 ID 校验按事件类型分支（见 §2 初审缺陷 #2 修复）：客户投诉 → `/^\d+$/` 数字记录 ID；还款 → `rp` 前缀；贷款申请/放款 → `LN` 前缀；删除旧 `LN|REP` 合并分支。含案件「重做检查」预填横幅、结果面板、风险/决策徽章渲染。 |
| `rules.html` | 已修改（未提交） | 规则管理重构：分页/分类筛选/每页条数持久化（`pageSize` localStorage）、前端搜索过滤、规则启停 `toggleRule`、条件 JSON 校验（`formatCondition` + 行号定位 `jsonLineOf`）、toast 提示、riskBadge 渲染。 |
| `cases.html` | 已修改（未提交） | 案件工作台：客户 ID 过滤（前端过滤当前页，后端 `user_id` 参数列为后续项）、状态列点击排序、评审确认弹窗（`reviewConfirmModal` + `confirmReview`）、`doReview` 提交评审、SLA 徽章、复制案件 ID。 |
| `blacklist.html` | 已修改（未提交） | 黑名单：跨页批量拉取 + 本地过滤（`fetchAll` + `applyLocalFilters`）、过期态展示（`isExpired`）、新增值校验 `validateValue`/`setValueError`、分页占位。 |
| `assessments.html` | 已修改（未提交） | 评估页：决策汇总条（`renderDecisionSummary`）、CSV 导出（`exportAssessmentsCSV`，含 BOM 与字段转义）、评估重检（`recheckAssessment` 预填跳转）。 |
| `chat.html` | 已修改（未提交） | AI 助手：本页样式移入 `{% block extra_css %}`（见 §2 初审缺陷 #1 修复）；Markdown 渲染（`escapeHtml` → `renderInline`/`renderTable`/`renderMarkdown`）；快捷指令 `sendQuick`；清空确认 `confirmClear`；消息复制 `copyMessage`；流式输出 `renderStreamedReply`、错误气泡。 |

> 说明：`dashboard.html` 的改动已在先前提交 `8a476d6` 落地；其余 6 页为本次待提交的工作区改动（1644 增 / 558 删，含 `tests/test_bank_pages.py`）。

---

## 2. 评审闭环

### 初审：发现 2 个缺陷

1. **chat.html 样式块上下文错误**：页面专属样式（错误气泡 / 元信息 / Markdown 元素）原先放置位置不当，脱离正确继承上下文。
2. **risk_check.html 投诉事件业务 ID 校验缺失**：`ck_source_id` 未按事件类型区分校验，旧 `LN|REP` 合并分支会把还款 `rp01..` 类 ID 误拦截。

### 修复

- **缺陷 #1**：chat 页面样式移入 `{% block extra_css %}`（chat.html L3–32），`base.html` 在 L140 提供该块（`{% block extra_css %}{% endblock %}`）。jinja 渲染确认 `style-in-output: True`，样式确实注入到输出 HTML。
- **缺陷 #2**：`ck_source_id` 按事件类型分支校验——
  - 客户投诉 → `/^\d+$/`（对应 `ComplaintRecord.record_id` 整数）；
  - 还款 → `/^rp/i`（对应 `_rid('rp')` = `rp` + ULID）；
  - 贷款申请/放款 → `/^LN/i`（对应 `f'LN{i:06d}'`）。
  - 与后端 `validator._EVENT_SOURCE_VALIDATORS` 语义一致；旧 `LN|REP` 合并分支已删除（grep = 0）。

### 复审：通过

复审结论：`{"verdict":"pass","reason":"修复符合上轮评审。"}`。要点：

- DOM/JS 绑定完整：chat 的 7 个 `getElementById` 与声明 id 全部对应；risk_check 的 11 个引用与声明 id 及 `id+'_error'` 动态拼接均存在。
- `sendQuick` / `confirmClear` / `renderMLScoreBlock`（定义于 `static/app.js`）均可达。
- 9 tests 通过。
- XSS 面改善：内容先 `escapeHtml` 再 markdown 渲染，链接属性无法逃逸。
- 残余低险：`renderMarkdown` 的 `isTableRow` 对含 `|` 的普通文本行可能误判为表格（纯外观，非正确性）；两点均为既有模式，非本次新引入，无阻塞。

---

## 3. 机器验证结果

```
warnings.warn(PytestDeprecationWarning(_DEFAULT_FIXTURE_LOOP_SCOPE_UNSET))
.........                                                                                                                   [100%]
9 passed in 0.07s
```

```
---jinja---
style-in-output: True
```

- 9 个测试全部通过（含新增回归用例 `test_risk_check_source_id_event_aware`：投诉数字 ID / 还款 `rp` 前缀 / 贷款申请 `LN` 前缀，且断言不残留 `LN|REP`）。
- jinja 渲染验证：chat 页 `style-in-output: True`，确认样式块修复生效。

---

## 4. 待办

- **公共文件改动是否实施**：`base.html` / `static/app.js` 的改动（如决策徽章类、toast 样式等）是否仍需落地，需与需求方确认。当前各页内联自带了部分同类样式（如 riskBadge、showToast），是否收敛为公共资产待定。

---

## 附

- 相关实现说明见 `docs/specs/bank-risk-migration.md`（D6/D7 前端与 Agent 语义银行化）。
- AGENTS.md 约定：如需变更源码/配置以支持上述待办，超出本文档范围，需单独提交任务。