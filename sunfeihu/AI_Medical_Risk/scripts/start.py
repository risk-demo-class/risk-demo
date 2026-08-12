"""自检通过后启动本地医疗风控服务。"""
import asyncio

import uvicorn

from app.config import settings
from scripts.startup_check import print_checks, run_checks


def main() -> None:
    checks = asyncio.run(run_checks())
    print_checks(checks)
    if any(item.critical and item.status == "FAIL" for item in checks):
        raise SystemExit("启动已停止：自检存在关键失败项。")
    uvicorn.run("run_app:app", host=settings.APP_HOST, port=settings.APP_PORT)


if __name__ == "__main__":
    main()
