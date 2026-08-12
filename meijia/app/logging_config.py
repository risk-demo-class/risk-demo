"""统一日志配置 (P4-L4)。

设计目标:
  1. 业务 logger (logging.getLogger(__name__)) 和 uvicorn access/error 日志
     都同时输出到 stdout + logs/app.log
  2. logs/app.log 用 RotatingFileHandler: 单文件 50 MB, 保留 5 个历史, 防磁盘爆
  3. 容器化部署 (Docker) 时 stdout 自动进容器日志, 文件作为历史归档

使用:
  # run_app.py / main.py
  from app.logging_config import LOGGING_CONFIG, setup_logging
  setup_logging()                 # 业务 logger 生效
  uvicorn.run(app, ..., log_config=LOGGING_CONFIG)
"""

from __future__ import annotations

import logging
import logging.config
import logging.handlers
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")
APP_LOG_FILE = os.path.join(LOG_DIR, "app.log")

MAX_BYTES = 50 * 1024 * 1024   # 50 MB
BACKUP_COUNT = 5                # 保留 5 个历史

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

DEFAULT_FORMATTER = {
    "format": LOG_FORMAT,
    "datefmt": DATE_FORMAT,
}


def build_logging_config(log_file: str = APP_LOG_FILE, level: str = "INFO") -> dict:
    """构造 logging.dictConfig 配置字典 (console + 轮转文件)。"""
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"default": DEFAULT_FORMATTER},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
                "level": level,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": log_file,
                "maxBytes": MAX_BYTES,
                "backupCount": BACKUP_COUNT,
                "encoding": "utf-8",
                "formatter": "default",
                "level": level,
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        },
        "root": {"handlers": ["console", "file"], "level": level},
    }


LOGGING_CONFIG = build_logging_config()


def setup_logging(log_file: str = APP_LOG_FILE, level: str = "INFO") -> None:
    """幂等地应用日志配置 (业务 logger 与 uvicorn 共用)。"""
    logging.config.dictConfig(build_logging_config(log_file, level))


if __name__ == "__main__":
    print("日志目录:", LOG_DIR)
    print("日志文件:", APP_LOG_FILE)
    print("轮转:", f"{MAX_BYTES // 1024 // 1024} MB × {BACKUP_COUNT} = 最多 {MAX_BYTES * BACKUP_COUNT // 1024 // 1024} MB")
    setup_logging()
    logging.getLogger("demo").info("这条日志会同时进 stdout 和 logs/app.log")
