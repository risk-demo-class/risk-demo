"""只读启动自检：环境、依赖、MySQL、表结构、端口和模型。"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.database import async_engine  # noqa: E402
from app.engine.ml_model import model_status  # noqa: E402


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    critical: bool = False


def _port_available() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((settings.APP_HOST, settings.APP_PORT))
            return True
        except OSError:
            return False


async def run_checks(skip_port: bool = False) -> list[Check]:
    checks = [
        Check("Python", "PASS" if sys.version_info[:2] == (3, 11) else "FAIL", sys.version.split()[0], True),
        Check(".env", "PASS" if (PROJECT_ROOT / ".env").exists() else "FAIL", "存在" if (PROJECT_ROOT / ".env").exists() else "缺失", True),
    ]
    dependencies = ("fastapi", "sqlalchemy", "aiomysql", "xgboost", "sklearn", "openai")
    missing = [name for name in dependencies if importlib.util.find_spec(name) is None]
    checks.append(Check("依赖", "PASS" if not missing else "FAIL", "完整" if not missing else f"缺少: {', '.join(missing)}", True))
    try:
        async with async_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            tables = (await connection.execute(text("SHOW TABLES"))).all()
            admin_hash = (await connection.execute(
                text("SELECT password_hash FROM app_user WHERE username = :username"),
                {"username": settings.DEFAULT_ADMIN_USERNAME.lower()},
            )).scalar_one_or_none()
        checks.append(Check("MySQL", "PASS", f"连接成功，当前库 {len(tables)} 张表", True))
        checks.append(Check("表结构", "PASS" if len(tables) == 18 else "FAIL", f"期望 18，实际 {len(tables)}", True))
        password_safe = bool(admin_hash and admin_hash != settings.DEFAULT_ADMIN_PASSWORD and admin_hash.startswith("$argon2"))
        checks.append(Check("默认管理员", "PASS" if password_safe else "FAIL", "密码已使用 Argon2 摘要" if password_safe else "账户缺失或密码未安全摘要", True))
    except Exception as exc:
        checks.append(Check("MySQL", "FAIL", f"连接失败: {type(exc).__name__}", True))
    finally:
        await async_engine.dispose()
    status = model_status()
    checks.append(Check("XGBoost", "PASS" if status["loaded"] else "WARN", "已加载" if status["loaded"] else "未加载，将使用纯规则"))
    checks.append(Check("LLM", "PASS" if settings.LLM_API_KEY else "WARN", "已配置" if settings.LLM_API_KEY else "未配置，本地只读助手仍可用"))
    if not skip_port:
        available = _port_available()
        checks.append(Check("端口", "PASS" if available else "FAIL", f"{settings.APP_HOST}:{settings.APP_PORT} {'可用' if available else '已占用'}", True))
    return checks


def print_checks(checks: list[Check]) -> None:
    for check in checks:
        print(f"[{check.status:<4}] {check.name:<10} {check.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="医疗风控启动自检")
    parser.add_argument("--skip-port", action="store_true", help="已有服务运行时跳过端口检查")
    args = parser.parse_args()
    checks = asyncio.run(run_checks(skip_port=args.skip_port))
    print_checks(checks)
    failed = [item for item in checks if item.critical and item.status == "FAIL"]
    if failed:
        print("启动自检未通过，请先处理关键项。")
        return 1
    print("启动自检通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
