# 银行智能风控系统：从零运行到完整验收

本项目是 AI_Risk 的银行行业版本，业务边界固定为 **信用卡、贷款、转账、登录** 四个场景。系统包含 MySQL 业务数据、规则引擎、25维特征、XGBoost模型、案件与黑名单、告警、AI Agent、FastAPI接口和Web管理页面。

本文以 **Windows PowerShell + Python 3.11 + uv + MySQL 8.0** 为唯一主流程。第一次运行时必须从第1步按顺序执行，不要跳步，也不要混用 `pip`、`python -m venv` 和 `uv sync`。

> 第6步使用 `--reset --yes`，会删除并重建 `.env` 中 `DB_NAME` 指定的数据库。只能对本项目教学库执行，禁止指向真实业务库。

## 一、完成后的结果

- 8张银行业务表和9张通用风控表，共17张表；
- 12条银行风控规则；
- 可复现的信用卡、贷款、转账、登录业务流水；
- 恰好1000次在线决策链训练样本；
- `app/engine/xgb_model.json` XGBoost模型；
- 可访问的Web管理页面、OpenAPI和风险检查接口；
- 本地测试和真实MySQL四场景验收通过。

完整顺序：

```text
进入项目根目录
→ 检查 uv 和 MySQL
→ 创建 .env
→ uv sync 创建根目录 .venv
→ 本地测试
→ 重建 bank_risk
→ 生成业务流水
→ 验证四场景规则链
→ 生成1000条训练样本
→ 训练 XGBoost
→ 回填历史模型评分
→ 启动 FastAPI
→ API 最终验收
```

## 二、第1步：进入项目根目录

使用PyCharm打开项目后，在PyCharm Terminal中执行：

```powershell
Get-Location
```

检查关键文件：

```powershell
Test-Path .\uv\pyproject.toml
Test-Path .\uv\uv.lock
Test-Path .\scripts\init_db.py
Test-Path .\run_app.py
```

终端当前目录应为项目根目录，四项检查都应返回 `True`。本文不再使用项目绝对路径。

## 三、第2步：检查 uv 和 MySQL

检查uv：

```powershell
uv --version
```

检查MySQL端口：

```powershell
Test-NetConnection 127.0.0.1 -Port 3306
```

应看到：

```text
TcpTestSucceeded : True
```

如果为 `False`，先查看并启动MySQL服务：

```powershell
Get-Service | Where-Object { $_.Name -like 'MySQL*' }
Start-Service MySQL80
```

服务名不一定是 `MySQL80`，请使用第一条命令显示的实际名称。启动服务可能需要管理员权限。

## 四、第3步：创建 `.env`

```powershell
if (-not (Test-Path .\.env)) { Copy-Item .\.env.example .\.env }
notepad .\.env
```

至少确认：

```dotenv
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的MySQL密码
DB_NAME=bank_risk
TEST_DB_NAME=bank_risk_test

XGB_ENABLED=true
XGB_MODEL_PATH=app/engine/xgb_model.json
XGB_TRAIN_DATA_LIMIT=1000

# 可选，只有AI Agent需要
LLM_API_KEY=
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus

CASE_TIMEOUT_HOURS=24
ALERT_SCHEDULER_INTERVAL_MIN=15
```

说明：

- `DB_PASSWORD` 必须是当前MySQL用户的真实密码；
- `DB_NAME` 建议保持 `bank_risk`；
- `XGB_TRAIN_DATA_LIMIT=1000` 是未传 `--samples` 时的训练默认值；
- `LLM_API_KEY` 可以留空，不影响规则、模型、案件和管理页面；
- 初始化、造数、训练、验收和服务统一读取根目录 `.env`。

## 五、第4步：使用 uv 安装依赖

项目依赖配置位于 `uv` 子目录，但虚拟环境统一放在项目根目录 `.venv`：

```powershell
$env:UV_PROJECT_ENVIRONMENT = (Join-Path (Get-Location) '.venv')
uv sync --project .\uv --frozen --python 3.11 --no-install-project
```

验证：

```powershell
python --version
python -c "import sys; print(sys.executable)"
python -c "import fastapi, sqlalchemy, aiomysql, xgboost; print('dependencies ok')"
```

预期包含：

```text
Python 3.11.x
dependencies ok
```

参数说明：

- `--project .\uv`：读取 `uv/pyproject.toml` 和 `uv/uv.lock`；
- `--frozen`：严格使用锁定版本；
- `--python 3.11`：固定Python 3.11；
- `--no-install-project`：只安装依赖，不把 `uv` 子目录当应用包；
- `UV_PROJECT_ENVIRONMENT`：把环境固定在根目录 `.venv`。

