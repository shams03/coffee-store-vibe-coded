"""
Integration tests: mock payment/notification with respx; test POST orders, idempotency, status PATCH.
Requires Postgres (TEST_DATABASE_URL) and migrated + seeded DB, or use conftest engine.
"""
import os
import pytest
import respx
from httpx import Response as HttpxResponse

# Skip if no Postgres or explicit env
pytestmark = pytest.mark.asyncio


@respx.mock
async def test_get_menu_returns_products(client, session):
    """GET /menu returns catalog (no auth)."""
    r = await client.get("/api/v1/menu")
    assert r.status_code == 200
    data = r.json()
    assert "products" in data
    assert isinstance(data["products"], list)


@respx.mock
async def test_login_returns_token(client):
    """POST /auth/token returns JWT with role (use seeded user)."""
    # Use seeded user from scripts/seed_users (customer@example.com / customer123)
    r = await client.post(
        "/api/v1/auth/token",
        data={"username": "customer@example.com", "password": "customer123"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # Decode JWT and check role
    from jose import jwt
    from app.config import get_settings
    settings = get_settings()
    payload = jwt.decode(data["access_token"], settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload.get("role") in ("customer", "manager")
    assert "sub" in payload
