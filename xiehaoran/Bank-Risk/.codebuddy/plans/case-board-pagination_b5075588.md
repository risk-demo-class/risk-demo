---
name: case-board-pagination
overview: 为案件管理页面增加与后端联动的分页功能，包括每页条数选择、分页导航及总条数信息展示。
todos:
  - id: pagination-state
    content: 在 CaseBoard.tsx 增加 page/pageSize 状态并改造 load 函数
    status: completed
  - id: pagination-ui
    content: 添加每页条数选择、总数提示与受控 Table 分页
    status: completed
    dependencies:
      - pagination-state
  - id: build-verify
    content: 构建前端并重启服务验证分页功能
    status: completed
    dependencies:
      - pagination-ui
---

## 用户需求

在案件管理（CaseBoard）页面增加与后端联动的分页功能，参考源项目截图样式。

## 产品概述

当前案件列表已支持状态筛选，但分页为前端固定 `pageSize: 10`，未与后端分页参数联动。本次需实现完整的分页控件。

## 核心功能

- 页码切换：表格底部分页条支持上一页/下一页/指定页跳转。
- 每页条数选择：提供 `每页 20 条` 等选项的下拉框。
- 总数提示：在分页条附近显示 `共 X 条，当前 X 条/页`。
- 筛选与分页联动：切换状态筛选或每页条数时重置到第 1 页，翻页时保留当前筛选条件。

## 技术栈

- 前端：React + TypeScript + Ant Design + Tailwind CSS
- 后端：FastAPI（分页接口已就绪：`/api/cases?page=&page_size=&status=&active_only=`）

## 实现方案

在 `CaseBoard.tsx` 中新增受控分页状态 `page`、`pageSize`，改造 `load` 函数将当前页码与每页条数随筛选参数一起传给 `api.cases`。Ant Design `Table` 的 `pagination` 改为受控对象，绑定 `current`、`pageSize`、`total`、`showSizeChanger`，并通过 `onChange` 与 `onShowSizeChange` 更新状态后重新拉取数据。页码切换时仅刷新列表，不重新请求统计卡片。

## 目录结构

```
web/src/pages/CaseBoard.tsx   # [MODIFY] 增加 page/pageSize 状态、分页控件、与 load 联动
```

## 实现注意事项

- 后端 `CaseListResponse` 已返回 `total/page/page_size`，直接用于 `Table` 的 `pagination.total`。
- 切换筛选条件或每页条数时重置到第 1 页，避免当前页码超出新总页数。
- 保持现有行点击打开详情的交互不变。
- 默认每页条数对齐截图使用 20 条。