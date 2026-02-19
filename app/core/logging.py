"""
Structured JSON logging with request_id, user_id, order_id when applicable.
Redact secrets in payment/notification response logs.
"""
from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any, Optional
from uuid import UUID

request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def _redact(obj: Any) -> Any:
    """Redact keys that might contain secrets (e.g. payment response)."""
    if isinstance(obj, dict):
        return {k: "***" if k.lower() in ("authorization", "token", "secret", "key") else _redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(record.created)),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if request_id_ctx.get():
            log["request_id"] = request_id_ctx.get()
        if getattr(record, "user_id", None):
            log["user_id"] = str(record.user_id)
        if getattr(record, "order_id", None):
            log["order_id"] = str(record.order_id)
        if getattr(record, "payment_response", None):
            log["payment_response"] = _redact(record.payment_response)
        if getattr(record, "notification_response", None):
            log["notification_response"] = _redact(record.notification_response)
        return json.dumps(log)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
