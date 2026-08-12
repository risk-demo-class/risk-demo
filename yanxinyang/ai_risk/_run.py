# -*- coding: utf-8 -*-
"""启动引导（宝典 3.1 `Start([_run.py]) --> Config[配置路径/编码/日志]`）

职责边界很清楚：
    _run.py  → **环境**：sys.path / 控制台编码 / 日志配置（LOGGING_CONFIG）
    main.py  → **装配**：App 对象 / 挂 10 个 router / 启动钩子

宝典 3.2 关键设计 ③：把日志重定向到 `logs/server.log`（同时保留控制台输出）。
"""
from __future__ import annotations

import logging
import logging.config
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_BOOTSTRAPPED = False


def _fix_console_encoding() -> None:
    """Windows 控制台默认 GBK，中文日志会 UnicodeEncodeError（FAQ 6 同源问题）。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def logging_config(level: str, log_file: str) -> dict:
    """对齐 uvicorn 的 `LOGGING_CONFIG`：控制台 + 轮转文件双输出。"""
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {"format": "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s",
                        "datefmt": "%H:%M:%S"},
            "file": {"format": "%(asctime)s | %(levelname)-7s | %(name)-22s | "
                               "%(filename)s:%(lineno)d | %(message)s",
                     "datefmt": "%Y-%m-%d %H:%M:%S"},
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "console",
                        "stream": "ext://sys.stdout", "level": level},
            "file": {"class": "logging.handlers.RotatingFileHandler", "formatter": "file",
                     "filename": log_file, "maxBytes": 5 * 1024 * 1024, "backupCount": 3,
                     "encoding": "utf-8", "level": level},
        },
        "loggers": {
            "ai_risk": {"handlers": ["console", "file"], "level": level, "propagate": False},
            # HTTP 访问日志量大，只进文件不刷屏
            "ai_risk.http": {"handlers": ["file"], "level": "INFO", "propagate": False},
        },
        "root": {"handlers": ["console", "file"], "level": "WARNING"},
    }


def bootstrap() -> None:
    """配置路径 / 编码 / 日志。幂等，可重复调用。"""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _fix_console_encoding()

    from app.config import settings  # 延迟导入：编码修好之后再读配置

    Path(settings.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(logging_config(settings.LOG_LEVEL.upper(), settings.LOG_FILE))
    _BOOTSTRAPPED = True
    logging.getLogger("ai_risk.boot").info(
        "环境就绪 | Python %s | 项目根 %s | 日志 %s",
        sys.version.split()[0], _ROOT, settings.LOG_FILE)


def main() -> None:
    bootstrap()
    from scripts.main import run
    run()


if __name__ == "__main__":
    main()
