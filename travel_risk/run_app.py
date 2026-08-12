"""
旅游风控系统 - 一键启动脚本 (含 6 步启动前自检)

自检项:
  1. .env 文件是否存在
  2. Python 核心依赖是否装好
  3. MySQL 是否在跑 (localhost:3306)
  4. 数据库是否已初始化 (risk_rule 表能查)
  5. 8000 端口是否被占
  6. XGBoost 模型文件是否存在 (可选, 没训过也能跑)
"""
import os
import socket
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _check_env_file() -> tuple[str, str]:
    """检查 .env 文件."""
    if not os.path.exists(".env"):
        return "WARN", (
            ".env 不存在, 复制 docker/.env.example 为 .env 并填真实值"
            "(LLM_API_KEY / MYSQL_ROOT_PASSWORD)"
        )
    return "OK", ".env 存在"


def _check_dependencies() -> tuple[str, str]:
    """检查核心 Python 依赖."""
    required = {
        "fastapi": "FastAPI Web 框架",
        "uvicorn": "ASGI 服务器",
        "sqlalchemy": "ORM",
        "pymysql": "MySQL 驱动 (同步)",
        "aiomysql": "MySQL 驱动 (异步)",
        "pydantic": "数据校验",
        "pydantic_settings": "配置管理",
        "xgboost": "XGBoost 模型",
        "sklearn": "XGBoost 训练 + 评估",
        "numpy": "数值计算",
        "pandas": "数据处理",
    }
    missing = []
    for mod, desc in required.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(f"{mod} ({desc})")
    if missing:
        return "FAIL", (
            f"缺 {len(missing)} 个依赖: " + ", ".join(missing[:3]) +
            ("..." if len(missing) > 3 else "") +
            "\n         跑: pip install -r requirements.txt"
        )
    return "OK", f"所有 {len(required)} 个核心依赖已装"


def _check_mysql_alive() -> tuple[str, str]:
    """检查 MySQL 是否可连."""
    import pymysql
    from app.config import settings  # 加载 .env
    user = settings.DB_USER
    password = settings.DB_PASSWORD
    db = settings.DB_NAME
    host = settings.DB_HOST
    port = settings.DB_PORT
    try:
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=db, connect_timeout=3,
        )
        conn.close()
        return "OK", f"MySQL {user}@{db} 可连"
    except Exception as e:
        return "WARN", (
            f"MySQL 连不上 ({host}:{port} {user}@{db}): {type(e).__name__}\n"
            f"         业务功能会失败, 检查 MySQL 是否启动 / 密码对不对"
        )


def _check_db_initialized() -> tuple[str, str]:
    """检查数据库是否已初始化 (risk_rule 表能查)."""
    try:
        import pymysql
        from app.config import settings
        user = settings.DB_USER
        password = settings.DB_PASSWORD
        db = settings.DB_NAME
        host = settings.DB_HOST
        port = settings.DB_PORT
        conn = pymysql.connect(
            host=host, port=port, user=user, password=password,
            database=db, connect_timeout=3,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM risk_rule")
                count = cur.fetchone()[0]
            return "OK", f"数据库已初始化, risk_rule 有 {count} 条规则"
        finally:
            conn.close()
    except Exception as e:
        err = str(e)
        if "1146" in err or "doesn't exist" in err.lower():
            return "WARN", (
                "risk_rule 表不存在, 数据库没初始化. 跑: "
                "python scripts/init_db.py --yes"
            )
        return "WARN", f"数据库状态未知: {type(e).__name__}: {err[:80]}"


def _check_port_available(port: int = 8000) -> tuple[str, str]:
    """检查端口是否被占."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.bind(("0.0.0.0", port))
        return "OK", f"端口 {port} 空闲"
    except OSError:
        return "WARN", f"端口 {port} 被占, 改 APP_PORT 环境变量"
    finally:
        sock.close()


def _check_xgb_model() -> tuple[str, str]:
    """检查 XGBoost 模型文件 (可选)."""
    try:
        from app.config import settings
        path = settings.XGB_MODEL_PATH
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
        if os.path.exists(path):
            size_kb = os.path.getsize(path) / 1024
            return "OK", f"XGBoost 模型已就绪 ({size_kb:.1f} KB)"
        return "WARN", (
            f"XGBoost 模型不存在 ({settings.XGB_MODEL_PATH}), "
            f"业务仍能跑 (纯规则模式), 想用 ML 跑: python scripts/train_xgb_model.py"
        )
    except Exception as e:
        return "WARN", f"XGBoost 模型检查失败: {e}"


def preflight_checks() -> list[tuple[str, str, str]]:
    """跑全部 6 步自检, 返回 [(级别, 检查项, 消息), ...]."""
    checks = [
        (".env", _check_env_file),
        ("Python 依赖", _check_dependencies),
        ("MySQL 连接", _check_mysql_alive),
        ("数据库初始化", _check_db_initialized),
        ("端口 8000", _check_port_available),
        ("XGBoost 模型", _check_xgb_model),
    ]
    results = []
    for name, fn in checks:
        try:
            level, msg = fn()
        except Exception as e:
            level, msg = "FAIL", f"自检脚本异常: {type(e).__name__}: {e}"
        results.append((level, name, msg))
    return results


def print_preflight(results: list[tuple[str, str, str]]) -> bool:
    """打印自检结果. 返回 True 表示可以继续 (无 FAIL)."""
    print("=" * 60)
    print("【启动前自检】 旅游风控系统")
    print("=" * 60)
    for level, name, msg in results:
        mark = level
        first, *rest = msg.split("\n")
        print(f"  [{mark}] {name:<14} {first}")
        for line in rest:
            print(f"           {line.strip()}")
    print("=" * 60)
    fail = sum(1 for l, _, _ in results if l == "FAIL")
    warn = sum(1 for l, _, _ in results if l == "WARN")
    ok = sum(1 for l, _, _ in results if l == "OK")
    print(f"汇总: {ok} OK / {warn} WARN / {fail} FAIL")
    if fail > 0:
        print("有致命问题, 启动取消.")
        return False
    if warn > 0:
        print("有警告, 业务可能受影响. 按回车继续 (Ctrl+C 取消)...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            print("\n启动取消")
            return False
    else:
        print("一切就绪, 启动 uvicorn...")
    return True


if __name__ == "__main__":
    results = preflight_checks()
    if not print_preflight(results):
        sys.exit(1)

    import uvicorn
    from app.logging_config import LOGGING_CONFIG
    from scripts.main import app

    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run(
        app, host="0.0.0.0", port=port,
        log_level="info", log_config=LOGGING_CONFIG,
    )