在PyCharm的项目解释器中选择该uv环境，然后重新打开Terminal。终端提示符通常会显示 `(.venv)`；`sys.executable` 应指向当前项目的uv虚拟环境。后续统一使用 `python ...`，依赖PyCharm激活的项目uv环境，不再指定解释器路径。

## 六、第5步：运行本地测试

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest -q
python -m compileall -q app scripts
```

测试必须全部通过后再继续。

## 七、第6步：从零初始化数据库

这是完整流程中唯一的删库步骤：

```powershell
python scripts\init_db.py --reset --yes
```

脚本按顺序执行：

1. 删除并创建 `.env` 中的 `bank_risk`；
2. 创建8张银行业务表；
3. 导入确定性银行样例；
4. 创建9张通用风控表；
5. 导入12条银行风控规则。

末尾应显示初始化成功且失败数为0。如果出现 `Access denied`，检查 `.env` 的MySQL用户名和密码；如果无法连接，回到第2步。

以后只补表和初始数据、不删库时使用：

```powershell
python scripts\init_db.py --keep-data
```

## 八、第7步：生成可复现业务流水

```powershell
python scripts\gen_business_data.py --count 300 --seed 42
```

编程逻辑：

- `seed=42` 保证客户、卡、设备、IP和流水主键可复现；
- 生成300条交易，并按比例生成贷款和登录记录；
- 每10条注入一个可解释风险模式；
- 卡号、身份证和设备敏感标识保存SHA-256摘要；
- 使用 `INSERT IGNORE`，相同seed重复运行不会重复插入业务记录。

这一步只生成银行业务事实，还没有生成机器学习训练样本。

## 九、第8步：验证四场景规则链

```powershell
python scripts\verify_bank_e2e.py
```

脚本会真实连接MySQL并验证：

- 当前数据库有17张表和12条规则；
- 银行业务样例不少于100条；
- 转账 `TXN_GEO_001` 命中R001；
- 信用卡 `TXN_CC_RISK` 命中R003；
- 贷款 `LOAN_MULTI_1` 命中R012；
- 登录 `LOGIN_PROXY` 命中R025；
- 涉诈收款卡 `TXN_BLACK_CARD` 命中R030。

脚本会写入5次风控评估，这是验收行为，不是只读查询。

## 十、第9步：按指定天数和数量生成训练样本

先在终端设置两个参数。示例表示“最近7天、共1000条”：

```powershell
$days = 7
$samples = 1000
python scripts\gen_train_dataset.py --repeats 12 --seed 42 --samples $samples --days $days
```

必须看到：

```text
训练样本生成完成: 计划 1000，成功 1000，失败 0
```

- `--days` 控制评估与案件覆盖最近多少天，例如 `7` 表示今天及之前6天；
- `--samples` 控制实际生成多少条评估；
- 当请求数量超过当前业务源数量时，脚本会自动增加重复轮数，保证精确生成指定数量；
- 关联事件、案件和自动审核日志会使用一致的历史时间，使仪表盘形成完整趋势曲线。

每个样本都会经过完整在线链路：

1. 选择交易、贷款或登录业务记录；
2. 校验事件类型、业务记录和客户归属；
3. 检查用户、设备、IP、银行卡和身份证黑名单；
4. 写入不可变 `risk_event`；
5. 计算客户10维、事件10维、上下文5维，共25维特征；
6. 将特征快照写入 `risk_feature`；
7. 执行当前场景规则并写入 `risk_assessment`；
8. 高风险样本创建或复用 `risk_case`；
9. 更新客户画像并提交事务。

脚本启动时会显式卸载当前进程中的旧XGBoost模型，确保本轮标签只来自规则决策，并让新评估保持 `ml_score=NULL`。这是为了避免“使用旧模型输出训练新模型”的数据泄漏。

训练样本生成不是幂等操作，再运行一次会继续新增评估。因此需要全新数据时应先执行第6步 `--reset --yes`。`XGB_TRAIN_DATA_LIMIT` 只是训练命令未提供 `--samples` 时的默认值，推荐始终显式传入相同的 `$samples`。

## 十一、第10步：使用相同数量训练XGBoost

```powershell
python scripts\train_xgb_model.py --samples $samples
```

训练逻辑：

1. 读取最近 `$samples` 条 `ml_score IS NULL` 的评估；
2. 按 `event_id` 批量读取25维特征；
3. 严格按 `FEATURE_COLUMNS` 拼成 `$samples × 25` 矩阵；
4. `通过/标记` 映射为0，`人工审核/拒绝` 映射为1；
5. 分层拆分80%训练集和20%验证集；
6. 使用AUC早停，计算AUC、F1、准确率、精确率和召回率；
7. 保存 `app/engine/xgb_model.json`；
8. 输出Top 10特征重要性。

检查模型文件：

```powershell
Test-Path .\app\engine\xgb_model.json
Get-Item .\app\engine\xgb_model.json | Select-Object FullName,Length,LastWriteTime
```

`Test-Path` 应返回 `True`。训练脚本会严格校验实际可加载数量等于 `--samples`，数量不足或25维特征不完整会直接停止，避免“生成数量和训练数量不一致”。1000条低于正式训练建议的1250条，可能出现小样本警告；教学模拟允许继续。

如果没有MySQL历史样本，只想验证算法接口，可以运行：

```powershell
python scripts\train_demo_model.py
```

完整复现主流程应使用 `train_xgb_model.py`。

## 十二、第11步：回填历史模型评分

训练样本在生成阶段故意保存 `ml_score=NULL`，否则旧模型输出会泄漏到新模型训练。训练完成后必须用新模型回填：

```powershell
python scripts\backfill_ml_score.py
```

该命令默认回填全部 `ml_score=NULL` 的评估。完成后，评估历史和案件详情不再大面积显示“-”，而会显示新模型的拒绝概率和模型决策。只想限制回填数量时可使用：

```powershell
python scripts\backfill_ml_score.py --samples $samples
```

## 十三、第12步：启动系统

```powershell
python run_app.py
```

启动脚本依次检查 `.env`、Python依赖、MySQL、数据库、8000端口和模型文件，然后启动FastAPI。应用启动时会真正加载XGBoost模型；按 `Ctrl+C` 停止时会先停止调度器，再释放aiomysql连接池。

访问地址：

- 管理页面：<http://127.0.0.1:8000>
- OpenAPI：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

## 十四、第13步：最终API验收

保持服务终端运行，打开第二个PowerShell：

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health'
```

