"""
Integration tests for orders API: POST /orders, GET /orders/{id}, PATCH /orders/{id}/status.
Tests with real database, mocked payment/notification with respx.
Requires Postgres (TEST_DATABASE_URL) and migrated DB, or uses conftest engine.
"""
import pytest
import respx
from uuid import uuid4
from unittest.mock import MagicMock
from httpx import Response as HttpxResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus
from app.models.product import Product, ProductVariation
from app.models.user import User, UserRole
from app.core.security import hash_password

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def customer_user(session: AsyncSession) -> User:
    """Create or retrieve test customer user."""
    from sqlalchemy import select
    
    # Check if user already exists
    result = await session.execute(
        select(User).where(User.email == "test_customer@example.com")
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        user = User(
            email="test_customer@example.com",
            hashed_password=hash_password("password123"),
            role=UserRole.CUSTOMER,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    
    return user


@pytest.fixture
async def manager_user(session: AsyncSession) -> User:
    """Create or retrieve test manager user."""
    from sqlalchemy import select
    
    # Check if user already exists
    result = await session.execute(
        select(User).where(User.email == "test_manager@example.com")
    )
    user = result.scalar_one_or_none()
    
    if user is None:
        user = User(
            email="test_manager@example.com",
            hashed_password=hash_password("password123"),
            role=UserRole.MANAGER,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    
    return user


@pytest.fixture
async def customer_token(customer_user: User) -> str:
    """Generate JWT token for customer user."""
    from app.core.auth import create_access_token
    return create_access_token(customer_user.id, UserRole.CUSTOMER)


@pytest.fixture
async def manager_token(manager_user: User) -> str:
    """Generate JWT token for manager user."""
    from app.core.auth import create_access_token
    return create_access_token(manager_user.id, UserRole.MANAGER)


@pytest.fixture
async def test_product(session: AsyncSession) -> Product:
    """Create a test product."""
    product = Product(
        name="Espresso",
        base_price_cents=300,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


@pytest.fixture
async def test_variation(session: AsyncSession, test_product: Product) -> ProductVariation:
    """Create a test product variation."""
    variation = ProductVariation(
        product_id=test_product.id,
        name="Double Shot",
        price_change_cents=100,
    )
    session.add(variation)
    await session.commit()
    await session.refresh(variation)
    return variation


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
    # Use seeded user from conftest (customer@example.com / customer123)
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


# POST /api/v1/orders - Place order tests

@respx.mock
async def test_place_order_success(
        client,
        customer_token: str,
        customer_user: User,
        test_product: Product,
        test_variation: ProductVariation,
    ):
        """POST /orders - customer successfully places order."""
        respx.post("https://challenge.trio.dev/api/v1/payment").mock(
            return_value=HttpxResponse(200, json={"transactionId": "tx123"})
        )

        body = {
            "items": [
                {
                    "product_id": str(test_product.id),
                    "variation_id": str(test_variation.id),
                    "quantity": 2,
                }
            ],
            "total_cents": 800,
            "metadata": {"notes": "extra hot"},
        }

        response = await client.post(
            "/api/v1/orders",
            json=body,
            headers={"Authorization": f"Bearer {customer_token}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "waiting"
        assert data["total_cents"] == 800
        assert data["customer_id"] == str(customer_user.id)
        assert len(data["items"]) == 1
        assert data["metadata"]["notes"] == "extra hot"
        assert "id" in data


@respx.mock
async def test_place_order_total_mismatch(
    client,
    customer_token: str,
    test_product: Product,
    test_variation: ProductVariation,
    ):
        """POST /orders - reject if computed total ≠ provided total."""
        body = {
            "items": [
                {
                    "product_id": str(test_product.id),
                    "variation_id": str(test_variation.id),
                    "quantity": 1,
                }
            ],
            "total_cents": 5000,  # Wrong: should be 400 (300 + 100)
            "metadata": {},
        }

        response = await client.post(
            "/api/v1/orders",
            json=body,
            headers={"Authorization": f"Bearer {customer_token}"},
        )

        assert response.status_code == 409
        assert "Total mismatch" in response.json()["detail"]


@respx.mock
async def test_place_order_payment_failure(
    client,
    customer_token: str,
    test_product: Product,
    test_variation: ProductVariation,
    ):
        """POST /orders - return 402 if payment service fails."""
        respx.post("https://challenge.trio.dev/api/v1/payment").mock(
            return_value=HttpxResponse(402, json={"error": "insufficient funds"})
        )

        body = {
            "items": [
                {
                    "product_id": str(test_product.id),
                    "variation_id": str(test_variation.id),
                    "quantity": 1,
                }
            ],
            "total_cents": 400,
            "metadata": {},
        }

        response = await client.post(
            "/api/v1/orders",
            json=body,
            headers={"Authorization": f"Bearer {customer_token}"},
        )

        assert response.status_code == 402
        assert "Payment failed" in response.json()["detail"]


@respx.mock
async def test_place_order_invalid_product(
        client,
        customer_token: str,
    ):
        """POST /orders - reject invalid product_id."""
        body = {
            "items": [
                {
                    "product_id": str(uuid4()),  # Non-existent product
                    "variation_id": str(uuid4()),
                    "quantity": 1,
                }
            ],
            "total_cents": 400,
            "metadata": {},
        }

        response = await client.post(
            "/api/v1/orders",
            json=body,
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert response.status_code == 400


# GET /api/v1/orders/{id} - Get order tests


@respx.mock
async def test_get_order_customer_own_order(
    client,
    customer_token: str,
    customer_user: User,
    session: AsyncSession,
    ):
        """GET /orders/{id} - customer retrieves own order."""
        respx.post("https://challenge.trio.dev/api/v1/payment").mock(
            return_value=HttpxResponse(200, json={"transactionId": "tx125"})
        )

        # Create order
        order = Order(
            customer_id=customer_user.id,
            status=OrderStatus.WAITING,
            total_cents=400,
            metadata_={"notes": "test"},
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        response = await client.get(
            f"/api/v1/orders/{order.id}",
            headers={"Authorization": f"Bearer {customer_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(order.id)
        assert data["customer_id"] == str(customer_user.id)
        assert data["status"] == "waiting"
        assert data["total_cents"] == 400


@respx.mock
async def test_get_order_customer_other_order_forbidden(
        client,
        customer_token: str,
        customer_user: User,
        session: AsyncSession,
    ):
        """GET /orders/{id} - customer cannot access other customer's order."""
        from sqlalchemy import select

        # Create order for different customer with unique email
        other_email = f"other_customer_{uuid4()}@test.com"
        other_customer = User(
            email=other_email,
            hashed_password=hash_password("password"),
            role=UserRole.CUSTOMER,
        )
        session.add(other_customer)
        await session.commit()

        order = Order(
            customer_id=other_customer.id,
            status=OrderStatus.WAITING,
            total_cents=400,
            metadata_={},
        )
        session.add(order)
        await session.commit()

        response = await client.get(
            f"/api/v1/orders/{order.id}",
            headers={"Authorization": f"Bearer {customer_token}"},
        )

        assert response.status_code == 404
        assert "Order not found" in response.json()["detail"]


@respx.mock
async def test_get_order_manager_any_order(
        client,
        manager_token: str,
        customer_user: User,
        session: AsyncSession,
    ):
        """GET /orders/{id} - manager can retrieve any order."""
        order = Order(
            customer_id=customer_user.id,
            status=OrderStatus.WAITING,
            total_cents=400,
            metadata_={},
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        response = await client.get(
            f"/api/v1/orders/{order.id}",
            headers={"Authorization": f"Bearer {manager_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(order.id)


@respx.mock
async def test_get_order_not_found(
        client,
        customer_token: str,
    ):
        """GET /orders/{id} - return 404 if order doesn't exist."""
        fake_order_id = uuid4()

        response = await client.get(
            f"/api/v1/orders/{fake_order_id}",
            headers={"Authorization": f"Bearer {customer_token}"},
        )

        assert response.status_code == 404
        assert "Order not found" in response.json()["detail"]


# PATCH /api/v1/orders/{id}/status - Update status tests


@respx.mock
async def test_update_status_waiting_to_preparation(
        client,
        manager_token: str,
        customer_user: User,
        session: AsyncSession,
    ):
        """PATCH /orders/{id}/status - transition waiting→preparation."""
        respx.post("https://challenge.trio.dev/api/v1/notification").mock(
            return_value=HttpxResponse(200, json={"status": "sent"})
        )

        order = Order(
            customer_id=customer_user.id,
            status=OrderStatus.WAITING,
            total_cents=400,
            metadata_={},
        )
        session.add(order)
        await session.commit()

        body = {"status": OrderStatus.PREPARATION.value}

        response = await client.patch(
            f"/api/v1/orders/{order.id}/status",
            json=body,
            headers={"Authorization": f"Bearer {manager_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "preparation"


@respx.mock
async def test_update_status_invalid_transition(
    client,
    manager_token: str,
    customer_user: User,
    session: AsyncSession,
    ):
        """PATCH /orders/{id}/status - reject invalid transition."""
        order = Order(
            customer_id=customer_user.id,
            status=OrderStatus.WAITING,
            total_cents=400,
            metadata_={},
        )
        session.add(order)
        await session.commit()

        body = {"status": OrderStatus.READY.value}

        response = await client.patch(
            f"/api/v1/orders/{order.id}/status",
            json=body,
            headers={"Authorization": f"Bearer {manager_token}"},
        )

        assert response.status_code == 400
        assert "Invalid transition" in response.json()["detail"]


@respx.mock
async def test_update_status_unauthorized(
    client,
    customer_user: User,
    session: AsyncSession,
    ):
        """reject if not authenticated."""
        order = Order(
            customer_id=customer_user.id,
            status=OrderStatus.WAITING,
            total_cents=400,
            metadata_={},
        )
        session.add(order)
        await session.commit()

        body = {"status": OrderStatus.PREPARATION.value}

        response = await client.patch(
            f"/api/v1/orders/{order.id}/status",
            json=body,
        )

        assert response.status_code == 401


# MANAGER ENDPOINTS - Product Management Tests


@respx.mock
async def test_create_product_success(
        client,
        manager_token: str,
    ):
        """POST /admin/products - manager creates new product with variations."""
        body = {
            "name": "Cappuccino",
            "base_price_cents": 450,
            "variations": [
                {"name": "Small", "price_change_cents": -50},
                {"name": "Large", "price_change_cents": 100},
            ],
        }

        response = await client.post(
            "/api/v1/admin/products",
            json=body,
            headers={"Authorization": f"Bearer {manager_token}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Cappuccino"
        assert data["base_price_cents"] == 450
        assert len(data["variations"]) == 2
        assert data["variations"][0]["name"] == "Small"
        assert data["variations"][1]["name"] == "Large"

@respx.mock
async def test_create_product_customer_forbidden(
    client,
    customer_token: str,
    ):
        """POST /admin/products - reject if user is customer (manager only)."""
        body = {
            "name": "Latte",
            "base_price_cents": 500,
            "variations": [],
        }

        response = await client.post(
            "/api/v1/admin/products",
            json=body,
            headers={"Authorization": f"Bearer {customer_token}"},
        )

        assert response.status_code == 403


@respx.mock
async def test_update_product_name(
    client,
    manager_token: str,
    test_product: Product,
    ):
        """PATCH /admin/products/{id} - update product name."""
        body = {"name": "Updated Espresso"}

        response = await client.patch(
            f"/api/v1/admin/products/{test_product.id}",
            json=body,
            headers={"Authorization": f"Bearer {manager_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Espresso"
        assert data["base_price_cents"] == test_product.base_price_cents

@respx.mock
async def test_delete_product_success(
    client,
    manager_token: str,
    test_product: Product,
    ):
        """manager deletes product."""
        response = await client.delete(
            f"/api/v1/admin/products/{test_product.id}",
            headers={"Authorization": f"Bearer {manager_token}"},
        )

        assert response.status_code == 204

