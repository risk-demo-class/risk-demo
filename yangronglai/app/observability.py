"""Structured, privacy-aware observability primitives for the risk platform."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from urllib import request as urllib_request
from uuid import uuid4

from fastapi import FastAPI, Request

from app.config import settings


_request_id: ContextVar[str] = ContextVar("bankrisk_request_id", default="-")
_scenario: ContextVar[str] = ContextVar("bankrisk_scenario", default="-")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,80}$")
_SENSITIVE_KEYS = {
    "authorization",
    "password",
    "token",
    "api_key",
    "secret",
    "cookie",
    "id_card",
    "id_card_hash",
    "card_no",
    "card_no_hash",
    "fingerprint_hash",
}
_IDENTIFIER_KEYS = {
    "user_id",
    "source_id",
    "device_id",
    "ip",
    "client_ip",
    "from_card",
    "to_card",
}


def new_request_id() -> str:
    """Return a server-owned unique identifier safe for logs and persistence."""
    return f"REQ_{uuid4().hex}"


def get_request_id() -> str:
    return _request_id.get()


def get_scenario() -> str:
    return _scenario.get()


def set_request_context(request_id: str, scenario: str = "-") -> tuple[Token[str], Token[str]]:
    return _request_id.set(request_id), _scenario.set(scenario)


def set_scenario(scenario: str) -> None:
    _scenario.set(scenario)


def reset_request_context(tokens: tuple[Token[str], Token[str]]) -> None:
    request_token, scenario_token = tokens
    _request_id.reset(request_token)
    _scenario.reset(scenario_token)


def pseudonymize(value: Any) -> str:
    """Create a stable, non-reversible HMAC reference for sensitive identifiers."""
    digest = hmac.new(
        settings.LOG_PSEUDONYM_KEY.encode("utf-8"),
        str(value).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"hmac:{digest[:16]}"


def sanitize_log_value(value: Any, key: str | None = None) -> Any:
    """Recursively redact secrets and pseudonymize banking identifiers."""
    normalized_key = (key or "").lower()
    if normalized_key in _SENSITIVE_KEYS or any(
        marker in normalized_key for marker in ("password", "secret", "token", "api_key")
    ):
        return "[REDACTED]"
    if normalized_key in _IDENTIFIER_KEYS:
        return pseudonymize(value) if value not in (None, "") else value
    if isinstance(value, dict):
        return {str(item_key): sanitize_log_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize_log_value(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat() if value.tzinfo else value.replace(tzinfo=UTC).isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class JsonLogFormatter(logging.Formatter):
    """Emit one JSON object per line for ingestion by a bank log platform."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": get_request_id(),
            "scenario": get_scenario(),
            "environment": settings.APP_ENV,
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
        }
        event_data = getattr(record, "event_data", None)
        if isinstance(event_data, dict):
            payload.update(sanitize_log_value(event_data))
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Exception"
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class WebhookAlertHandler(logging.Handler):
    """Optional ERROR/CRITICAL alert sink; disabled when no webhook is configured."""

    def __init__(self, endpoint: str, timeout_seconds: float = 2.0) -> None:
        super().__init__(level=logging.ERROR)
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def emit(self, record: logging.LogRecord) -> None:
        if not self.endpoint:
            return
        try:
            body = self.format(record).encode("utf-8")
            request = urllib_request.Request(
                self.endpoint,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib_request.urlopen(request, timeout=self.timeout_seconds):  # noqa: S310
                pass
        except Exception:
            self.handleError(record)


def classify_outcome(path: str, status_code: int, decision: str | None = None) -> str:
    """Separate policy outcomes from validation and platform failures."""
    if status_code >= 500:
        return "SYSTEM_ERROR"
    if path == "/api/risk/check" and status_code == 422:
        return "VALIDATION_ERROR"
    decision_outcomes = {
        "通过": "BUSINESS_PASS",
        "标记": "RISK_FLAGGED",
        "人工审核": "RISK_REVIEW_REQUIRED",
        "拒绝": "RISK_POLICY_REJECTED",
    }
    if decision in decision_outcomes:
        return decision_outcomes[decision]
    if 400 <= status_code < 500:
        return "CLIENT_ERROR"
    return "SUCCESS"


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) else "UNMATCHED_ROUTE"


def install_observability_middleware(application: FastAPI) -> None:
    access_logger = logging.getLogger("bankrisk.access")
    system_logger = logging.getLogger("bankrisk.system")

    @application.middleware("http")
    async def structured_access_log(request: Request, call_next):
        request_id = new_request_id()
        tokens = set_request_context(request_id)
        request.state.request_id = request_id
        started = perf_counter()
        status_code = 500
        response = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            system_logger.exception(
                "system_request_failed",
                extra={
                    "event_data": {
                        "outcome": "SYSTEM_ERROR",
                        "method": request.method,
                        "route": _route_template(request),
                    }
                },
            )
            raise
        finally:
            scenario = getattr(request.state, "risk_scenario", "-")
            decision = getattr(request.state, "risk_decision", None)
            outcome_override = getattr(request.state, "outcome_override", None)
            set_scenario(scenario)
            duration_ms = round((perf_counter() - started) * 1000, 3)
            access_logger.info(
                "http_request_completed",
                extra={
                    "event_data": {
                        "method": request.method,
                        "route": _route_template(request),
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                        "outcome": outcome_override
                        or classify_outcome(request.url.path, status_code, decision),
                        "decision": decision,
                        "client_ip": request.client.host if request.client else None,
                    }
                },
            )
            reset_request_context(tokens)


def safe_client_request_reference(value: str | None) -> str | None:
    """Validate an upstream request reference before it is included in logs."""
    if value and _SAFE_REQUEST_ID.fullmatch(value):
        return pseudonymize(value)
    return None
