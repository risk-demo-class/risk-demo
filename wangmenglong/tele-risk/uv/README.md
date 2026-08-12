# uv 目录

> 用 [uv](https://github.com/astral-sh/uv) 管理 tele-risk 的 Python 环境和依赖 (参照 ai_risk)

## 这是什么？

`uv/` 目录放 uv 工具的环境说明。项目根目录的 `pyproject.toml` 是 uv 识别的项目元数据 + 依赖范围。

```
tele-risk/
├── pyproject.toml        ← uv 项目配置 (PEP 621, uv 0.5+ 直接读)
├── requirements.txt      ← pip 宽松版本 (传统 pip 用)
├── uv/
│   └── README.md         ← 本文件
└── .python-version       ← uv 自动读, 指定 Python 3.11
```

## 5 分钟上手

### 0. 安装 uv (一次性)

```bash
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1. 创建虚拟环境 + 装依赖

```bash
# 在项目根目录
uv venv                          # 创建 .venv (Python 3.11, 比 venv 快 100 倍)
uv pip install -e ".[test]"      # 装 pyproject.toml 依赖 (含测试)
```

### 2. 或用 `uv sync` 一键复现 (推荐)

```bash
uv sync                          # 自动读 pyproject.toml + 生成 uv.lock + 装依赖
```

### 3. 跑项目

```bash
# Windows PowerShell
.\.venv\Scripts\activate
python scripts/init_db.py --yes
python scripts/gen_telecom_data.py
python scripts/init_rules.py --yes
python scripts/train_xgb_model.py

# 不 activate 直接用 uv run
uv run python scripts/train_xgb_model.py
```

## 常用命令

```bash
uv add <package>                 # 加包到 pyproject.toml + 更新锁
uv add --upgrade <package>       # 升级到最新版
uv lock                          # 重新生成 uv.lock
uv run pytest tests/ -v          # 在 .venv 跑测试
uv venv --remove .venv           # 删除虚拟环境
```

## 跟 ai_risk 的关系

tele-risk 复用 ai_risk 的 docker MySQL (新建 `telecom` 库), Python 环境独立用 uv 管理。
依赖精简: 去掉 ai_risk 的 langchain/deepagents (Agent 层未实现), 保留风控核心 (sqlalchemy/xgboost/sklearn)。
