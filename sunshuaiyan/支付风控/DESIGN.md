---
name: PingPong Risk Ledger
description: 面向跨境收付审查的高密度风险控制账本
colors:
  ink: "#14201e"
  muted: "#5f6c69"
  line: "#d9e0de"
  line-strong: "#b8c4c1"
  paper: "#f4f7f6"
  surface: "#fbfcfc"
  surface-alt: "#edf2f0"
  accent: "#0b7465"
  accent-strong: "#07594e"
  accent-soft: "#dbece8"
  danger: "#a33a36"
  danger-soft: "#f5e6e4"
  warning: "#86620d"
  warning-soft: "#f4edd8"
typography:
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "25px"
    fontWeight: 720
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "15px"
    fontWeight: 720
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.02em"
rounded:
  compact: "6px"
  control: "8px"
  panel: "14px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "14px"
  lg: "18px"
  xl: "28px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-primary-hover:
    backgroundColor: "{colors.accent-strong}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "14px 16px"
  input:
    backgroundColor: "#ffffff"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 10px"
  status-chip:
    backgroundColor: "{colors.surface-alt}"
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "3px 8px"
---

# Design System: PingPong Risk Ledger

## Overview

**Creative North Star: "跨境支付走廊控制账本"**

系统的视觉世界来自风控分析师的实时控制台，而不是营销网站或通用管理后台。商户、付款人、贸易材料、资金走廊和决策证据被安排成一本可追溯的电子账本。

业务屏幕保持严谨、低噪声和高密度。细边线和色调层叠承担分区，单一青绿色承担操作与正向状态，风险色只在需要审查员介入时出现。

**Key Characteristics:**

- 冷灰纸面、深墨文字和单一青绿操作色。
- 精准表格、细线分区和等宽数字构成账本感。
- 数据决策优先，装饰和运动保持克制。
- 风险证据在当前上下文中展开，不打断案件浏览。

## Colors

色板以冷感纸面中性色为主，青绿作为稀缺操作色，暗红和褐黄仅表示需要干预的风险。具体色值以前置令牌为准。

### Primary

- **走廊青绿** (`accent`, `accent-strong`, `accent-soft`)：主要操作、正常状态、特征权重和链接。

### Neutral

- **深墨** (`ink`)：标题、主值和强调文字。
- **审计灰** (`muted`)：次要信息、字段名和辅助说明。
- **冷纸面** (`paper`, `surface`, `surface-alt`)：页面底色、主数据容器和表头层次。
- **校验线** (`line`, `line-strong`)：分区、输入边界和紧凑表格网格。

### Named Rules

**The One Operational Accent Rule.** 青绿是唯一操作色，不为每个模块发明新颜色。

**The Evidence Severity Rule.** 暗红只用于拒绝、退款、P0/P1 或明确风险值；警示黄用于需补材料或人审状态。

## Typography

**Display Font:** 系统中文无衬线字体栈

**Body Font:** 系统中文无衬线字体栈

**Label/Mono Font:** UI monospace, SFMono-Regular, Menlo, Consolas

**Character:** 标题短促稳定，正文尺寸克制，数值、交易号和风险标识使用等宽字形保持垂直可扫读性。

### Hierarchy

- **Headline:** 页面级标题，中等尺寸和紧字距。
- **Title:** 面板与区域标题，尺寸接近正文但权重更高。
- **Body:** 业务说明、表格内容和状态文字。
- **Label:** 指标值、交易 ID、时间和严重性编码。

### Named Rules

**The Tabular Evidence Rule.** 所有交易 ID、金额、分数和时间使用等宽字体与表格数字特性。

## Layout

桌面端使用 224px 常驻侧边导航，工作区内边距为 28px，主要模块间距为 18px。核心指标在宽屏排成六列，趋势与案件按 1.7:0.8 组成主次工作区。

1180px 以下指标收缩为三列，趋势与案件改为单列。768px 以下隐藏常驻侧边栏，使用 58px 粘性移动顶栏和 offcanvas 导航；工作区内边距收缩为 14px，指标变为两列，宽表格保留水平滚动。

**The Decision-First Grid Rule.** 首屏先放系统状态和六个决策 KPI，其后才是趋势、案件和明细。

## Elevation & Depth

界面默认无阴影。深度通过纸面色阶、1px 边线和清晰的区块包含关系表达；聚焦状态使用青绿透明环，而不是浮起卡片。

**The Flat Ledger Rule.** 面板在静止状态下不使用外部阴影，信息层级由色调和边线提供。

## Shapes

形状语言为轻微圆角的技术工具。主面板使用 14px 圆角，输入和按钮使用 8px，优先级块使用 6px，状态标签使用完全胶囊。边界始终是细线，不使用硬偏移阴影或拟物纹理。

## Components

### Buttons

- **Shape:** 紧凑圆角控件。
- **Primary:** 走廊青绿底色与浅色文字，只承载当前页面主操作。
- **Hover / Focus:** hover 变为深青绿；键盘聚焦显示 3px 半透明青绿环；active 向下移动 1px。
- **Table Action:** 白底细边线，hover 时使用青绿浅底。

### Chips

- **Style:** 默认为中性灰胶囊，通过、拒绝和人审状态分别使用青绿、暗红和褐黄语义色。
- **State:** 状态文字必须完整显示，不只依赖颜色。

### Cards / Containers

- **Corner Style:** 面板圆角，内部的指标或表格使用分割线而非多层嵌套卡片。
- **Background:** 主容器使用冷白表面，表头和次要区域使用浅灰绿色调。
- **Shadow Strategy:** 无阴影，依赖 1px 边线。
- **Internal Padding:** 通常为 14px 到 18px。

### Inputs / Fields

- **Style:** 白底、1px 强分割线、8px 圆角。
- **Focus:** 边线变为青绿，同时显示 3px 半透明聚焦环。
- **Placeholder:** 中性灰且保持可读，不用于代替字段标签。

### Navigation

桌面导航是冷灰纸面上的紧凑工具列。激活项使用冷白底和内描边，文字变为深青绿；移动端使用图标按钮打开 offcanvas，但抽屉内保留完整文字导航。

### Evidence Drawer

风险证据抽屉从右侧进入，宽度不超过 520px。它按联合决策、三组分数、命中规则、关键特征和审计标识的顺序呈现，保持交易上下文不丢失。

### Task Form and Decision Ledger

风险检查与黑名单编辑使用左任务表单、右数据证据的工作区。表单仅保留一个青绿主操作；决策区先显示通过、标记、人审或拒绝，再展开黑名单、规则、模型和审计标识。

### Assistant Workspace

AI 助手使用左侧查询指引和右侧对话账本。用户问题与助手回复使用对称对齐和不同色阶，但不使用额外彩色。对话栏固定在工作区底部，并始终显示本地数据边界与当前运行模式。

## Do's and Don'ts

### Do:

- **Do** 让交易证据、时间、金额和决策比装饰元素更显眼。
- **Do** 用细边线和冷灰色调建立层级，并在 767.98px 断点切换为移动导航。
- **Do** 为加载、空数据、请求失败和审计成功提供明确文字反馈。
- **Do** 保留可见键盘聚焦，并尊重 `prefers-reduced-motion`。

### Don't:

- **Don't** 使用渐变、硬偏移阴影、装饰性浮空卡片或多套主色。
- **Don't** 用只有图标的按钮承载复杂风控操作，也不要只靠颜色区分结果。
- **Don't** 把拒绝、制裁或 P0 的暗红用作普通装饰色。
- **Don't** 把生产宣称或真实客户效果混入合成数据界面。
