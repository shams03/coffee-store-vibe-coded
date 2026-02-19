from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class VariationSchema(BaseModel):
    id: UUID
    name: str
    price_change_cents: int


class ProductMenuSchema(BaseModel):
    id: UUID
    name: str
    base_price_cents: int
    variations: list[VariationSchema] = Field(default_factory=list)


class MenuResponse(BaseModel):
    """GET /api/v1/menu — full catalog with variations and price changes."""

    products: list[ProductMenuSchema]