重点确认：

```text
status            = ok
industry          = bank
xgb_loaded        = True
scheduler_running = True
```

调用转账风控接口：

```powershell
$payload = @{
    event_type = '转账'
    source_id  = 'TXN_GEO_001'
    user_id    = 'U002'
    event_data = @{}
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
    -Uri 'http://127.0.0.1:8000/api/risk/check' `
    -Method Post `
    -ContentType 'application/json; charset=utf-8' `
    -Body ([Text.Encoding]::UTF8.GetBytes($payload))
```

响应应包含 `assessment_id`、`event_id`、`final_score`、`decision`、R001规则命中、25维特征，以及模型加载后的 `ml_score` 和 `ml_decision`。至此数据库、业务流水、规则、特征、训练、模型加载和在线推理闭环完成。

## 十五、参数化一键清库重建

只有在 `.env` 和 `uv sync` 已完成，并理解 `--reset` 会删库后，才使用：

```powershell
python scripts\one_command.py --prepare --reset --days 7 --samples 1000 --business-count 300 --seed 42 --no-start
```

它依次执行：

```text
重建数据库
→ 生成300条业务流水
→ 按最近7天生成1000条纯规则训练样本
→ 使用相同1000条训练XGBoost
→ 回填全部历史ML评分
```

确认上述步骤全部完成后启动服务：

```powershell
python run_app.py
```

参数可自由调整，例如生成最近30天、5000条，并用同样5000条训练：

```powershell
python scripts\one_command.py --prepare --reset --days 30 --samples 5000 --business-count 600 --seed 42 --no-start
```

参数说明：

| 参数 | 含义 | 默认值 |
|---|---|---:|
| `--days` | 评估、事件和案件分布天数 | 7 |
| `--samples` | 生成数量，同时也是训练读取数量 | 1000 |
| `--business-count` | 额外业务交易流水数量 | 300 |
| `--seed` | 随机种子，相同参数可复现 | 42 |
| `--reset` | 删除并重建教学数据库 | 不启用 |
| `--no-start` | 准备完成后不自动启动服务 | 不启用 |
| `--skip-backfill` | 不回填历史模型评分 | 不启用 |

只启动已经准备好的系统：

```powershell
python scripts\one_command.py
```

第一次建议手动执行各步骤，以便准确定位失败位置；熟悉后再使用参数化一键命令。

## 十六、核心编程逻辑

### 16.1 四场景统一入口

`app/service/event.py::process_event()` 接收固定四字段：

```json
{
  "event_type": "转账",
  "source_id": "TXN_GEO_001",
  "user_id": "U002",
  "event_data": {}
}
```

| event_type | 业务事实表 |
|---|---|
| 信用卡 | `bank_transaction` |
| 转账 | `bank_transaction` |
| 贷款 | `loan_application` |
| 登录 | `login_log` |

业务表只保存事实，风控表保存事件、特征、评估、案件和审计。

### 16.2 规则引擎

规则支持递归 `and/or`：

```json
{
  "and": [
    {"field": "event_geo_mismatch", "op": "==", "value": 1},
    {"field": "event_amount", "op": ">", "value": 50000}
  ]
}
```

支持 `> >= < <= == != in not_in between`。规则字段必须来自统一的25维 `FEATURE_COLUMNS`，避免训练和在线推理错位。

### 16.3 规则与模型融合

`app/engine/decision.py::_calculate_decision()`：

1. 规则命中计算可解释规则分；
2. 模型输出拒绝概率；
3. 按规则权重和模型权重融合；
4. 一票否决规则优先；
5. 最终映射为通过、标记、人工审核、拒绝。

模型不存在或加载失败时，系统自动退化为纯规则模式，不阻断核心业务。

## 十七、目录结构

```text
app/
  engine/                 # 特征、规则、XGBoost和七步决策
  service/                # 事件编排、案件、告警和审计
  agent/                  # 银行风控Agent工具
  routers/                # FastAPI路由
  models_business.py      # 8张银行业务ORM
  models_risk.py          # 9张风控ORM
