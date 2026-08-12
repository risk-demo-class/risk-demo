<<<<<<< HEAD
# 📊 Insight Demo 课程演示仓库

本仓库用于课程各小组的**演示成果提交与展示**。每位同学把自己的代码 / 演示成果推送到**对应行业方向的分支**上。

- 仓库地址：https://github.com/wyxaxx02419/insight_demo

---

## 一、分支说明（按行业方向划分）

| 分支名 | 行业方向 | 说明 |
|---|---|---|
| `main` | 主分支 | 只读，**禁止直接推送**（已设置保护） |
| `tourism` | 旅游 | 旅游组同学推送 |
| `banking` | 银行 | 银行组同学推送 |
| `education` | 教育 | 教育组同学推送 |
| `manufacturing` | 制造业 | 制造业组同学推送 |
| `logistics` | 物流 | 物流组同学推送 |
| `medical` | 医疗 | 医疗组同学推送 |
| `telecom` | 电信 | 电信组同学推送 |
| `sharing-economy` | 共享经济 | 共享经济组同学推送 |

> 分支名统一用英文，是为了兼容各类 Git 工具（Windows 下中文分支名容易出问题），中文含义见上表。

---

## 二、重要规则（务必遵守）

1. ✅ **每位同学只能往自己的分支推送**，分支用自己的名字命名（如 `zhangsan`、`li-xiaoming`）
2. 🚫 **禁止向 `main` 推送**（已开启分支保护，会直接报错拒绝）
3. 🚫 **禁止修改、覆盖其他同学的分支**
4. 📁 建议在分支内先建一个**自己名字的文件夹**，把成果放进去，方便老师和同学查看
5. ❤️ 尊重他人成果，只提交自己的内容

---

## 三、学生推送步骤（第一次）

### 第 0 步：准备工作

1. **注册 GitHub 账号**：https://github.com/join （已有账号跳过）
2. **把你的 GitHub 用户名发给老师**——老师把你加为仓库协作者后，你才有推送权限（邀请链接会发到你的 GitHub 通知里，点 Accept 接受即可）
3. **安装 Git**：https://git-scm.com/download/win 一路 Next 安装

### 第 1 步：克隆仓库到本地

打开命令行（Windows 按 `Win+R` 输入 `cmd` 回车；或右键桌面 →「在终端中打开」），执行：

```bash
git clone https://github.com/wyxaxx02419/insight_demo.git
cd insight_demo
```

### 第 2 步：创建自己的分支（用自己的名字）

```bash
git checkout -b zhangsan
```

> 分支名建议：名字拼音全小写，多个字用 `-` 连接，例如 `zhangsan`、`wang-xiaoming`、`chenxi`。**不要用中文和空格**。

### 第 3 步：放入你的成果

把代码 / 演示文件（PPT、图片、视频、代码等）复制到仓库文件夹里，建议建一个自己的文件夹：

```bash
mkdir zhangsan
# 然后把你的文件放进 zhangsan 文件夹
```

### 第 4 步：提交并推送（关键！）

```bash
git add .
git commit -m "zhangsan 提交旅游行业演示成果"
git push -u origin zhangsan
```

看到 `branch 'zhangsan' set up to track` 和进度条走完，就说明**推送成功**了 🎉

### 第 5 步：确认成果

打开 https://github.com/wyxaxx02419/insight_demo ，点击左上角的 **Branch 下拉框**，选择你的分支名 `zhangsan`，即可看到你的文件。

---

## 四、以后每次更新（重复这三条）

```bash
git add .
git commit -m "更新说明，比如：补充了演示视频"
git push
```

---

## 五、常见问题（FAQ）

| 问题 | 原因与解决办法 |
|---|---|
| `Permission to ... denied` | 老师还没邀请你，或邀请没点接受。把 GitHub 用户名发给老师 |
| `Updates were rejected` | 你当前不在自己的分支上。先 `git status` 查看，再用 `git checkout 你的分支名` 切回去，最后 `git push` |
| `master has no upstream branch` | 说明你在 `main` 上，直接用 `git checkout -b 你的名字` 建自己的分支再推 |
| 推送超时 / 网络错误 | GitHub 网络不稳定，可以开代理，或改用 SSH 方式（见下节） |
| 忘了自己分支名 | `git branch -a` 查看所有分支（本地+远程） |

