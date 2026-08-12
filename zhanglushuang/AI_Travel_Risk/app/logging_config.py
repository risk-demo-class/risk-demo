"""
统一日志配置.

业务日志同时输出到 stdout 和 logs/app.log, 文件按大小轮转.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from app.config import settings

logger = logging.getLogger(__name__)


def _ensure_log_dir(log_dir: str) -> str:
    """创建日志目录, 失败时回退到当前目录."""
    try:
        os.makedirs(log_dir, exist_ok=True)
        return log_dir
    except Exception:
        logging.getLogger(__name__).exception("创建日志目录失败, 回退到当前目录")
        return "."


def setup_logging(level: str | None = None) -> None:
    """
    初始化根日志器.

    - console: 适合容器 / 前台运行
    - file: RotatingFileHandler, 50MB * 5 份
    """
    log_level = (level or settings.LOG_LEVEL or "INFO").upper()
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)

    if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
        try:
            log_dir = _ensure_log_dir(settings.LOG_DIR)
            file_handler = RotatingFileHandler(
                os.path.join(log_dir, "app.log"),
                maxBytes=50 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(log_level)
            root_logger.addHandler(file_handler)
        except Exception:
            logging.getLogger(__name__).exception("初始化文件日志失败")

    logger.info("日志初始化完成, level=%s", log_level)


if __name__ == "__main__":
    setup_logging()
    logger.info("日志配置演示")
