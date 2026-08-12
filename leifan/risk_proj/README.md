# 旅盾 RiskOps：OTA 旅游风控平台

这是一个基于 MySQL、FastAPI、SQLAlchemy、XGBoost 和 Deep Agents 的旅游订单风控管理项目，覆盖机票、酒店、签证和跟团游业务。

系统包含风险规则评估、模型评分、自动决策、人工审核、黑护照名单、审计日志、员工权限管理，以及仅管理员可使用的数据库管理 Agent。

## 一、主要功能

- 风险主面板：查看订单、交易金额、风险决策和待审核案件统计。
- 订单中心：查询订单、用户、业务类型、金额、最终风险分和决策结果。
- 人工审核：处理待审核订单，并记录放行或拒绝原因。
- 规则管理：按规则组维护多个风险档位、启停规则并自动重算全部评分。
- 黑名单管理：维护使用哈希和脱敏值保存的黑护照名单。
- 审计日志：记录规则、名单、审核、账号及 Agent 数据库写操作。
- 权限管理：管理员工账号和角色；每个员工只能分配一个角色。
- 管理 Agent：管理员使用自然语言查询或操作项目数据库，不保存聊天历史。

## 二、运行环境

启动项目前请准备：

| 组件 | 要求 |
|---|---|
| 操作系统 | Windows、Linux 或 macOS |
| Python | 3.12 |
| Python 环境与依赖管理 | uv |
| 数据库 | MySQL 8.0 |
| 浏览器 | Chrome、Edge 或其他现代浏览器 |

以下命令默认在项目根目录执行。Windows 示例使用 PowerShell；Linux 和 macOS 可使用含义相同的终端命令。

## 三、从零启动项目

### 1. 进入项目目录

```powershell
cd C:\path\to\risk_proj
```

如果代码来自 Git 仓库，应先克隆仓库，再进入包含 `pyproject.toml` 的项目根目录。

### 2. 安装 uv 和 Python 3.12

如果尚未安装 uv，可使用官方安装程序。

Windows PowerShell：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Linux 或 macOS：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

