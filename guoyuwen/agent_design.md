# agent_design.md —— 用 LLM 与四个 `/goal` 协作完成银行风控重构

> 本文说明本仓库如何用 LLM 助手与 `prompts/` 下的四份 `/goal` 提示词，把一个电商风控基线改造成银行风控教学项目。过程事实取自 `docs/goal-progress.md` 与本仓库 Git 历史；没有证据的阶段不做虚构。

## 1. 协作方式概览

项目以“一个人工确认边界 + 一个 LLM 执行助手 + 四份阶段提示词”的方式推进。每份提示词对应一个递进目标，必须在上一目标验收、提交并推送私有仓库后，才能串行开始下一目标（见 [PROMPTS_README.md](PROMPTS_README.md) 的“执行顺序”）。

```text
电商基线 (sgg_AI_RISK_demo)
   │  Goal 1 基线/业务/私有仓库
   ▼
银行方向文档 + 独立 Git + private repo
   │  Goal 2 银行数据层
   ▼
8 张业务表 + 校验层 + 造数
   │  Goal 3 pipeline/规则/XGBoost/前端
   ▼
25 维特征 + 8 控制 + 双轨决策 + 全新前端
   │  Goal 4 演示/文档/面试/最终验收
   ▼
README 可复现 + 浏览器验收 + 演示材料 + 全量验证 + 私有推送
```

四份提示词分别位于 [prompts/01-goal-业务理解与基线.md](prompts/01-goal-业务理解与基线.md)、[prompts/02-goal-银行数据层.md](prompts/02-goal-银行数据层.md)、[prompts/03-goal-pipeline规则与训练.md](prompts/03-goal-pipeline规则与训练.md)、[prompts/04-goal-演示文档与面试.md](prompts/04-goal-演示文档与面试.md)。

## 2. 为什么拆成四个目标

1. **控制单步上下文与风险**：一个目标只改一层（文档→数据→流水线/前端→交付），避免在长对话里同时改业务表、特征、规则和前端导致互相牵连。`PROMPTS_README.md` 明确“每个 Goal 使用独立对话”，对话记录不跨阶段继承，已提交文件、Git 历史和项目说明才是交接依据。
2. **契约先行**：Goal 1 先冻结 9 张核心表、`process_event` 四步、`run_risk_check` 七步、四字段外部契约、`bank_risk`/`bank_risk_test` 库名与 25 维形状（14 `user_*` + 8 `order_*` + 3 `addr_*`），后三个阶段只在不破坏这些契约的前提下施工。Goal 3 提示词把这些列为“绝对不变量”。
3. **验收驱动推进**：每份提示词都给出停止条件（例如 Goal 3 要求四事件全链路、完整 25 维、至少 3 条规则命中、1 个黑名单拒绝、模型双指标达标、双视口浏览器验收），未满足不进入下一阶段。Goal 2 明确“不实现 25 维特征、不写银行规则、不训练模型”。
4. **失败隔离**：每个阶段有独立提交与回归测试，安全修复（`a0db4cd`）作为 Goal 3 之后的独立提交，不混入功能开发。

## 3. 每个目标的输入/输出/验收

| 目标 | 提示词 | 关键输入 | 主要交付 | 验收要点（摘自提示词） |
|---|---|---|---|---|
| Goal 1 | `01-goal-业务理解与基线.md` | 电商基线、任务书、未跟踪银行草稿 | `1-业务说明.md`、`docs/refactor-contract.md`、`docs/frontend-design-brief.md`、`docs/baseline-test-report.md`、独立 Git、私有仓库 `ai-risk-bank` | 独立历史、基线状态不变、官方监管来源、仓库回读为 PRIVATE |
| Goal 2 | `02-goal-银行数据层.md` | Goal 1 文档、契约 | 8 张业务表 ORM + DDL、`gen_business_data.py`、validator 归属校验、聚焦测试 | 8+9 表、≥100 条四事件数据、幂等造数、越权 403、核心 9 表不变 |
| Goal 3 | `03-goal-pipeline规则与训练.md` | Goal 2 数据层 | 25 维特征、7 条规则 + 黑卡、XGBoost、全新前端、`docs/model-evaluation.md`、`docs/frontend-design.md`、8 张截图 | 四事件 25 维、模型 AUC≥0.70/F1≥0.50、双视口浏览器验收、520 测试通过 |
| Goal 4 | `04-goal-演示文档与面试.md` | Goal 3 全部产物 | README 重写、`agent_design.md`、演示脚本与清单、面试问答、`.env.example`、Docker/启动复现、`docs/final-verification.md` | README 可复现、浏览器验收、全量测试、私有推送回读 |