### 网络不好？用 SSH 方式（可选）

如果 HTTPS 推送经常超时，可以用 SSH：

1. 生成密钥：`ssh-keygen -t ed25519 -C "你的邮箱"`（一路回车）
2. 查看公钥：`cat ~/.ssh/id_ed25519.pub`，复制全部内容
3. 粘贴到 GitHub：https://github.com/settings/keys → New SSH key → 保存
4. 之后用 SSH 地址克隆：

```bash
git clone git@github.com:wyxaxx02419/insight_demo.git
cd insight_demo
git checkout -b zhangsan
# ... 后面的提交推送步骤一样
=======
# Medical_Risk — 医疗智能风控系统

> 面向 **医保结算 / 处方审核 / 挂号黄牛 / 药品代购** 4 大场景的医疗行业智能风控系统。
> 风控核心引擎与电商版 (AI_Risk) 完全一致 (9 张风控表 + 7 步决策流水线 + 4 步业务流),
> 业务表 / 特征计算 / 规则 / 数据生成 / 前端全部按医疗行业重做。

---

## 一、系统定位

医疗行业强监管, 风控对象不只是"用户", 还有 **医生 / 医院 / 医保卡**:

| 场景 | 典型风险 | 对应规则 |
|---|---|---|
| 医保结算 | 医保卡盗刷 (1 小时多院刷卡) / 异地集中结算 / 黑医保卡 | R001 / R025 / R030 |
| 处方审核 | 医生统方 (单日 50+ 处方) / 处方超量 (阿普唑仑 > 30 片) / 虚假病历 | R002 / R008 / R012 |
| 挂号黄牛 | 同手机号 24h 取消挂号 ≥5 次 (反复抢号转卖) | R005 |
| 药品代购 | 处方药收件人 ≠ 患者本人 + 累计金额 > 5000 | R018 |

**核心契约 (与电商版一致, 不许改)**:

```
process_event(RiskCheckRequest) -> RiskCheckResponse
RiskCheckRequest = { event_type, source_id, user_id, event_data }
```

- `event_type`: 挂号 / 处方开具 / 医保结算 / 药品下单
- `source_id`: 对应单据 ID (appt_id / rx_id / claim_id / drug_order_id)

---

## 二、技术栈

| 层 | 技术 |
|---|---|
| Web 框架 | FastAPI 0.115 + Uvicorn |
| ORM | SQLAlchemy 2.0 (async, Mapped/mapped_column) |
| 数据库 | MySQL 8.0 (utf8mb4) + aiomysql |
| 数据校验 | Pydantic 2.10 |
| 机器学习 | XGBoost 2.1 + scikit-learn (双轨融合: 规则分 × 0.5 + ML 分 × 0.5) |
| AI Agent | LangChain / DeepAgents + 阿里云百炼 qwen-plus |
| 前端 | Jinja2 + Bootstrap 5 + Chart.js |

---

## 三、目录结构

```
Medical_Risk/
├── app/
│   ├── engine/                  # 风控引擎 (与电商版同构)
│   │   ├── decision.py          # 7 步决策流水线 run_risk_check
│   │   ├── rule.py              # 规则加载 + 条件匹配 (完全复用)
│   │   ├── feature.py           # 25 维医疗特征计算 (重做)
│   │   └── ml_model.py          # XGBoost 加载/推理/训练 (FEATURE_COLUMNS 医疗化)
│   ├── service/
│   │   ├── event.py             # process_event 4 步业务流 (5 类黑名单短路)
│   │   ├── validator.py         # 业务实体校验派发表 (重做)
│   │   ├── case.py              # 案件/黑名单服务 (复用)
│   │   ├── alert.py             # 告警服务 (复用)
│   │   └── action_log.py        # 审计日志 (复用)
│   ├── agent/                   # AI 助手 (8 个 LangChain 工具, 业务查询医疗化)
│   ├── routers/                 # REST API + 页面路由
│   ├── models_risk.py           # 9 张风控表 ORM (结构复用, 枚举医疗化)
│   ├── models_business.py       # 8 张医疗业务表 ORM (重做)
│   ├── schemas.py               # Pydantic 模型 (事件/规则/黑名单类型医疗化)
│   ├── config.py                # 全局配置 (.env)
│   └── api.py                   # FastAPI 应用装配
├── sql/                         # DDL + 预置规则 (30 条医疗规则)
├── scripts/                     # 建库 / 造数据 / 训练脚本 (医疗重做)
├── templates/ static/           # 前端页面 (医疗风格)
├── docker/                      # Docker + Nginx 部署
└── tests/                       # pytest 测试
>>>>>>> 8e173f1 (feat:医疗风控项目demo)
```

---

<<<<<<< HEAD
## 六、老师（管理员）操作备忘

### 1. 添加学生为协作者（学生有推送权限的前提）

```bash
gh repo add-collaborator wyxaxx02419/insight_demo <学生GitHub用户名> --permission push
```

或网页操作：仓库页面 → **Settings → Collaborators → Add people** → 输入学生用户名 → 选择 **Write** 权限 → 发送邀请。

### 2. 严格锁定：每个分支只允许本组同学推送（强烈建议）

默认情况下，协作者可以推送到任意分支。为了真正做到「只能推送自己的分支」，收集齐学生用户名后，对每个分支设置「只允许指定用户推送」：

```bash
# 先准备好 students.csv，格式：分支名,用户名（一行一个学生）
# 例如：
# tourism,zhangsan
# tourism,lisi
# banking,wangwu

