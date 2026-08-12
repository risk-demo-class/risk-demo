"""
统一日志配置: 业务 logger + uvicorn 全走 console + logs/app.log (50MB × 5 滚动)
"""
import logging.config
import logging.handlers
import os


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")
APP_LOG_FILE = os.path.join(LOG_DIR, "app.log")

MAX_BYTES = 50 * 1024 * 1024
BACKUP_COUNT = 5

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def build_logging_config(log_file: str = APP_LOG_FILE, level: str = "INFO") -> dict:
    """构造 logging.dictConfig 配置字典."""
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {"format": LOG_FORMAT, "datefmt": DATE_FORMAT},
        },
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
        "root": {
            "handlers": ["console", "file"],
            "level": level,
        },
        "loggers": {
            "uvicorn": {"handlers": ["console", "file"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["console", "file"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["console", "file"], "level": level, "propagate": False},
        },
    }


LOGGING_CONFIG = build_logging_config()


def setup_logging(level: str = "INFO") -> None:
    """应用启动时调用: 应用 dictConfig."""
    logging.config.dictConfig(build_logging_config(level=level))
