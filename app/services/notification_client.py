"""
Notification integration: on order status change, POST to Trio notification URL.
Log and store response; failure does not revert order (retry/log).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def send_notification(status: str) -> tuple[int, dict[str, Any]]:
    """
    POST to notification service with {"status": status}.
    Returns (status_code, response_body).
    """
    settings = get_settings()
    url = settings.notification_service_url
    payload = {"status": status}
    try:
        async with httpx.AsyncClient(timeout=settings.notification_request_timeout) as client:
            resp = await client.post(url, json=payload)
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            logger.info(
                "notification_response",
                extra={"notification_response": {"status_code": resp.status_code, "body": body}, "status": status},
            )
            print(f"Notification response: status_code={resp.status_code}, body={body}")
            return resp.status_code, body
    except Exception as e:
        logger.exception("notification_request_failed", extra={"error": str(e), "url": url})
        return 500, {"error": str(e)}
