"""
Trio Coffee Shop Order Management API.
FastAPI async backend; JWT auth with role (customer/manager); payment & notification integration.
"""
from __future__ import annotations

import time
import uuid as uuid_lib

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest
from starlette.responses import Response

from app.api import auth, menu, orders, admin
from app.config import get_settings
from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)
settings = get_settings()

# Sentry (configurable via SENTRY_DSN)
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=0.1,
        integrations=[FastApiIntegration()],
    )

app = FastAPI(
    title="Coffee Shop Order API",
    description="Trio technical challenge: order management with payment and notification integration.",
    version="1.0.0",
    openapi_tags=[
        {"name": "menu", "description": "Catalog / menu"},
        {"name": "auth", "description": "JWT login"},
        {"name": "orders", "description": "Place and manage orders"},
        {"name": "admin", "description": "Product management (manager only)"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics
REQUEST_COUNT = Counter("http_requests_total", "Total requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["method", "path"])


@app.middleware("http")
async def request_id_and_metrics(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid_lib.uuid4())
    request_id_ctx.set(request_id)
    start = time.perf_counter()
    path = request.scope.get("path", "")
    method = request.scope.get("method", "")
    response = await call_next(request)
    duration = time.perf_counter() - start
    REQUEST_COUNT.labels(method=method, path=path, status=response.status_code).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(duration)
    response.headers["X-Request-ID"] = request_id
    return response


prefix = settings.api_prefix
app.include_router(menu.router, prefix=prefix)
app.include_router(auth.router, prefix=prefix)
app.include_router(orders.router, prefix=prefix)
app.include_router(admin.router, prefix=prefix)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")


@app.get("/")
async def root():
    return {"message": "Coffee Shop Order API", "docs": "/docs"}