sql/                      # 表、初始数据和12条规则
scripts/                  # 初始化、造数、训练、验证和启动
templates/ + static/      # Web管理端
docs/                     # 任务规划和演示资料
tests/                    # 本地契约测试
uv/                       # pyproject.toml、uv.lock和精确依赖
```

业务定义见 [1-业务说明.md](1-业务说明.md)，任务拆解见 [docs/任务规划与实现对照.md](docs/任务规划与实现对照.md)。

## 十八、常见问题

### 18.1 `python -m venv .venv` 没有输出

标准venv成功时本来就不输出，但本项目无需执行它，直接使用第4步的 `uv sync`。

### 18.2 创建 `.venv` 时 `Permission denied`

通常是PyCharm正在安装包或占用 `.venv\Scripts\python.exe`。停止相关任务后再执行 `uv sync`，不要同时运行 `python -m venv` 和 `uv sync`。

### 18.3 环境被创建到 `uv\.venv`

说明漏掉：

```powershell
$env:UV_PROJECT_ENVIRONMENT = (Join-Path (Get-Location) '.venv')
```

重新设置并同步，然后在PyCharm中选择根目录 `.venv` 对应的uv解释器。

### 18.4 MySQL报 `Access denied`

检查 `.env` 的 `DB_USER` 和 `DB_PASSWORD`，并确保所有脚本从项目根目录运行。

### 18.5 如何自定义生成天数和训练数量

必须显式执行：

```powershell
$days = 14
$samples = 3000
python scripts\gen_train_dataset.py --repeats 12 --seed 42 --samples $samples --days $days
python scripts\train_xgb_model.py --samples $samples
python scripts\backfill_ml_score.py
```

生成和训练必须传相同的 `$samples`。需要干净数据时，推荐直接使用参数化一键清库命令，不要在旧数据上反复追加。

### 18.6 `RuntimeError: Event loop is closed`

当前入口已在事件循环关闭前释放连接池。请使用 `run_app.py` 启动，并用 `Ctrl+C` 正常停止，不要直接关闭整个PyCharm进程。

### 18.7 1000条低于推荐1250条

这是质量提醒，不阻断教学训练。项目按需求使用1000条模拟数据，正式训练再扩大样本量。

### 18.8 训练提示没有合格样本

如果日志显示“DB总数大于0，但拉取评估为0”，说明已有评估全部带有旧模型的 `ml_score`，训练脚本为防止数据泄漏主动排除了它们。使用当前修复后的脚本再生成一轮纯规则样本，然后训练：

```powershell
python scripts\one_command.py --prepare --reset --days 7 --samples 1000 --business-count 300 --seed 42 --no-start
```

该命令会清空教学库、重新生成、训练并回填评分。如果刚执行过 `backfill_ml_score.py`，所有旧记录已有评分，下一次训练前也必须重新生成纯规则样本或直接按上述命令重建。

### 18.9 仪表盘只有一天，近7天曲线没有效果

新的造数命令已经支持 `--days 7`。如果数据库中已有大量记录且都集中在今天，不需要重复新增数据，可以将现有教学评估及关联案件均匀铺到最近7天：

```powershell
python scripts\spread_demo_history.py --days 7 --yes
```

该命令只修改 `risk_event`、`risk_assessment`、`risk_case` 和关联案件审计日志的时间字段，不删除记录，也不改变评分、决策、规则结果或模型分数。

### 18.10 8000端口被占

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
$env:APP_PORT = '8001'
python run_app.py
```

### 18.11 Agent不能回答但其他功能正常

规则、模型和API不需要LLM。只有Agent聊天需要在 `.env` 中填写有效的LLM配置。

## 十九、安全边界

- 项目样例全部为虚构数据；
- 银行卡、身份证和设备敏感标识只存摘要；
- `.env` 不应提交版本库，`.env.example` 不保存真实密钥；
- `--reset` 只能用于项目专用教学数据库；
- 本项目用于教学复现，未经安全、合规和压力测试不得处理真实资金业务。