# 然后运行下面的脚本（bash / git-bash）
while IFS=, read -r branch user; do
  gh api -X PUT "repos/wyxaxx02419/insight_demo/branches/$branch/protection" \
    -H "Accept: application/vnd.github+json" \
    --input - <<EOF
{"required_status_checks":null,"enforce_admins":false,
 "required_pull_request_reviews":null,
 "restrictions":{"users":["$user"],"teams":[],"apps":[]}}
EOF
done < students.csv
```

> 说明：脚本会给每个分支设置「仅允许指定学生 + 老师推送」。注意一个分支有多个学生时，后执行的行会覆盖前面的 users 列表——如果每组多人，把同分支的所有用户名放进一个数组再设置一次即可（或直接找我帮你配置，把名单给我就行）。

### 3. 查看仓库状态

```bash
gh api repos/wyxaxx02419/insight_demo/branches --jq '.[].name'   # 列出所有分支
gh repo view wyxaxx02419/insight_demo                            # 查看仓库信息
=======
## 四、数据模型

### 4.1 风控核心 9 张表 (与电商版完全一致, 不许改结构)

`risk_rule` / `risk_event` / `risk_feature` / `risk_assessment` / `risk_case` /
`risk_blacklist` / `risk_user_profile` / `risk_action_log` / `risk_alert`

医疗行业只改**枚举值**:

| 枚举 | 医疗版取值 |
|---|---|
| 事件类型 | 挂号 / 处方开具 / 医保结算 / 药品下单 |
| 规则分类 | 医保欺诈 / 处方违规 / 挂号黄牛 / 药品代购 / 账户风险 / 机构风险 |
| 黑名单类型 | 用户 / 医保卡号 / 身份证号 / 医生执业证 / 医院编码 |
| 特征实体 | 用户=患者, 订单=诊疗单据, 地址=医疗机构 |

`risk_user_profile` 列名不变, 语义映射: `total_orders`=总挂号数,
`total_refunds`=取消挂号数, `refund_rate`=取消率, `avg_order_amount`=平均结算金额,
`address_count`=就诊医院数, `complaint_count`=医保结算次数。

### 4.2 医疗业务 8 张表 (重做)

| 表 | 说明 |
|---|---|
| `user_info` | 患者档案 (医保卡号 / 身份证号哈希 / 参保类型 / 参保地) |
| `hospital` | 医院档案 (等级 / 省市 / 医保定点) |
| `doctor` | 医生档案 (科室 / 职称 / 执业证号) |
| `appointment` | 挂号记录 (含预约手机号, 黄牛识别用) |
| `prescription` | 处方单 (诊断编码 ICD-10 + 药品明细 JSON) |
| `insurance_claim` | 医保结算 (总费用 / 报销额 / 结算状态) |
| `drug_order` | 药品订单 (收件人, 代购识别用) |
| `blacklist_extra` | 行业黑名单登记簿 (4 类) |