## 4. 核心不可变契约

来源：[docs/refactor-contract.md](docs/refactor-contract.md) 与四份提示词的“不变量/绝对不变量”。

1. **9 张核心风控表**：`risk_rule`、`risk_event`、`risk_feature`、`risk_assessment`、`risk_case`、`risk_blacklist`、`risk_user_profile`、`risk_action_log`、`risk_alert` 的表名与字段契约不变；业务表不得反向要求改这 9 张表。
2. **`process_event` 四步**：业务实体校验 → 补全内部兼容字段 → 黑名单前置检查 → 调用决策引擎。
3. **`run_risk_check` 七步**：准备上下文 → 创建事件 → 计算特征 → 保存特征快照 → 加载并匹配规则 → 计算决策 → 原子落库并响应。
4. **外部契约**：`event_type/source_id/user_id/event_data` 四字段；`order_id/receive_id` 只做内部兼容。
5. **枚举与库名**：事件固定为 `登录/转账/贷款申请/绑卡`；库 `bank_risk`、测试库 `bank_risk_test`。
6. **25 维形状**：14 `user_*` + 8 `order_*` + 3 `addr_*`，顺序即模型 ABI；任何重命名必须原子同步特征、模型、训练、前端标签与测试。
7. **通用引擎职责**：`app/engine/rule.py` 只负责规则解析与匹配，不在其中硬编码银行阈值；`ml_model.py` 保持通用训练/加载/推理算法。

## 5. 关键技术取舍

- **外部四字段 + 内部兼容字段**：银行 API 不新增必填字段，`event.py` 自动用 `source_id` 补全 `order_id`（`decision.py::_build_context`），既保留基线 pipeline 的 7 步钩子，又不把电商字段暴露给调用方。
- **黑名单前置短路**：黑卡场景保留为核心 `risk_blacklist` 前置控制而非规则，命中时 `rule_count=0`、`blocked_by='银行卡号'`、`final_score=100`，与规则/模型拒绝明确区分。文档与前端据此解释“黑卡样例 rule_count=0”。
- **`order_*`/`addr_*` 兼容前缀**：不重命名 25 维列（避免训练/推理错位），`order_*` 解释为“本次银行事件”，`addr_*` 解释为“设备/IP/地理环境”，中文 UI 用真实银行语义（`static/app.js::FEATURE_LABELS`）。
- **标签由规则/决策产生 + 用户级切分**：训练标签 `通过/标记→0`、`人工审核/拒绝→1`；用 `GroupShuffleSplit(user_id)` 切分防止同用户事件同时落在训练/验证两侧（`docs/model-evaluation.md`：用户交集为 0）。
- **双轨融合 + 一票否决**：`final_score = 0.5×rule + 0.5×ml(sigmoid 校准)`；规则命中「极高」时强制拒绝，不被 ML 低分推翻（`decision.py::_calculate_decision`）。
- **前端不引入新框架**：保持 FastAPI + Jinja2 + Bootstrap 5 + 原生 JS，只在 `static/app.js` 统一工具函数（分页、转义、ML 分块、条件构建器），避免为教学项目引入构建链。

## 6. 实际失败与修正

以下为 `docs/goal-progress.md`、代码注释与 Git 历史中可查证的修正（`#` 后可回看提交/文件）：

