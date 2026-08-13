# 基线验证报告

> 验证日期：2026-08-11；结论：**基线未全量通过**。可行子集通过，但完整套件存在旧绝对路径和本机 MySQL 凭据两个已知阻塞。

## 1. 基线与导入

| 项目 | 结果 |
|---|---|
| 只读源 | `D:\Program Files\temp_data\Projects\SGG_projects\sgg_AI_RISK_demo` |
| 源提交 | `384abb3d3f2f0f221ab98571ee19b0061a68c465` |
| 源状态 | `main...origin/main`；仅有未跟踪 `1-业务说明.md` |
| 导入范围 | 仅源 `HEAD` 已跟踪内容；未导入源 `.git` 和未跟踪草稿 |
| 目标初始提交 | `e6592344e45d630bf6c9e94ea6cb46c8e270f078`（`chore: import e-commerce risk-control baseline`） |
| 目标保留项 | `PROMPTS_README.md` 与 `prompts/` 已保留并纳入独立历史 |
| 测试规模 | 38 个测试文件；静态发现 453 个 `test_*` 定义；`pytest` 实际收集 451 项 |

导入后再次读取源仓库：提交 ID 未变，状态仍只有原先未跟踪草稿，说明源基线未被修改。

## 2. 环境准备

- 操作系统：Windows；Shell：PowerShell。
- Python：`3.12.8`，虚拟环境：目标目录下已被 `.gitignore` 忽略的 `.venv`。
- 关键依赖：`pytest 8.3.4`、`fastapi 0.115.6`、`sqlalchemy 2.0.36`、`xgboost 2.0.3`。
- 初始系统 Python 缺少 `pytest`；首次 `pip install` 还遇到 Windows GBK 解码问题。设置 `PYTHONUTF8=1` 后，按 `requirements.txt` 完成安装；`pip check` 返回 `No broken requirements found.`。

## 3. 命令与结果

### 收集检查

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider
```

结果：`451 tests collected in 12.71s`；另有 `pytest-asyncio` 未显式配置默认 fixture loop scope 的弃用警告。

### 完整测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

结果：`383 passed, 1 failed, 2 skipped, 65 errors in 23.30s`。

- **65 个 error**：以下 5 个测试文件硬编码旧路径 `D:/workroom/尚硅谷大模型项目之风控系统/3.代码/AI_Risk`，在当前工作区读取模板或 `static/app.js` 时触发 `FileNotFoundError`：
  - `tests/test_blacklist_reject_ui.py`
  - `tests/test_cond_builder_grid_layout.py`
  - `tests/test_cond_json_editor.py`
  - `tests/test_modal_init_timing.py`
  - `tests/test_rule_level_event_config.py`
- **1 个 failed**：`tests/test_scheduler.py::TestRunOnceReturnType::test_run_once_returns_dict_with_correct_types` 连接本机 MySQL 时返回 `(1045) Access denied for user 'root'@'localhost'`。本阶段未获取或猜测数据库凭据，也未创建/删除数据库。
- **2 个 skipped**：`tests/test_ddl_sync.py` 默认要求 `DDL_CHECK_ENABLED=1` 和真实数据库；`tests/test_xgboost.py::TestModelLoad::test_load_real_model` 要求先生成模型文件。

### 可行子集

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider `
  --ignore=tests/test_cond_builder_grid_layout.py `
  --ignore=tests/test_cond_json_editor.py `
  --ignore=tests/test_modal_init_timing.py `
  --ignore=tests/test_rule_level_event_config.py `
  -k "not TestRiskCheckPageBlacklistHint and not test_run_once_returns_dict_with_correct_types"
```

结果：`348 passed, 2 skipped, 4 deselected in 22.51s`。这只证明未被上述环境阻塞的子集通过，不能替代完整套件结论。

## 4. 后续复现与解除阻塞

1. 将上述 5 个测试文件的项目根改为相对 `Path(__file__)` 解析后，重新运行完整套件；该修复不属于 Goal 1。
2. 准备隔离的 MySQL 测试实例，并在 `.env` 中配置 `DB_*` 和 `TEST_DB_NAME=bank_risk_test`；不得把凭据提交。随后运行：

```powershell
$env:DDL_CHECK_ENABLED='1'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

3. 只有完成银行数据层与训练流程后，才生成模型文件并复测真实模型加载；Goal 1 不生成或提交模型产物。