---

## 五、决策流水线 (与电商版同流程)

### process_event 4 步业务流
1. 业务实体校验 (患者存在 + source_id 类型匹配 + 单据归属一致)
2. 补全 hospital_id
3. 黑名单前置拦截 (用户 > 医保卡号 > 身份证号 > 医生执业证 > 医院编码, 撞黑直接拒绝)
4. 调 run_risk_check

### run_risk_check 7 步
1. 准备上下文 → 2. 创建事件记录 → 3-4. 计算并保存 25 维特征快照 →
5. 加载并匹配规则 → 6. 评分与决策 (一票否决 + 双轨融合) → 7. 落库 + 响应

**评分**: `final_score = min(max(规则分) + 3 × 额外命中数, 100)`
**双轨融合**: `final_score = 0.5 × 规则分 + 0.5 × ML分` (ML 分 = sigmoid 校准 `100×(1-e^{-3p})`)
**一票否决**: 任何 `极高` 规则命中 → 强制拒绝, 不被 XGBoost 推翻

### 25 维特征 (重做)

- 患者 14 维: `user_total_visits` / `user_visits_7d` / `user_visits_30d` /
  `user_cancel_count` / `user_cancel_24h` / `user_hospital_count` /
  `user_claim_hospitals_1h` / `user_claim_count` / `user_claim_amount` /
  `user_claim_30d_count` / `user_claim_30d_amount` / `user_rx_count` /
  `user_drug_amount` / `user_card_blacklist_hit`
- 诊疗单据 8 维: `order_total_amount` / `order_item_count` / `order_drug_quantity` /
  `order_is_night` / `order_doctor_rx_1d` / `order_doctor_patient_1d` /
  `order_diagnosis_same_7d` / `order_receiver_not_self`
- 医疗机构 3 维: `addr_visit_count` / `addr_is_new` / `addr_cross_region`

---

## 六、预置规则 (30 条, R001-R030)

示例 8 条 (行业专属):

| 编号 | 规则名 | 触发条件 | 等级 | 决策 |
|---|---|---|---|---|
| R001 | 医保卡盗刷 | 同一医保卡 1h 内 ≥3 家医院结算 | 极高 | 拒绝 |
| R002 | 医生统方 | 医生 1 天 ≥50 张处方 + ≥10 患者 | 极高 | 人工审核 |
| R005 | 挂号黄牛 | 同手机号 24h 取消挂号 ≥5 次 | 高 | 人工审核 |
| R008 | 处方超量 | 单张处方药品数量 > 30 | 极高 | 拒绝 |
| R012 | 虚假病历 | 同医生同诊断编码 7 天 ≥5 患者 | 高 | 人工审核 |
| R018 | 药品代购 | 收件人 ≠ 本人 + 累计购药 > 5000 | 中 | 标记 |
| R025 | 异地集中结算 | 异地 + 30 天 ≥3 次结算 + 累计 >1 万 | 中 | 标记 |
| R030 | 黑医保卡 | 医保卡号/身份证号命中黑名单 | 极高 | 拒绝 |

---

## 七、快速开始

### 1. 环境准备

```bash
# Python 3.11+, MySQL 8.0 已启动
pip install -r requirements.txt
cp docker/.env.example .env   # 或直接用项目根 .env, 按需改 DB 密码 / LLM key
```

### 2. 一键初始化 + 造数据 + 训练 + 启动

```bash
python scripts/one_command.py
```

6 步: 重置数据库 → 造 30 个 RISK 高风险患者 → 造 1500 条训练数据 →
训练 XGBoost → 回填 ml_score → 造 50 条今日评估。

### 3. 分步执行

```bash
python scripts/init_db.py --reset --yes        # 建库 (medical_risk) + 30 条规则
python scripts/gen_risky_users.py --count 30   # 5 种医疗风险模式患者
python scripts/gen_risk_data.py --count 50     # 跑真实风控评估
python scripts/train_demo_model.py             # 无 DB 合成训练演示模型
python run_app.py                              # 启动 http://localhost:8000
```