- **基线完整测试不可跑**：38 个测试文件中 5 个硬编码旧绝对路径，65 个 error；`test_scheduler` 连本机 MySQL 无凭据 1 个 failed。修正：Goal 1 不修业务代码，只在 `docs/baseline-test-report.md` 记录阻塞与复现命令，改跑可行子集（348 passed）。后续 Goal 2 用隔离的 `bank_risk_test` 容器解除阻塞。
- **ML 评分量纲错配**（`decision.py::_ml_prob_to_risk_score` 注释 P4-L4）：原先 `int(prob*100)` 把概率当分值，导致“规则 60 + ML 0.5”被拉低到 55。修正：sigmoid 校准 `100×(1-e^(-3p))`，0.5→78，与规则分同量纲融合。
- **一票否决被融合拉低**（P0-S2 注释）：原实现只对 rule_score 判 veto，融合后可能被 ML 低分降级放行。修正：融合完成后再判一次 veto，强制 `拒绝/极高` 并抬分。
- **训练标签自举污染**（提交 `a0db4cd`）：`gen_train_dataset.py` 生成标签时若已加载旧模型，会把旧模型结果混入标签造成自举。修正：生成训练数据时强制纯规则决策（`ml_model.disabled()` 上下文）。
- **5 处存储型 XSS**（提交 `a0db4cd`）：`rules/cases/blacklist/assessments/chat` 的用户可控字段拼接进 innerHTML。修正：`app.js` 新增全局 `escapeHtml`，内联事件改 `data-*` + 事件委托，新增 `tests/test_goal3_security_fixes.py`（10 项）回归。
- **移动端抽屉焦点丢失**（`base.html`）：关闭抽屉后焦点回到菜单按钮，遮罩点击与 Escape 均可关闭，`aria-expanded` 复位。
- **规则构建器 modal 时机**（P4-L5 注释）：`buildConditionUI` 必须在 `shown.bs.modal` 事件后调用，避免 modal 复用场景下 DOM 未就绪；双保险（shown 回调 + setTimeout 兜底）。
- **条件构建器同步删改**（P4-L5 注释）：删 leaf/group 时通过 `removeCondFromTree` 从 `window._CURRENT_COND` 树 splice 再整体重渲，保证 UI/数据 100% 同步。

## 7. 测试与 Git 检查点

- **测试检查点**：每个 Goal 都要求“先写能复现行为的测试再实现”，并在阶段末运行聚焦测试 + 完整 pytest +（Goal 2/3）实库 DDL 验收。测试规模：基线 451 项 → Goal 2 完整 514 passed/1 skipped → Goal 3 完整 520 passed/0 failed（含 DDL 实库 18 项）。
- **Git 检查点**：每阶段一个聚焦提交到 `main`，推送到 private `origin` 后回读可见性。提交序列（`git log --oneline`）：`e659234` 导入基线 → `f4cbb8f`/`f1e0eb0`/`008a5b3` Goal 1 文档 → `54563f0` Goal 2 数据层 → `efdfae5` Goal 3 pipeline/前端 → `adce302` Goal 3 验收记录 → `a0db4cd` 安全修复。
- **提交卫生**：`.gitignore` 覆盖 `.env`、日志、缓存、模型临时文件、IDE 状态；推送前扫描无凭据/真实 PII/转储。

## 8. 人工参与边界

- LLM 可自主推进：目标内本地编辑、非破坏性验证、阶段提交、向新建私有仓库推送。
- 必须停下并报告：删除真实数据库、覆盖已有 GitHub 仓库、修改只读基线、任何破坏性或范围扩张操作（提示词中的“授权边界”）。
- 涉及真实资源或影响用户权益的结论不自动下：教学项目只用虚构数据，风险分/规则阈值/模型结果不得描述成生产授信或反洗钱结论。
- 录屏与最终视频由人工完成，LLM 只提供脚本与验收状态（Goal 4 提示词明确“不得虚假宣称已录制”）。

## 9. Vibe Coding 收益与局限

**收益**
- 高层目标提示词（业务契约 + 停止条件）能让助手按“契约优先、验收驱动”自主施工，产出可复现的测试与文档。
- 阶段拆分 + 独立对话避免长上下文互相污染，每阶段聚焦、可审查、可回滚。
- 自动生成聚焦测试、验证报告与文档，形成可复核的证据链（`docs/goal-progress.md`、`docs/model-evaluation.md`、`docs/frontend-design.md`）。

**局限**
- 助手倾向报喜不报忧：Goal 3 指标 AUC/F1=1.0 是“规则即标签”的干净合成结果，不是真实泛化能力，必须靠评估文档主动声明局限，不能当成功宣传。
- 长流程中历史决定易被遗忘：跨阶段只靠提交与文档交接，需要契约文档持续强化。
- 无法替代真实业务判断：监管引用、教学边界、生产化差距（实时特征、监控、审批治理、可解释性、灾备、监管报送）仍需人工把关。

## 10. 总结

四个 `/goal` 提示词把一次大重构切成“定契约 → 建数据 → 做能力 → 做交付”四个可验收阶段；LLM 在其中按契约施工、写测试、产出证据，人工在边界与结论上把关。最终项目同时交付：可运行的银行风控流水线、全新前端、训练评估、演示材料、面试问答与 `docs/final-verification.md` 全量验证，并全部推送到私有仓库。
