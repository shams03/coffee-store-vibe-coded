"""
Order placement: validate catalog, compute pricing, idempotency, payment, atomic order+payment.
Status transitions: strict flow with row-level lock; notification on change.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderItem, OrderStatus
from app.models.payment import Payment
from app.models.notification import Notification
from app.repositories.order_repo import OrderRepository
from app.repositories.product_repo import ProductRepository
from app.repositories.idempotency_repo import IdempotencyRepository, hash_key
from app.schemas.order import OrderItemCreate
from app.services.payment_client import request_payment
from app.services.notification_client import send_notification

logger = logging.getLogger(__name__)

# Allowed status transitions (Trio spec)
VALID_TRANSITIONS = {
    OrderStatus.WAITING: OrderStatus.PREPARATION,
    OrderStatus.PREPARATION: OrderStatus.READY,
    OrderStatus.READY: OrderStatus.DELIVERED,
}


async def validate_and_compute_total(
    session: AsyncSession,
    items: list[OrderItemCreate],
) -> tuple[int, list[tuple[UUID, UUID, int, int]]]:
    """
    Validate product_id/variation_id against catalog; compute unit_price = base + variation change.
    Returns (total_cents, [(product_id, variation_id, quantity, unit_price_cents), ...]).
    Raises ValueError with message if invalid.
    """
    product_repo = ProductRepository(session)
    result_items: list[tuple[UUID, UUID, int, int]] = []
    total = 0
    for it in items:
        var = await product_repo.get_variation_for_product(it.product_id, it.variation_id)
        if var is None:
            raise ValueError(f"Invalid product_id or variation_id: {it.product_id}, {it.variation_id}")
        product = var.product
        unit_cents = product.base_price_cents + var.price_change_cents
        line = it.quantity * unit_cents
        total += line
        result_items.append((it.product_id, it.variation_id, it.quantity, unit_cents))
    return total, result_items


async def create_order_with_payment(
    session: AsyncSession,
    customer_id: UUID,
    items: list[OrderItemCreate],
    metadata: dict,
    idempotency_key: Optional[str],
) -> tuple[Optional[Order], Optional[Payment], Optional[str], bool]:
    """
    If idempotency_key is set and already used, return (existing_order, existing_payment, None, True).
    Else validate items, compute total, call payment; on success create order+payment atomically.
    Returns (order, payment, error_message, is_replay). If error_message is set, no order created (e.g. 402).
    """
    total_cents, computed = await validate_and_compute_total(session, items)
    idem_repo = IdempotencyRepository(session)
    order_repo = OrderRepository(session)

    if idempotency_key:
        key_hash = hash_key(idempotency_key)
        existing = await idem_repo.find_by_key(key_hash)
        if existing and existing.order_id:
            order = await order_repo.get_by_id(existing.order_id)
            payment = order.payment if order else None
            return order, payment, None, True

    # Call payment first (before creating order)
    status_code, response_body = await request_payment(total_cents)
    if status_code < 200 or status_code >= 300:
        return None, None, f"Payment failed: {status_code} — {response_body}"

    # Atomic: order + items + payment + idempotency
    order = await order_repo.create(customer_id, total_cents, metadata)
    for product_id, variation_id, quantity, unit_cents in computed:
        item = OrderItem(
            order_id=order.id,
            product_id=product_id,
            variation_id=variation_id,
            quantity=quantity,
            unit_price_cents=unit_cents,
        )
        session.add(item)
    payment = Payment(
        order_id=order.id,
        amount_cents=total_cents,
        request_payload={"value": total_cents},
        response_status_code=status_code,
        response_payload=response_body,
    )
    session.add(payment)

    if idempotency_key:
        key_hash = hash_key(idempotency_key)
        existing = await idem_repo.find_by_key(key_hash)
        if existing:
            await idem_repo.link_order_and_payment(existing, order.id, payment.id)
        else:
            key_row = await idem_repo.create_key(key_hash, idempotency_key)
            await idem_repo.link_order_and_payment(key_row, order.id, payment.id)

    await session.flush()
    return order, payment, None, False


async def update_order_status_and_notify(
    session: AsyncSession,
    order_id: UUID,
    new_status_str: str,
) -> tuple[Optional[Order], Optional[str]]:
    """
    Validate new_status is next in flow; lock order row; update; send notification; store notification.
    Returns (order, error_message). On invalid transition returns (None, "message").
    """
    try:
        new_status = OrderStatus(new_status_str)
    except ValueError:
        return None, f"Invalid status: {new_status_str}. Allowed: waiting, preparation, ready, delivered."

    order_repo = OrderRepository(session)
    order = await order_repo.get_by_id_for_update(order_id)
    if order is None:
        return None, "Order not found"
    allowed = VALID_TRANSITIONS.get(order.status)
    if allowed != new_status:
        return None, (
            f"Invalid transition: current status is {order.status.value}, "
            f"only next allowed is {allowed.value if allowed else 'none'}."
        )

    order_repo.update_status(order, new_status)
    await session.flush()

    # Notification: fire-and-forget style; store result; don't fail the request
    status_code, response_body = await send_notification(new_status.value)
    notif = Notification(
        order_id=order.id,
        status=new_status.value,
        response_status_code=status_code,
        response_payload=response_body,
    )
    session.add(notif)
    await session.flush()
    return order, None
