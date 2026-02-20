"""
Unit tests: basic service functionality.
"""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from app.models.order import OrderStatus
from app.services.order_service import VALID_TRANSITIONS


def test_valid_transitions():
    """Tests for allowed transitions."""
    assert VALID_TRANSITIONS[OrderStatus.WAITING] == OrderStatus.PREPARATION
    assert VALID_TRANSITIONS[OrderStatus.PREPARATION] == OrderStatus.READY
    assert VALID_TRANSITIONS[OrderStatus.READY] == OrderStatus.DELIVERED
    assert OrderStatus.DELIVERED not in VALID_TRANSITIONS


@pytest.mark.asyncio
async def test_validate_and_compute_total_success():
    """Test successful validation and price computation."""
    from app.services.order_service import validate_and_compute_total
    from app.schemas.order import OrderItemCreate
    from app.models.product import Product, ProductVariation

    product_id = uuid4()
    variation_id = uuid4()

    product = MagicMock(spec=Product)
    product.base_price_cents = 300
    product.id = product_id

    variation = MagicMock(spec=ProductVariation)
    variation.price_change_cents = 100
    variation.product = product
    variation.id = variation_id

    session = AsyncMock()
    with AsyncMock() as mock_repo:
        mock_repo.get_variation_for_product = AsyncMock(return_value=variation)
        from unittest.mock import patch
        with patch("app.services.order_service.ProductRepository") as MockRepo:
            MockRepo.return_value = mock_repo
            total, items = await validate_and_compute_total(
                session,
                [OrderItemCreate(product_id=product_id, variation_id=variation_id, quantity=2)],
            )

    assert total == 800
    assert len(items) == 1


@pytest.mark.asyncio
async def test_create_order_with_payment_success():
    """Test successful order creation with payment."""
    from app.services.order_service import create_order_with_payment
    from app.schemas.order import OrderItemCreate
    from app.models.product import Product, ProductVariation
    from unittest.mock import patch

    customer_id = uuid4()
    product_id = uuid4()
    variation_id = uuid4()
    order_id = uuid4()

    product = MagicMock(spec=Product)
    product.base_price_cents = 300
    product.id = product_id

    variation = MagicMock(spec=ProductVariation)
    variation.price_change_cents = 100
    variation.product = product
    variation.id = variation_id

    session = AsyncMock()
    mock_order = MagicMock()
    mock_order.id = order_id

    with patch("app.services.order_service.ProductRepository") as MockProdRepo:
        mock_prod_repo = MagicMock()
        mock_prod_repo.get_variation_for_product = AsyncMock(return_value=variation)
        MockProdRepo.return_value = mock_prod_repo

        with patch("app.services.order_service.OrderRepository") as MockOrderRepo:
            mock_order_repo = MagicMock()
            mock_order_repo.create = AsyncMock(return_value=mock_order)
            MockOrderRepo.return_value = mock_order_repo

            with patch("app.services.order_service.IdempotencyRepository") as MockIdemRepo:
                mock_idem_repo = MagicMock()
                mock_idem_repo.find_by_key = AsyncMock(return_value=None)
                MockIdemRepo.return_value = mock_idem_repo

                with patch("app.services.order_service.request_payment") as mock_payment:
                    mock_payment.return_value = (200, {"transactionId": "tx123"})
                    order, payment, error, is_replay = await create_order_with_payment(
                        session,
                        customer_id,
                        [OrderItemCreate(product_id=product_id, variation_id=variation_id, quantity=1)],
                        {"notes": "test"},
                        None,
                    )

    assert order is not None
    assert payment is not None
    assert error is None


@pytest.mark.asyncio
async def test_update_order_status_all_valid_transitions():
    """Test all valid status transitions."""
    from app.services.order_service import update_order_status_and_notify
    from unittest.mock import patch

    transitions = [
        (OrderStatus.WAITING, OrderStatus.PREPARATION),
        (OrderStatus.PREPARATION, OrderStatus.READY),
        (OrderStatus.READY, OrderStatus.DELIVERED),
    ]

    for current_status, next_status in transitions:
        order_id = uuid4()
        mock_order = MagicMock()
        mock_order.id = order_id
        mock_order.status = current_status
        session = AsyncMock()

        with patch("app.services.order_service.OrderRepository") as MockOrderRepo:
            mock_order_repo = MagicMock()
            mock_order_repo.get_by_id_for_update = AsyncMock(return_value=mock_order)
            mock_order_repo.update_status = AsyncMock()
            MockOrderRepo.return_value = mock_order_repo

            with patch("app.services.order_service.send_notification") as mock_notify:
                mock_notify.return_value = (200, {})
                order, error = await update_order_status_and_notify(
                    session, order_id, next_status.value
                )

        assert order is not None
        assert error is None
