# uv 目录 — 物流风控系统环境管理

> 用 [uv](https://github.com/astral-sh/uv) 管理 Python 依赖，装包速度比 pip 快 10-100 倍
> 数据库默认 `ecs_logistics`

## 与 requirements.txt 的关系

| 文件 | 用途 |
|---|---|
| `requirements.txt`（项目根） | pip 宽松版本，教学/默认用 |
| `requirements-uv.txt` | uv 精确锁定版本（==x.y.z），跨环境一致 |
| `pyproject.toml` | 项目元数据 + 依赖范围（PEP 621） |
| `uv.lock` | 依赖树哈希锁，CI/CD 完全复现 |

## 快速启动

```bash
# 安装 uv（一次性）
powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"

# 创建虚拟环境 + 安装依赖
uv venv .venv
uv pip install -r requirements-uv.txt

# 或一键复现
uv sync
```

## 启动服务

```bash
.venv\\Scripts\\activate
python scripts\\main.py
# 访问 http://localhost:8000
```

## 物流风控系统依赖说明

项目核心依赖：FastAPI / SQLAlchemy / aiomysql / XGBoost / LangChain + Qwen-Plus

**关键版本**：Python 3.12+ / XGBoost 2.1+ / FastAPI 0.115+ / SQLAlchemy 2.0+", "filePath": "D:\\Projects\\My_Pycharm\\risk\\Logistics_risk\\risk-demo\\linhuangqin\\uv\\README.md"}