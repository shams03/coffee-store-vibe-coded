"""
Orders API - catalog validation, payment processing, order persistence, and status management.
Idempotency-Key header on POST; strict status transitions; 402 on payment failure.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_role
from app.db import get_db
from app.models.user import User, UserRole
from app.models.order import Order
from app.schemas.order import OrderCreate, OrderResponse, OrderItemResponse, OrderStatusUpdate, PaymentInfoSchema
from app.services.order_service import create_order_with_payment, update_order_status_and_notify

router = APIRouter(prefix="/orders", tags=["orders"])

# Key Decisions
# Idempotency via header to prevent duplicate charges on retries
# Strict state machine for order status transitions
# Payment is called before order creation — no order record exists if payment fails


async def _order_to_response(order: Order, session: AsyncSession = None) -> OrderResponse:
    items = []
    if session is not None:
        from app.repositories.product_repo import ProductRepository
        product_repo = ProductRepository(session)
        import asyncio
        async def enrich_item(it):
            product = await product_repo.get_product_by_id(it.product_id)
            variation = await product_repo.get_variation_by_id(it.variation_id)
            return OrderItemResponse(
                product_id=it.product_id,
                variation_id=it.variation_id,
                quantity=it.quantity,
                unit_price_cents=it.unit_price_cents,
                line_total_cents=it.quantity * it.unit_price_cents,
                product_name=product.name if product else None,
                variation_name=variation.name if variation else None,
                variation_price_change_cents=variation.price_change_cents if variation else None,
                product_base_price_cents=product.base_price_cents if product else None,
            )
        items = await asyncio.gather(*[enrich_item(it) for it in order.items])
    else:
        items = [
            OrderItemResponse(
                product_id=it.product_id,
                variation_id=it.variation_id,
                quantity=it.quantity,
                unit_price_cents=it.unit_price_cents,
                line_total_cents=it.quantity * it.unit_price_cents,
            )
            for it in order.items
        ]
    payment_schema = None
    if order.payment:
        payment_schema = PaymentInfoSchema(
            id=order.payment.id,
            amount_cents=order.payment.amount_cents,
            response_status_code=order.payment.response_status_code,
        )
    return OrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status.value,
        total_cents=order.total_cents,
        metadata=order.metadata_,
        created_at=order.created_at.isoformat(),
        items=items,
        payment=payment_schema,
    )


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Place order (customer)",
    description="Validates items against catalog, computes total, calls payment, creates order only on payment success. Use Idempotency-Key to prevent duplicate charges.",
    responses={
        201: {"description": "Order created"},
        402: {"description": "Payment required / failed"},
        409: {"description": "Validation error (e.g. total mismatch)"},
    },
)
async def place_order(
    body: OrderCreate,
    current_user: User = require_role(UserRole.CUSTOMER),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_db),
) -> OrderResponse:
    from app.repositories.order_repo import OrderRepository
    from app.services.order_service import validate_and_compute_total

    try:
        total_computed, _ = await validate_and_compute_total(session, body.items)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if body.total_cents is not None and body.total_cents != total_computed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Total mismatch: computed {total_computed}, received {body.total_cents}",
        )
    order, payment, err, is_replay = await create_order_with_payment(
        session, current_user.id, body.items, body.metadata, idempotency_key
    )
    if err is not None:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=err)
    if order is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Payment succeeded but order not created")
    repo = OrderRepository(session)
    order = await repo.get_by_id(order.id)
    response = await _order_to_response(order, session)
    if is_replay:
        return JSONResponse(content=response.model_dump(mode="json"), status_code=200)
    return response


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="Get order by ID",
    description="Customer: own orders only. Manager: any order.",
)
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> OrderResponse:
    from app.repositories.order_repo import OrderRepository
    repo = OrderRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if current_user.role == UserRole.CUSTOMER and order.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return await _order_to_response(order, session)


@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse,
    summary="Update order status (manager only)",
    description="Strict transition: waiting-preparation-ready-delivered. Invalid transition returns 400. Triggers notification.",
    responses={400: {"description": "Invalid status transition"}},
)
async def update_status(
    order_id: UUID,
    body: OrderStatusUpdate,
    session: AsyncSession = Depends(get_db),
) -> OrderResponse:
    from app.repositories.order_repo import OrderRepository
    order, err = await update_order_status_and_notify(session, order_id, body.status)
    if err is not None:
        if "not found" in err.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    repo = OrderRepository(session)
    order = await repo.get_by_id(order.id)
    return await _order_to_response(order, session)