### 4. Docker 部署

```bash
cd docker
cp .env.example .env   # 填 LLM_API_KEY
docker compose up -d
>>>>>>> 8e173f1 (feat:医疗风控项目demo)
```

---

<<<<<<< HEAD
*本指南由老师统一发布，如有问题请私信老师。祝大家演示顺利！🎓*
=======
## 八、API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/risk/check` | 风险检查 (4 字段核心契约) |
| GET | `/api/rules` | 规则列表 (分页/分类筛选) |
| POST/PUT/DELETE | `/api/rules/{id}` | 规则 CRUD + 启停 |
| GET | `/api/cases` | 案件列表 |
| POST | `/api/cases/{id}/review` | 案件审核 (可联动加黑名单) |
| GET | `/api/assessments` | 评估历史 |
| GET | `/api/profile/{user_id}` | 患者风险画像 |
| GET/POST/DELETE | `/api/blacklist` | 黑名单管理 (5 类) |
| GET | `/api/dashboard/*` | 仪表盘统计 |
| GET | `/api/alerts` / POST `/api/alerts/check` | 告警 |
| POST | `/api/agent/chat` | AI 助手对话 |

风险检查示例:

```bash
curl -X POST http://localhost:8000/api/risk/check \
  -H "Content-Type: application/json" \
  -d '{"event_type": "医保结算", "source_id": "CLM_SEED_001", "user_id": "P0001"}'
```

---

## 九、前端页面

| 页面 | 路径 | 功能 |
|---|---|---|
| 仪表盘 | `/` | 今日评估 / 高风险 / 待审案件 / 7 天趋势 / TOP 规则 |
| 规则管理 | `/rules` | 30 条医疗规则 CRUD + 启停 |
| 案件管理 | `/cases` | 待审核案件工作台 + 审核 + 重做检查 |
| 评估历史 | `/assessments` | 全量评估 (含通过/标记) |
| 风险检查 | `/risk-check` | 手动发起 4 类事件检查 |
| AI 助手 | `/chat` | 对话式风控分析 |
| 黑名单 | `/blacklist` | 5 类黑名单管理 |

---

## 十、脚本清单

| 脚本 | 用途 |
|---|---|
| `scripts/init_db.py` | 一键建库 (8 业务表 + 9 风控表 + 种子数据 + 30 规则) |
| `scripts/gen_risky_users.py` | 造 RISK 高风险患者 (盗刷/统方/黄牛/超量/代购 5 模式) |
| `scripts/gen_risk_data.py` | 从单据池挑数据跑真实风控评估 |
| `scripts/gen_risk_data_with_dates.py` | 带日期范围造评估 (趋势图/训练用) |
| `scripts/gen_train_dataset.py` | 造 1500 条强标注训练数据 (ml_score=NULL) |
| `scripts/gen_10w_data.py` | 造约 10w 条业务流水 (性能/大数据量演示) |
| `scripts/train_xgb_model.py` | 用 risk_assessment 训练 XGBoost |
| `scripts/train_demo_model.py` | 不依赖 DB, 合成数据训演示模型 |
| `scripts/backfill_ml_score.py` | 用训好的模型回填 ml_score |
| `scripts/one_command.py` | 一条龙: 重置 → 造数 → 训练 → 回填 → 启动 |

---

## 十一、与电商版 (AI_Risk) 的差异总览

| 模块 | 复用情况 |
|---|---|
| 风控核心 9 张表 | 完全复用 (仅枚举值医疗化) |
| 引擎 4 核心 (decision/feature/rule/ml_model) | 完全复用 (只改特征计算函数) |
| 决策流水线 (process_event 4 步 + run_risk_check 7 步) | 完全复用 |
| 业务表 models_business.py | 重做 (17 张 → 8 张医疗表) |
| 特征计算 | 重做 (25 维医疗特征) |
| validator 派发表 / 事件类型 / 黑名单类型 | 重做 |
| 数据生成脚本 | 重做 |
| 业务规则 | 重做 (30 条医疗规则) |
| 前端 / 文档 / Docker | 重做 (医疗风格) |
>>>>>>> 8e173f1 (feat:医疗风控项目demo)
