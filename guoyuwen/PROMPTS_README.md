# 银行风控重构 `/goal` 提示词使用说明

这套提示词用于把电商版 `AI_Risk` 重构成银行风控教学项目，并重新设计一套银行风控前端。四个目标必须按顺序执行，每次只粘贴一份提示词。

## 固定路径与默认选择

- 当前新项目工作区：`D:\Program Files\temp_data\Projects\SGG_projects\risk-control`
- 只读基线项目：`D:\Program Files\temp_data\Projects\SGG_projects\sgg_AI_RISK_demo`
- 任务书：`D:\Program Files\temp_data\尚硅谷大模型项目之风控系统\AI_Risk_行业风控实战任务书.md`
- 数据库：`bank_risk`
- 测试数据库：`bank_risk_test`
- 银行事件：`登录`、`转账`、`贷款申请`、`绑卡`
- GitHub 仓库默认名：`ai-risk-bank`
- GitHub 可见性：`private`

如果默认仓库名已被占用，Goal 1 必须停止并报告，不得覆盖已有仓库，也不得擅自换名。

## 执行顺序

1. 打开 [`prompts/01-goal-业务理解与基线.md`](prompts/01-goal-业务理解与基线.md)，复制其中完整提示词并发送。
2. 用 `/goal` 查看状态，等待 Goal 1 达到停止条件并核对交付物。
3. 推荐在同一工作区中为 Goal 2 新建一个对话，复制下一份完整提示词；Goal 3、Goal 4 同理。四个 Goal 必须串行，前一阶段未验收、提交并推送时不要启动下一阶段。
4. 如果选择在同一个对话中继续，先用 `/goal clear` 清除已完成目标，再发送下一份提示词；目标暂停时，处理阻塞条件后使用 `/goal resume`。

## 每个 Goal 使用独立对话

- 可以，而且推荐一个 Goal 对应一个新对话：每个阶段的结果和验收边界更清楚，也能减少长上下文干扰。
- 新对话必须打开同一个本地项目工作区，并先读取仓库中的 `AGENTS.md`、`PROMPTS_README.md`、`docs/goal-progress.md` 和上一阶段产物。对话记录与 `/goal` 状态不会自动继承，已提交文件、Git 历史和项目说明才是跨对话交接依据。
- 最稳妥的节奏是：上一 Goal 验收完成 → 更新进度文档 → 提交并推送 → 确认工作区干净 → 新建对话执行下一 Goal。不要让两个 Goal 同时修改同一工作树。
- 如果新对话由 Codex 自动创建了独立 worktree 或新分支，必须先确认上一 Goal 的提交已经合并或当前分支能够看到它；本套提示词默认在同一 `main` 工作树上串行执行。

官方用法参考：[OpenAI Docs：Follow a goal](https://learn.chatgpt.com/use-cases/follow-goals)。如果客户端没有 `/goal`，可在 Codex 配置中启用 `features.goals`，或在 CLI 执行 `codex features enable goals`。

## 文件清单

- `01-goal-业务理解与基线.md`：导入只读基线、完成银行业务说明与前端设计简报、创建私有 GitHub 仓库。
- `02-goal-银行数据层.md`：实现 8 张银行业务表、数据、配置与校验。
- `03-goal-pipeline规则与训练.md`：实现 25 维银行特征、规则、完整流水线、XGBoost 与全新的银行风控前端。
- `04-goal-演示文档与面试.md`：完成前端统一打磨、README、演示材料、面试问答和最终验收。

## 重要说明

- 这些文件只是执行提示词；创建它们不会启动目标、复制旧项目或创建 GitHub 仓库。
- Goal 1 导入旧项目时必须保留本文件和整个 `prompts/` 目录。
- 四份提示词已经授权目标内的正常本地编辑、非破坏性验证、阶段提交，以及向新建的私有仓库推送。任何删除真实数据库、覆盖已有 GitHub 仓库或修改只读基线的行为仍然禁止。
- 不主动调用或检查 Superpowers 插件技能；只有用户在当次消息中使用完整 `$superpowers:<skill-name>` 格式时才允许调用。
