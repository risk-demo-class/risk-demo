"""Dependency-safe startup preflight followed by Uvicorn launch."""

from __future__ import annotations

import argparse
import importlib.util
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REQUIRED_MODULES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "sqlalchemy": "sqlalchemy",
    "aiomysql": "aiomysql",
    "aiosqlite": "aiosqlite",
    "pydantic-settings": "pydantic_settings",
    "jinja2": "jinja2",
    "neo4j": "neo4j",
    "numpy": "numpy",
    "scikit-learn": "sklearn",
    "xgboost": "xgboost",
    "networkx": "networkx",
}
REQUIRED_PATHS = [
    ROOT / "app" / "api.py",
    ROOT / "app" / "engine" / "decision.py",
    ROOT / "app" / "engine" / "rule_catalog.py",
    ROOT / "app" / "engine" / "fusion.py",
    ROOT / "app" / "engine" / "model_manager.py",
    ROOT / "app" / "engine" / "graph.py",
    ROOT / "app" / "bootstrap.py",
    ROOT / "app" / "logging_config.py",
    ROOT / "app" / "observability.py",
    ROOT / "app" / "agent" / "tools.py",
    ROOT / "templates" / "dashboard.html",
    ROOT / "static" / "app.css",
]


@dataclass(slots=True)
class Check:
    name: str
    ok: bool
    detail: str
    fatal: bool = False


def _load_env_value(name: str, default: str) -> str:
    """Read process env only; pydantic-settings loads .env after dependencies pass."""
    return os.getenv(name, default)


def _port_available(host: str, port: int) -> bool:
    bind_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((bind_host, port)) != 0


def run_preflight(host: str, port: int) -> list[Check]:
    py_ok = (3, 11) <= sys.version_info[:2] < (3, 14)
    checks = [
        Check("Python", py_ok, sys.version.split()[0], fatal=True),
        Check(".env", (ROOT / ".env").exists(), "存在" if (ROOT / ".env").exists() else "未创建，可先复制 .env.example"),
    ]

    missing = [display for display, module in REQUIRED_MODULES.items() if importlib.util.find_spec(module) is None]
    checks.append(
        Check(
            "Python依赖",
            not missing,
            "已安装" if not missing else f"缺少: {', '.join(missing)}",
            fatal=True,
        )
    )

    missing_paths = [str(path.relative_to(ROOT)) for path in REQUIRED_PATHS if not path.exists()]
    checks.append(
        Check(
            "项目结构",
            not missing_paths,
            "完整" if not missing_paths else f"缺少: {', '.join(missing_paths)}",
            fatal=True,
        )
    )
    port_is_available = _port_available(host, port)
    checks.append(
        Check(
            f"端口 {port}",
            port_is_available,
            "可用" if port_is_available else "已被占用",
            fatal=True,
        )
    )
    return checks


def print_preflight(checks: list[Check]) -> None:
    print("=" * 68)
    print("BankRisk-AI 启动前自检 · complete-three-layer")
    print("=" * 68)
    for check in checks:
        state = "OK" if check.ok else ("FAIL" if check.fatal else "WARN")
        print(f"[{state:<4}] {check.name:<14} {check.detail}")
    print("=" * 68)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BankRisk-AI startup")
    parser.add_argument("--check", action="store_true", help="仅运行启动前自检")
    parser.add_argument("--host", default=_load_env_value("APP_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(_load_env_value("APP_PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="开发模式自动重载")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = run_preflight(args.host, args.port)
    print_preflight(checks)
    fatal = [check for check in checks if check.fatal and not check.ok]
    if fatal:
        print("自检未通过。若缺少依赖，请运行: python -m pip install -r requirements.txt")
        return 1
    if args.check:
        print("完整项目启动自检通过。")
        return 0

    import uvicorn

    uvicorn.run("app.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
