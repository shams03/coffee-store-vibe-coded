from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class OrderItemCreate(BaseModel):
    product_id: UUID
    variation_id: UUID
    quantity: int = Field(ge=1, le=100)


class OrderCreate(BaseModel):
    """POST /api/v1/orders body."""

    items: list[OrderItemCreate] = Field(min_length=1)
    metadata: dict = Field(default_factory=dict)
    total_cents: Optional[int] = None  # optional client-sent total; if provided must match computed


class OrderItemResponse(BaseModel):
    product_id: UUID
    variation_id: UUID
    quantity: int
    unit_price_cents: int
    line_total_cents: int


class PaymentInfoSchema(BaseModel):
    id: UUID
    amount_cents: int
    response_status_code: Optional[int] = None


class OrderResponse(BaseModel):
    """GET /api/v1/orders/{order_id} response."""

    id: UUID
    customer_id: UUID
    status: str
    total_cents: int
    metadata: dict
    created_at: str
    items: list[OrderItemResponse]
    payment: Optional[PaymentInfoSchema] = None


class OrderStatusUpdate(BaseModel):
    """PATCH /api/v1/orders/{order_id}/status body."""

    status: str
