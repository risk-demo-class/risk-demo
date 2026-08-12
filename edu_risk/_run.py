"""
启动入口 — python _run.py
配置路径/编码/日志 → import scripts.main 触发 FastAPI 创建 → 挂载 router → 监听 0.0.0.0:8000
"""
import logging
import logging.config
import sys
from pathlib import Path

# 项目根目录进 sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(ROOT / "logs" / "server.log"),
            "formatter": "default",
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 3,
            "encoding": "utf-8",
        },
    },
    "root": {"level": "INFO", "handlers": ["console", "file"]},
}

logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger("edu_risk")

if __name__ == "__main__":
    import uvicorn
    from scripts.main import app  # noqa: F401  触发 FastAPI 创建

    logger.info("=" * 50)
    logger.info("EduRisk 教育风控系统启动中...")
    logger.info("Swagger 文档: http://localhost:8000/docs")
    logger.info("=" * 50)

    uvicorn.run(
        "scripts.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_config=LOGGING_CONFIG,
    )
