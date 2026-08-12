"""Structured daily-rotating application, access, decision and alert logs."""

from __future__ import annotations

import logging.config
from pathlib import Path
from typing import Any

from app.config import settings


LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "bankrisk.log"
ACCESS_LOG_FILE = LOG_DIR / "access.log"
DECISION_LOG_FILE = LOG_DIR / "risk_decision.log"
ALERT_LOG_FILE = LOG_DIR / "alerts.log"


def _daily_file_handler(filename: Path, level: str = "INFO") -> dict[str, Any]:
    return {
        "class": "logging.handlers.TimedRotatingFileHandler",
        "formatter": "json",
        "level": level,
        "filename": str(filename),
        "when": "midnight",
        "interval": 1,
        "backupCount": settings.LOG_RETENTION_DAYS,
        "encoding": "utf-8",
        "utc": True,
        "delay": True,
    }


def build_logging_config() -> dict[str, Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "level": settings.LOG_LEVEL,
        },
        "app_file": _daily_file_handler(LOG_FILE),
        "access_file": _daily_file_handler(ACCESS_LOG_FILE),
        "decision_file": _daily_file_handler(DECISION_LOG_FILE),
        "alert_file": _daily_file_handler(ALERT_LOG_FILE, level="ERROR"),
    }
    # Keep an empty alert file present so the collector can watch it before the
    # first incident occurs; other high-volume files remain lazily opened.
    handlers["alert_file"]["delay"] = False
    root_handlers = ["console", "app_file", "alert_file"]
    if settings.ALERT_WEBHOOK_URL:
        handlers["alert_webhook"] = {
            "()": "app.observability.WebhookAlertHandler",
            "formatter": "json",
            "level": "ERROR",
            "endpoint": settings.ALERT_WEBHOOK_URL,
            "timeout_seconds": settings.ALERT_WEBHOOK_TIMEOUT_SECONDS,
        }
        root_handlers.append("alert_webhook")

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": "app.observability.JsonLogFormatter"},
        },
        "handlers": handlers,
        "loggers": {
            "bankrisk.access": {
                "handlers": ["access_file"],
                "level": "INFO",
                "propagate": False,
            },
            "bankrisk.decision": {
                "handlers": ["decision_file", "console"],
                "level": "INFO",
                "propagate": False,
            },
            "bankrisk.validation": {
                "handlers": ["decision_file", "console"],
                "level": "INFO",
                "propagate": False,
            },
            "httpx": {
                "handlers": [],
                "level": "WARNING",
                "propagate": True,
            },
            "uvicorn.access": {
                "handlers": [],
                "level": "WARNING",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": root_handlers,
                "level": settings.LOG_LEVEL,
                "propagate": False,
            },
        },
        "root": {
            "handlers": root_handlers,
            "level": settings.LOG_LEVEL,
        },
    }


def configure_logging() -> None:
    logging.config.dictConfig(build_logging_config())