其他安装方式见 [uv 官方安装文档](https://docs.astral.sh/uv/getting-started/installation/)。安装完成后重新打开终端，并确认命令可用：

```powershell
uv --version
```

安装项目需要的 Python 版本，并在项目目录创建 `.venv`：

```powershell
uv python install 3.12
uv venv --python 3.12
uv sync
```

`uv sync` 会根据 `pyproject.toml` 和 `uv.lock` 把运行与测试依赖安装到当前项目的 `.venv`，不需要全局安装 FastAPI、SQLAlchemy、PyMySQL、XGBoost 或 Deep Agents。

### 3. 启动 MySQL 8.0

确认 MySQL 服务已经启动，并准备一个可创建数据库和表的 MySQL 账号。初始化脚本会自动创建 `risk_proj` 数据库，因此该账号至少需要建库、建表和读写权限。

可以先验证连接：

```powershell
mysql -h 127.0.0.1 -P 3306 -u root -p
```

如果 MySQL 客户端命令未加入环境变量，也可以直接继续后续步骤，通过初始化脚本验证连接。

### 4. 创建并配置 `.env`

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

Linux 或 macOS：

```bash
cp .env.example .env
```

编辑项目根目录的 `.env`：

```dotenv
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=请填写本机MySQL密码
MYSQL_DATABASE=risk_proj

APP_SECRET_KEY=请填写至少32个字符的随机密钥
SESSION_TTL_SECONDS=28800
SESSION_COOKIE_SECURE=false

ADMIN_USERNAME=administer
ADMIN_INITIAL_PASSWORD=123456

XGBOOST_MODEL_PATH=models/travel_risk_xgboost.ubj

OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5.6
```

可以生成一个随机的 `APP_SECRET_KEY`：

```powershell
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

注意：

- `APP_SECRET_KEY` 少于 32 个字符时无法登录。
- `ADMIN_INITIAL_PASSWORD` 至少需要 6 个字符。
- `ADMIN_INITIAL_PASSWORD` 只在管理员账号首次创建时使用；账号已经存在时，修改该配置不会自动重置密码，应在权限管理页面重置。
- `123456` 仅适合本地演示，部署前必须修改。
- 本地 HTTP 开发使用 `SESSION_COOKIE_SECURE=false`；通过 HTTPS 部署时应改为 `true`。
- OpenAI 配置只影响管理 Agent，其他风控页面无需配置模型 API 也可以运行。

### 5. 创建数据库和全部表

推荐执行：

```powershell
uv run python -m scripts.init_db
```

该命令会：

1. 在数据库不存在时创建 `.env` 中的 `MYSQL_DATABASE`；
2. 使用 `utf8mb4` 字符集创建数据库；
3. 根据 SQLAlchemy ORM 创建当前项目的 20 张表；
4. 保留已经存在的数据，不会删除现有表或记录。

项目还提供了位于 `sql` 目录的分类 Python 建表程序。需要一次创建全部表时也可以执行：

```powershell
uv run python sql/init_all.py
```

按分类建表的命令见 [sql/README.md](sql/README.md)。新环境选择一种完整建表方式即可，不需要把两种命令都执行一遍。

### 6. 初始化角色、权限和管理员

```powershell
uv run python -m scripts.init_auth
```

该命令会初始化：

- 11 个细粒度权限点；
- 系统管理员、风控审核员、规则运营、只读人员 4 个角色；
- `.env` 中指定的管理员账号；
- 管理员与系统管理员角色的关联。

命令可以重复执行，不会重复创建相同的角色、权限或管理员。

### 7. 初始化规则和演示业务数据

```powershell
uv run python -m scripts.seed_data --orders 400
```

该命令会生成：

- 13 个风险规则档位；
- 用户、支付账号和乘客；
- 机票、酒店、签证和跟团游订单；
- 黑名单、规则命中、初始评分、审核案件和审计日志。

`--orders` 不能小于 40。脚本默认拒绝向已有业务数据的数据库重复写入，以防止误覆盖。

如果明确要删除现有演示业务数据并重新生成，可执行：

```powershell
uv run python -m scripts.seed_data --orders 400 --reset
```

警告：`--reset` 会清空 15 张业务与风控表的数据，但不会删除员工、角色和权限数据。使用前应确认当前数据库只用于演示，正式数据不要执行此命令。

### 8. 写入模型评分和最终状态

仓库已经包含演示模型：

```text
models/travel_risk_xgboost.ubj
```

演示数据初始化完成后，执行一次全量重算：

```powershell
uv run python -m scripts.recalculate_scores
```

系统会使用当前启用的规则和 `XGBOOST_MODEL_PATH` 指向的模型，更新每笔订单的：

- 规则原始分；
- 模型风险概率和模型分；
- 最终风险分；
- 放行、人工审核或自动拒绝状态；
- 规则命中记录和审核案件状态。

如果模型文件不存在，系统仍可运行，但全量重算会退化为只使用规则评分，模型相关字段为空。

### 9. 启动 Web 服务

开发环境：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

终端出现 `Application startup complete` 后访问：

- 登录页面：<http://127.0.0.1:8000/login>
- 健康检查：<http://127.0.0.1:8000/api/health>
- FastAPI 接口文档：<http://127.0.0.1:8000/docs>

默认演示管理员：

| 项目 | 默认值 |
|---|---|
| 用户名 | `administer` |
| 密码 | `.env` 中的 `ADMIN_INITIAL_PASSWORD`，示例为 `123456` |

停止服务时在启动服务的终端按 `Ctrl+C`。

生产或局域网运行时可以去掉 `--reload`，并按实际需要调整监听地址：

```powershell
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`0.0.0.0` 会允许其他设备访问。使用前应同时配置防火墙、HTTPS、强密码、数据库最小权限和 `SESSION_COOKIE_SECURE=true`。

## 四、使用系统

### 风险主面板

登录后默认进入风险主面板，可以查看订单数量、交易金额、风险决策分布、业务分布、规则命中和待审核案件等概览。

### 订单中心

可以按订单号、用户、业务类型和风险状态筛选订单，支持对合适的数据库列排序。点击订单号可查看用户、乘客、规则分、模型分、最终分及命中证据。

### 人工审核

最终分在人工审核范围内的订单会进入审核队列。具有 `reviews:decide` 权限的员工可以填写处置原因并选择放行或拒绝，结果会同步到订单和审核案件，并写入审计日志。

### 规则管理

同一业务含义的多个档位合并为一个规则组展示。具有 `rules:manage` 权限的员工可以：

- 编辑档位条件和风险分；
- 启用或停用规则组；
- 保存后自动重算全部订单。

规则修改和评分重算处于同一事务中；任一步骤失败时，规则修改与重算结果会一起回滚。也可以通过 `scripts.recalculate_scores` 手动触发相同的全量重算流程。

### 黑护照名单

具有 `blacklist:manage` 权限的员工可以新增、修改或停用黑名单。证件号只保存哈希值和脱敏值，不保存明文；涉及完整证件号的操作应在可信环境中完成。

### 审计日志

审计日志记录操作人、动作、对象、请求编号以及变更前后的数据，可按适合的列排序，用于追踪规则、名单、审核、权限和 Agent 操作。

### 权限管理

只有具有 `iam:manage` 权限的管理员可以创建员工、启停账号、重置密码和分配角色。每个员工只能选择一个角色。

内置角色：

| 角色 | 主要用途 |
|---|---|
| 系统管理员 | 使用全部后台功能和权限管理能力 |
| 风控审核员 | 查看订单并处理人工审核案件 |
| 规则运营 | 维护风险规则和黑名单，查看审计日志 |
| 只读人员 | 只读查看主面板、订单、规则、名单和审计日志 |

页面与接口都会在服务端校验权限，前端导航还会隐藏当前账号无权访问的入口。

## 五、配置和使用管理 Agent

管理 Agent 页面地址为 <http://127.0.0.1:8000/agent>，只有系统管理员角色可以访问。

Agent 使用 Deep Agents 的 `create_deep_agent` 创建，并通过 16 个白名单工具操作当前项目数据库。它支持：

- 查询风险概览、订单、用户和评分详情；
- 查询并处置人工审核案件；
- 管理规则启停、档位分数并重算全部评分；
- 查询、新增和更新黑护照名单；
- 查询审计日志和员工账号状态。

Agent 不支持项目外聊天、任意 SQL、文件操作、命令执行和子 Agent。每次任务独立执行，不保存聊天历史；数据库写操作会写入审计日志。单次输入最多 200 个字符，多条结构化查询结果会优先以表格展示。

启用前在 `.env` 配置：

```dotenv
OPENAI_API_KEY=你的API密钥
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=支持工具调用的模型名称
```

使用 OpenAI 兼容模型网关时，把 `OPENAI_BASE_URL` 改为服务商提供的 API 根地址，通常需要包含 `/v1`，并把 `OPENAI_MODEL` 改为该服务当前可用且支持工具调用的模型名称。修改 `.env` 后需要重启 Uvicorn。

如果未配置 `OPENAI_API_KEY`，管理 Agent 会提示配置缺失，但不会影响其他页面。

## 六、风险评分规则

### 1. 规则分

```text
R = 命中规则最高分 + 命中规则数 - 1
```

没有命中规则时规则分为 0。

### 2. 模型分

XGBoost 输出原始值 `z`：

```text
p = 1 / (1 + exp(-z))
M = round(p × 100)
```

其中 `p` 是模型风险概率，`M` 是模型分。

### 3. 融合分和最终分

```text
融合分 = round(0.6 × R + 0.4 × M)
最终分 = min(max(R, 融合分), 100)
```

最终分不会低于规则分，最高为 100。

### 4. 自动决策

| 最终分 | 决策 | 系统处理 |
|---|---|---|
| 0–29 | 放行 | 订单状态更新为已确认 |
| 30–74 | 人工审核 | 创建或重新打开待审核案件 |
| 75–100 | 自动拒绝 | 订单状态更新为风险拒绝 |

数据库中 `risk_assessment.raw_score` 保存规则原始分，`risk_score` 保存最终分；模型概率、模型分和模型版本分别保存在 `model_probability`、`model_score` 和 `model_version`。用户账号年龄在查询和评估时根据 `registered_at` 动态计算。

## 七、训练自己的 XGBoost 模型

项目自带模型可直接用于演示。如果需要根据当前数据库重新训练：

```powershell
uv run python -m scripts.train_xgboost_model
uv run python -m scripts.recalculate_scores
```

默认输出：

- 模型：`models/travel_risk_xgboost.ubj`
- 元数据：`models/travel_risk_xgboost.metadata.json`

常用训练参数：

```powershell
uv run python -m scripts.train_xgboost_model --rounds 240 --validation-ratio 0.2 --seed 20260812
```

只使用已经完成的人工审核结果作为训练标签：

```powershell
uv run python -m scripts.train_xgboost_model --manual-only
```

训练至少需要 40 条带标签数据，并且安全和风险两类标签都必须存在。默认情况下，训练脚本优先使用已完成人工审核的结果；真实标签不足时，也会使用当前放行和自动拒绝结果作为弱监督标签。

演示数据训练出的模型不应直接用于生产。正式投产前应使用真实欺诈、拒付或人工核验标签重新训练，并评估 AUC、准确率、误拒率、召回率及业务稳定性。

## 八、已有旧数据库的升级

全新数据库通过当前 ORM 建表后已经包含模型字段和单角色约束，不需要执行本节命令。

从早期版本升级已有数据库时，建议先备份数据库，再根据实际缺失内容执行：

```powershell
# 为 risk_assessment 补充模型概率、模型分和模型版本字段
uv run python -m scripts.add_model_scoring_fields

# 清理员工的重复角色关联，并添加单角色唯一约束
uv run python -m scripts.enforce_single_staff_role

# 使用当前规则和模型刷新评分、状态和审核案件
uv run python -m scripts.recalculate_scores
```

`sql` 目录的建表程序只会创建缺失表，不会修改已有表的字段，因此已有表结构变更应使用对应升级脚本。

## 九、运行测试

依赖同步完成且测试数据库可连接后，在项目根目录执行：

```powershell
uv run pytest -q
```

只运行 Agent 测试：

```powershell
uv run pytest tests/test_agent.py -q
```

只运行评分与重算测试：

```powershell
uv run pytest tests/test_scoring.py tests/test_risk_engine.py -q
```

测试会使用 `.env` 指向的数据库，并可能创建后清理临时测试数据。不要让测试配置指向生产数据库。

## 十、常见问题

### MySQL 提示 `Access denied`

检查 `.env` 中的主机、端口、用户名和密码，并确认账号具有创建 `risk_proj` 数据库和表的权限。

### MySQL 提示无法连接

确认 MySQL 8.0 服务已经启动，端口与 `MYSQL_PORT` 一致，且防火墙没有阻止连接。

### 登录时提示 `APP_SECRET_KEY must contain at least 32 characters`

把 `.env` 中的 `APP_SECRET_KEY` 改为至少 32 个字符的随机值，然后重启服务。

### 演示数据脚本提示数据库已经包含数据

这是防误覆盖保护。继续使用现有数据即可；只有确认要替换演示数据时才使用 `--reset`。

### 修改规则后评分没有变化

先检查规则是否启用以及订单是否满足条件。页面保存规则时会自动全量重算；也可以执行：

```powershell
uv run python -m scripts.recalculate_scores
```

### 模型字段为空

确认 `XGBOOST_MODEL_PATH` 指向存在且兼容当前特征结构的模型，然后执行全量重算。旧数据库还需要先运行 `scripts.add_model_scoring_fields`。

### Agent 提示模型不可用或容量已满

检查 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`，并把 `OPENAI_MODEL` 改为服务商当前可用、支持工具调用的模型。修改后重启服务。该问题不影响订单、规则和人工审核等普通页面。

### 8000 端口被占用

使用其他端口启动：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

随后访问 <http://127.0.0.1:8001/login>。

## 十一、项目目录

```text
risk_proj/
├─ app/                 FastAPI、ORM、权限、规则引擎、模型和 Agent 后端
├─ frontend/            管理后台 HTML、CSS 和 JavaScript
├─ models/              XGBoost 模型与训练元数据
├─ scripts/             初始化、演示数据、升级、训练和重算脚本
├─ sql/                 按类别组织的可运行 Python 建表程序
├─ tests/               自动化测试
├─ .env.example         环境变量模板
├─ pyproject.toml       Python 版本和依赖配置
└─ uv.lock              可复现依赖锁文件
```

## 十二、推荐的首次启动命令汇总

已经正确填写 `.env` 后，首次启动依次执行：

```powershell
uv python install 3.12
uv venv --python 3.12
uv sync
uv run python -m scripts.init_db
uv run python -m scripts.init_auth
uv run python -m scripts.seed_data --orders 400
uv run python -m scripts.recalculate_scores
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

之后日常启动通常只需要：

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
