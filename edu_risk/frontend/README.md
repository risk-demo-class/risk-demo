# EduRisk 前端控制台

针对 `edu_risk`（教育行业 AI 风控系统）后端生成的管理控制台前端。
纯 HTML/CSS/JS，**零构建、零外部依赖**（图表为手写 SVG），开箱即用。

## 目录结构

```
frontend/
├── index.html      # 页面骨架：侧边栏 + 顶栏 + 10 个功能页 + 弹窗/Toast
├── css/style.css   # 浅色主题样式（风险色：低绿/中橙/高深橙/极高红）
└── js/
    ├── core.js     # API 客户端（base 可配置）+ 通用组件 + SVG 图表
    └── pages.js    # 10 个页面的业务逻辑 + 路由 + 初始化
```

## 快速开始

```bash
# 1. 启动后端（项目根目录，默认端口 8000）
python _run.py

# 2. 启动前端静态服务（本目录，端口 8080）
python -m http.server 8080

# 3. 浏览器访问
#    http://localhost:8080
```

也可以直接用浏览器打开 `index.html`（无需静态服务器；API 地址默认 `http://localhost:8000`，
点左下角「🔌 API 配置」可改，配置保存在 localStorage）。

> 后端已配置 CORS 全放开，前端跨域直连即可。

## 页面功能对照后端 Router

| 页面 | 对应 API | 功能 |
|------|---------|------|
| 📊 运营仪表盘 | `/api/dashboard/stats` `/trend` `/rule-effectiveness` | 统计卡（检查量/待审核/业务量）+ 风险趋势折线 + 决策分布环形 + 规则命中 TOP10 条形 |
| 🔍 风控检查 | `POST /api/risk/check` | 提交 报名/缴费/退费/考试/作业 事件，展示综合分圆环、双轨分数、决策/等级徽章、命中规则表、25 维特征快照 |
| 📋 案件工作台 | `/api/cases` 全套 | 状态筛选、分页、领取（待审核→审核中）、通过/拒绝（填意见）、关闭、超时自动关闭 |
| 📜 规则管理 | `/api/rules` 全套 | 30 条规则列表、按事件类型筛选、启用开关、新建规则（JSON 条件）、规则测试工具（命中判定） |
| 👤 学员画像 | `/api/users/{id}/profile` | 基本信息 + 检查/案件/最高分/平均分 + 风险标签 + 黑名单状态 |
| 🚫 黑名单管理 | `/api/blacklist` 全套 | 加入黑名单（人工/AI/规则）、生效列表、解除 |
| 📡 风控事件 | `/api/events` + `/api/risk/check/{event_id}` | 事件列表、筛选、详情（特征快照 + 评估结果） |
| 🏫 业务数据 | `/api/business/*` | 课程 / 报名 / 缴费 / 退费 / 考试 五个 Tab，支持按学员筛选 |
| ⚙️ 系统设置 | `/api/settings` | 决策阈值、双轨融合权重、告警配置、案件超时、XGB 状态（只读） |
| 🤖 AI 助手 | `POST /api/agent/chat`（SSE） | 流式聊天，解析 `event: tool/text/done/error`；未配置 LLM_API_KEY 时后端自动降级提示 |

## 关键实现说明

- **零依赖图表**：`core.js` 中 `svgLineChart` / `svgDonut` / `svgBars` 手写 SVG 渲染，离线可用。
- **API 地址可配置**：左下角按钮，存 `localStorage['edurisk_api_base']`。
- **SSE 解析**：`fetch` + `ReadableStream` 按 `\n\n` 分帧，支持工具调用记录展示与打字光标。
- **风控检查入参**：`source_id` 必须是业务表中真实存在的单据号（后端校验器强制），
  演示可用 `scripts/gen_edu_data.py` 造出的数据，如 `ENR_xxx` / `PAY_xxx` / `RFD_xxx` / `EXM_xxx`。

## 常见问题

- **页面打开但显示"后端未连接"**：确认 `python _run.py` 已启动（8000 端口），并点击「🔌 API 配置」核对地址。
- **AI 助手提示不可用**：后端 `.env` 未配置 `LLM_API_KEY`，属预期降级；配置后重启后端即可。
- **分页条数**：后端 `list_cases`/`list_events` 返回的 `total` 为当前页条数，前端据此显示"本页 N 条"，不影响翻页。
