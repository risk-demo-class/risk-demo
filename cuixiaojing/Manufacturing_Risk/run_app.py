"""
一键启动脚本.

启动前自动做 4 步自检:
  1. Python 核心依赖是否装好
  2. MySQL 是否在跑 (localhost:3306)
  3. 数据库是否已初始化 (risk_rule 表能否查询)
  4. 端口是否被占

致命问题 (FAIL) → 直接 sys.exit(1)
警告 (WARN)     → 打印提示 + 让用户决定是否继续
"""
import os
import socket
import sys

# 让中文日志别报 UnicodeEncodeError
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings  # noqa: E402


def _check_dependencies() -> tuple[str, str]:
    """检查核心 Python 依赖. 任意一个失败 → FAIL."""
    required = {
        "fastapi": "FastAPI Web 框架",
        "uvicorn": "ASGI 服务器",
        "sqlalchemy": "ORM",
        "pymysql": "MySQL 驱动 (同步)",
        "aiomysql": "MySQL 驱动 (异步)",
        "pydantic": "数据校验",
        "pydantic_settings": "配置管理",
        "jinja2": "模板引擎",
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
            "\n         跑: uv sync  (或 uv pip install -r pyproject.toml)"
        )
    return "OK", f"所有 {len(required)} 个核心依赖已装"


def _check_mysql_alive() -> tuple[str, str]:
    """检查 MySQL 是否可连."""
    try:
        import pymysql
        conn = pymysql.connect(
            host=settings.DB_HOST, port=settings.DB_PORT,
            user=settings.DB_USER, password=settings.DB_PASSWORD,
            database=settings.DB_NAME, connect_timeout=3,
        )
        conn.close()
        return "OK", f"MySQL {settings.DB_USER}@{settings.DB_NAME} 可连"
    except Exception as e:
        return "WARN", (
            f"MySQL 连不上 (localhost:3306 {settings.DB_USER}@{settings.DB_NAME}): {type(e).__name__}\n"
            f"         业务功能会失败. 检查: MySQL 启动了? 密码对了? 先跑 scripts/init_db.py --yes?"
        )


def _check_db_initialized() -> tuple[str, str]:
    """检查数据库是否已初始化 (risk_rule 表能查)."""
    try:
        import pymysql
        conn = pymysql.connect(
            host=settings.DB_HOST, port=settings.DB_PORT,
            user=settings.DB_USER, password=settings.DB_PASSWORD,
            database=settings.DB_NAME, connect_timeout=3,
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
        if "1146" in err or "doesn't exist" in err.lower() or "1049" in err:
            return "WARN", (
                "表/库不存在, 数据库没初始化. 跑: python scripts/init_db.py --yes "
                "&& python scripts/gen_data.py"
            )
        return "WARN", f"数据库状态未知: {type(e).__name__}: {err[:80]}"


def _check_port_available(port: int = 8000) -> tuple[str, str]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.bind(("0.0.0.0", port))
        return "OK", f"端口 {port} 空闲"
    except OSError:
        return "WARN", f"端口 {port} 被占, 杀占用进程或设 APP_PORT 环境变量换端口"
    finally:
        sock.close()


def preflight_checks() -> list[tuple[str, str, str]]:
    checks = [
        ("Python 依赖", _check_dependencies),
        ("MySQL 连接", _check_mysql_alive),
        ("数据库初始化", _check_db_initialized),
        ("端口", _check_port_available),
    ]
    results = []
    for name, fn in checks:
        try:
            level, msg = fn()
        except Exception as e:
            level, msg = "FAIL", f"自检脚本异常: {type(e).__name__}: {e}"
        results.append((level, name, msg))
    return results


def _print_preflight(results: list[tuple[str, str, str]]) -> bool:
    print("=" * 60)
    print("【启动前自检】")
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
        print("有致命问题, 启动取消. 修完上面 FAIL 项再跑.")
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
    if not _print_preflight(results):
        sys.exit(1)

    from app.logging_config import LOGGING_CONFIG  # noqa: E402
    import uvicorn  # noqa: E402
    from scripts.main import app  # noqa: E402

    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run(
        app, host="0.0.0.0", port=port,
        log_level="info", log_config=LOGGING_CONFIG,
    )
