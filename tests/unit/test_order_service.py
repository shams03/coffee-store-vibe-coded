"""
Unit tests: status transitions, validation, idempotency logic.
"""
import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

from app.models.order import OrderStatus
from app.services.order_service import VALID_TRANSITIONS


def test_valid_transitions():
    assert VALID_TRANSITIONS[OrderStatus.WAITING] == OrderStatus.PREPARATION
    assert VALID_TRANSITIONS[OrderStatus.PREPARATION] == OrderStatus.READY
    assert VALID_TRANSITIONS[OrderStatus.READY] == OrderStatus.DELIVERED
    assert OrderStatus.DELIVERED not in VALID_TRANSITIONS


def test_order_status_next():
    assert OrderStatus.next_allowed(OrderStatus.WAITING) == OrderStatus.PREPARATION
    assert OrderStatus.next_allowed(OrderStatus.PREPARATION) == OrderStatus.READY
    assert OrderStatus.next_allowed(OrderStatus.READY) == OrderStatus.DELIVERED
    assert OrderStatus.next_allowed(OrderStatus.DELIVERED) is None


@pytest.mark.asyncio
async def test_validate_and_compute_total_invalid_variation():
    from app.services.order_service import validate_and_compute_total
    from app.schemas.order import OrderItemCreate

    session = AsyncMock()
    # Repository uses result.scalar_one_or_none() returning None for invalid variation
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    with pytest.raises(ValueError, match="Invalid product_id or variation_id"):
        await validate_and_compute_total(
            session,
            [OrderItemCreate(product_id=uuid4(), variation_id=uuid4(), quantity=1)],
        )
