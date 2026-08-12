"""教育风控 Web 应用启动入口。"""

from __future__ import annotations

import os
import sys

from app.logging_config import LOGGING_CONFIG, setup_logging


def preflight() -> None:
    from sqlalchemy import inspect, text
    from app.database import engine

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    required = {"user_info", "risk_rule", "risk_assessment", "risk_case"}
    missing = required - set(inspect(engine).get_table_names())
    if missing:
        raise RuntimeError(f"数据库未初始化，缺少表: {sorted(missing)}")


if __name__ == "__main__":
    setup_logging()
    try:
        preflight()
    except Exception as exc:
        print(f"启动检查失败: {exc}")
        print("请先运行: docker compose up -d && python scripts/init_db.py --yes")
        sys.exit(1)
    import uvicorn

    port = int(os.getenv("APP_PORT", "8000"))
    print(f"教育风控系统: http://127.0.0.1:{port}")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_config=LOGGING_CONFIG,
    )
