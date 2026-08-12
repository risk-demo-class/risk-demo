# AGENTS.md

电商风控系统 (AI_Risk)：FastAPI + SQLAlchemy 2.0 + MySQL 8.0 + XGBoost 双轨（规则 + ML）+ LangChain Agent 的教学项目。**全部代码注释 / 文档 / 测试 / 提交信息都是中文**，改动保持一致。

## 环境

- Python **3.11–3.12**，禁用 3.13（`uv/pyproject.toml` 要求 `>=3.11,<3.13`）。
- MySQL 8.0；连接参数由根目录 `.env` 提供（`app/config.py::Settings` 用 pydantic-settings 加载）。`docker/.env.example` 是 Docker compose 专用模板，**不要**复制到根目录当 `.env`。
- 装依赖：`uv pip install -r uv/requirements-uv.txt` 或 `pip install -r requirements.txt`。
- 安全：`.env`（含真实 DB/LLM 凭据）**已被 git 跟踪**，仓库也没有 `.gitignore`——不要新增提交任何密钥或日志文件。

## 命令（都必须在项目根目录执行）

| 操作 | 命令 |
|---|---|
| 启动服务 | `python run_app.py`（6 步自检后起 uvicorn:8000，推荐） |
| 直接启动 | `python scripts/main.py` |
| 初始化 DB | `python scripts/init_db.py --yes` |
| **危险** | `init_db.py --drop` / `--reset` 会删库重建、清空数据 |
| 跑全部测试 | `python -m pytest tests/` |
| 跑单个文件 | `python -m pytest tests/test_risk_decision.py -v` |
| DDL 校验 | `DDL_CHECK_ENABLED=1 python -m pytest tests/test_ddl_sync.py`（默认 skip，需真实 DB） |
| 训练模型 | `python scripts/train_xgb_model.py` → 写 `app/engine/xgb_model.json` |
| 一条龙 | `python scripts/one_command.py`（6 步：init_db → gen_risky_users → gen_train_dataset → train → backfill_ml_score → gen_risk_data_with_dates） |

## 测试

- 必须用 `python -m pytest`（把 cwd 加进 sys.path）。**裸 `pytest tests/` 会 `ModuleNotFoundError: No module named 'app'`**——README 里 `pytest tests/` 的写法已过期。
- pytest 配置（`asyncio_mode=strict` 等）在 `uv/pyproject.toml`，从根目录跑不会加载（会有 pytest-asyncio deprecation warning，属正常）；asyncio 测试要显式加 `@pytest.mark.asyncio`。
- 基线（当前环境）：**329 过 / 1 挂 / 1 skip**。唯一挂的 `tests/test_run_preflight.py::test_mysql_down` 断言错误信息含 `localhost:3306`，`.env` 的 DB_HOST 指向远程主机时必挂，属环境相关，不是代码回归。1 个 skip 是 `test_ddl_sync.py`（需 `DDL_CHECK_ENABLED=1`）。
- 大部分测试不需要真实 DB，但会真实访问 MySQL（如 preflight 检查），本地得开着 MySQL。

## 架构

- `app/routers/` HTTP 路由，`app/api.py` 汇总注册；前端是 Jinja2 服务端渲染（`templates/` + `static/app.js`），改页面要动模板。
- `app/engine/` 风控核心：`rule.py`（规则引擎）、`feature.py`（25 维特征）、`decision.py`（规则+ML 加权融合）、`ml_model.py`（XGBoost 加载/预测）。
- `app/service/` 业务层（event/case/alert/action_log/validator），`app/agent/` LangChain agent，`app/scheduler.py` 后台调度（案件超时关案 + 告警检查，由 FastAPI lifespan 启停）。
- `scripts/` 一次性 CLI 脚本；`sql/` DDL + 种子 + 迁移；`docker/` 生产部署（compose：MySQL + app + nginx）。

## 陷阱

- **XGBoost 降级**：`app/engine/xgb_model.json` 不存在时自动走纯规则，业务照常；模型在 import `app.engine.ml_model` 时自动加载。
- **加特征**：改 `feature.py` 特征 dict → 同步 `ml_model.py::FEATURE_COLUMNS`（25 维）→ 重训 → 过 `tests/test_xgboost.py::test_feature_columns_align_with_feature_module`，否则对齐测试挂。
- **不要用 `reload=True` 起 uvicorn**：lifespan 会让 scheduler 起两遍。`scripts/main.py` 已固定 `reload=False`。
- **软删**：`risk_rule` / `risk_blacklist` 用 `deleted_at` 软删，所有查询都过滤 `deleted_at IS NULL`（规则、黑名单、列表）。
- **日志**：统一走 `app/logging_config.py`，stdout + `logs/app.log`（50MB × 5 轮转）；业务代码用 `logging.getLogger(__name__)`，别另起 logger。
- **状态机**：案件流转白名单在 `app/service/case.py::_ALLOWED_CASE_TRANSITIONS`，改动前先看它。
- 训练数据正例不足时，用 `scripts/gen_risk_data.py --count N --balance-pos` 或 `gen_train_dataset.py` 补齐，再训练。
