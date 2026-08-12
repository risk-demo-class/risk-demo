---
name: AI助手欢迎语与快捷指令改造
overview: 参考源项目 AI_Risk 的 AI 助手排版，改造 Bank-Risk 的 AgentChat 欢迎语（改为任务清单式 + "请问有什么需要帮助的?"），并增加银行风控域的快捷指令按钮。
design:
  architecture:
    framework: react
  styleKeywords:
    - 企业级金融控制台
    - 浅色卡片气泡
    - 主色描边 Chip
    - 简洁对齐
  fontSystem:
    fontFamily: PingFang SC
    heading:
      size: 18px
      weight: 600
    subheading:
      size: 14px
      weight: 500
    body:
      size: 13px
      weight: 400
  colorSystem:
    primary:
      - "#1677FF"
      - "#722ED1"
    background:
      - "#F0F2F5"
      - "#FFFFFF"
    text:
      - "#262626"
      - "#8C8C8C"
    functional:
      - "#52C41A"
      - "#FF4D4F"
      - "#FA8C16"
todos:
  - id: update-welcome
    content: 修改 AgentChat.tsx 初始欢迎语为银行风控任务清单式多行文本
    status: completed
  - id: add-quick-chips
    content: 在 AgentChat.tsx 输入区上方新增快捷指令 Chip 并绑定 send()
    status: completed
    dependencies:
      - update-welcome
  - id: build-verify
    content: npm run build 构建前端，重启 Bank-Risk 验证 AI 助手页欢迎语与快捷指令
    status: completed
    dependencies:
      - add-quick-chips
---

## 用户需求

当前 Bank-Risk「AI 风控助手」页欢迎语过于简单（单行提示），要求参考源项目 AI_Risk 的聊天页排版，改为多任务清单式欢迎语，并新增快捷指令入口，使提示更专业、可控、贴合银行风控语义。

## 核心改造点

- 欢迎语改为任务清单式：列出可完成的 5 类风控任务（风险检查/案件/用户画像/仪表盘统计趋势/黑名单），并以「请问有什么需要帮助的?」收尾。
- 输入框上方增加快捷指令按钮（Chip），点击即填入并发送，参考源项目 chat.html 的 sendQuick 行为（今日统计/待审案件/用户画像/规则分析/趋势分析）。
- 银行语义对齐：将源项目的「对用户/订单进行风险检查」转为「对账户/交易进行风险检查」。
- 保持现有 `api.agentChat` 调用逻辑、会话 management、消息渲染结构不变。

## 技术栈

- 前端：React 18 + TypeScript + Vite + Ant Design 5（Bank-Risk 现有 web 工程，FastAPI 托管 web/dist）
- 状态：组件内 useState/useRef（无额外状态库）

## 实现方案

1. **修改欢迎语**：在 `web/src/pages/AgentChat.tsx` 的初始 `msgs` 状态中，将单行 `content` 替换为多行任务清单字符串（保留 `whitespace-pre-wrap` 渲染即可正确换行）。银行语义版本：

```
你好！我是银行风控 AI 助手，可以帮你完成以下任务：

- 对账户/交易进行风险检查
- 查询和分析风控案件
- 查看用户风险画像
- 查看仪表盘统计和趋势
- 管理黑名单
请问有什么需要帮助的？
```

2. **新增快捷指令**：在输入框上方渲染一组 Ant Design `Tag`/`Button` 组成的 Chip 行（如「今日统计」「待审案件」「用户画像」「规则分析」「趋势分析」）。点击处理逻辑复用现有 `send(text)` 函数——将预设问题设为 input 并直接调用 `send()`。
3. **最小化改动**：仅修改 `AgentChat.tsx` 单文件；不改动 `api.ts`、`chat.py`、路由或其它页面，避免回归。

## 实现要点（防回归）

- 复用现有 `send` 函数，快捷指令仅构造 `text` 后调用 `send(text)`；不要重复实现 fetch 逻辑。
- 快捷指令文案与银行域现有接口能力一致（`/api/dashboard/overview`、`/api/cases`、`/api/profile/{id}`、`/api/rules`、`/api/assessments` 均可被 Agent 工具覆盖，无需新增后端）。
- 欢迎语使用 `\n` 换行 + 现有 `whitespace-pre-wrap`，无需额外富文本组件。

## 架构与文件结构

仅改动一个文件：

```
web/src/pages/AgentChat.tsx   # [MODIFY] 初始欢迎语改为任务清单；新增快捷指令 Chip 行并绑定 send()
```

## 设计风格

沿用现有 Bank-Risk 控制台风格（左侧深色 Sider + 白色顶栏 + 浅灰内容区），AI 助手页保持卡片式聊天区。欢迎语气泡采用现有 AI 气泡样式（白底描边、紫色机器人头像），无需重新设计。

## 页面区块（自上而下）

1. 聊天消息区（现有）：首条为改造后的任务清单欢迎气泡。
2. 快捷指令行（新增）：位于输入区上方，一行可换行排列的浅色 Chip 按钮（用 Ant Design `Tag` 或 `Button size="small"` + `type="default"`，主色描边 #1677FF），文案：今日统计 / 待审案件 / 用户画像 / 规则分析 / 趋势分析。
3. 输入区（现有）：文本框 + 发送按钮，回车发送。

## 交互

- 点击快捷指令 Chip：立即将该问题填入并触发发送，气泡进入对话流，体验与源项目一致。
- 移动端/窄屏：Chip 自动换行，不影响布局。