"""
Payment integration: POST to Trio challenge payment URL.
Create order only if payment returns success; log full response (redacted in app logs).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


async def request_payment(total_cents: int) -> tuple[int, dict[str, Any]]:
    """
    POST to payment service with {"value": total_cents}.
    Returns (status_code, response_body).
    """
    settings = get_settings()
    url = settings.payment_service_url
    payload = {"value": total_cents}
    try:
        async with httpx.AsyncClient(timeout=settings.payment_request_timeout) as client:
            resp = await client.post(url, json=payload)
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            logger.info(
                "payment_response",
                extra={
                    "payment_response": {"status_code": resp.status_code, "body": body},
                    "request_value_cents": total_cents,
                },
            )
            print(f"Payment response: status_code={resp.status_code}, body={body}")
            return resp.status_code, body
    except Exception as e:
        logger.exception("payment_request_failed", extra={"error": str(e), "url": url})
        return 500, {"error": str(e)}
