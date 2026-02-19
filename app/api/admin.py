"""
Optional admin: create/update/delete products and variations (manager only).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_role
from app.db import get_db
from app.models.user import User, UserRole
from app.models.product import Product, ProductVariation
from app.schemas.menu import ProductMenuSchema, VariationSchema
from pydantic import BaseModel, Field

router = APIRouter(prefix="/admin", tags=["admin"])


class VariationCreate(BaseModel):
    name: str
    price_change_cents: int = 0


class ProductCreate(BaseModel):
    name: str
    base_price_cents: int = Field(ge=0)
    variations: list[VariationCreate] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    base_price_cents: Optional[int] = Field(None, ge=0)


@router.post("/products", response_model=ProductMenuSchema, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate,
    current_user: User = require_role(UserRole.MANAGER),
    session: AsyncSession = Depends(get_db),
) -> ProductMenuSchema:
    product = Product(name=body.name, base_price_cents=body.base_price_cents)
    session.add(product)
    await session.flush()
    for v in body.variations:
        var = ProductVariation(
            product_id=product.id,
            name=v.name,
            price_change_cents=v.price_change_cents,
        )
        session.add(var)
    await session.flush()
    await session.refresh(product)
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    r = await session.execute(
        select(Product).options(selectinload(Product.variations)).where(Product.id == product.id)
    )
    product = r.scalar_one()
    return ProductMenuSchema(
        id=product.id,
        name=product.name,
        base_price_cents=product.base_price_cents,
        variations=[VariationSchema(id=v.id, name=v.name, price_change_cents=v.price_change_cents) for v in product.variations],
    )


@router.patch("/products/{product_id}", response_model=ProductMenuSchema)
async def update_product(
    product_id: UUID,
    body: ProductUpdate,
    current_user: User = require_role(UserRole.MANAGER),
    session: AsyncSession = Depends(get_db),
) -> ProductMenuSchema:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    r = await session.execute(
        select(Product).options(selectinload(Product.variations)).where(Product.id == product_id)
    )
    product = r.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if body.name is not None:
        product.name = body.name
    if body.base_price_cents is not None:
        product.base_price_cents = body.base_price_cents
    await session.flush()
    await session.refresh(product)
    r = await session.execute(
        select(Product).options(selectinload(Product.variations)).where(Product.id == product_id)
    )
    product = r.scalar_one()
    return ProductMenuSchema(
        id=product.id,
        name=product.name,
        base_price_cents=product.base_price_cents,
        variations=[VariationSchema(id=v.id, name=v.name, price_change_cents=v.price_change_cents) for v in product.variations],
    )


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    current_user: User = require_role(UserRole.MANAGER),
    session: AsyncSession = Depends(get_db),
) -> None:
    from sqlalchemy import select
    r = await session.execute(select(Product).where(Product.id == product_id))
    product = r.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    await session.delete(product)
    await session.flush()
