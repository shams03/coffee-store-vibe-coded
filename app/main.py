"""
Coffee Shop Order Management API - Main Application Entry Point.

This is the core FastAPI application that handles all HTTP requests for the coffee shop ordering system.
It provides JWT-based authentication with role-based access control (customer/manager), integrates with
external payment processing and notification services, and manages the complete order lifecycle.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, menu, orders, admin
from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="Coffee Shop Order Management Application",
    description="Trio technical challenge: order management with payment and notification integration.",
    version="1.0.0",
    openapi_tags=[
        {"name": "menu", "description": "Catalog"},
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


prefix = settings.api_prefix
app.include_router(menu.router, prefix=prefix)
app.include_router(auth.router, prefix=prefix)
app.include_router(orders.router, prefix=prefix)
app.include_router(admin.router, prefix=prefix)


@app.get("/")
async def root():
    return {"message": "Coffee Shop Order API", "docs": "/docs"}
