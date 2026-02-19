from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.product import Product, ProductVariation


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_products_with_variations(self) -> list[Product]:
        r = await self.session.execute(
            select(Product).options(selectinload(Product.variations)).order_by(Product.name)
        )
        return list(r.scalars().all())

    async def get_product_by_id(self, product_id: UUID) -> Product | None:
        r = await self.session.execute(
            select(Product).options(selectinload(Product.variations)).where(Product.id == product_id)
        )
        return r.scalar_one_or_none()

    async def get_variation_by_id(self, variation_id: UUID) -> ProductVariation | None:
        r = await self.session.execute(
            select(ProductVariation).where(ProductVariation.id == variation_id)
        )
        return r.scalar_one_or_none()

    async def get_variation_for_product(
        self, product_id: UUID, variation_id: UUID
    ) -> ProductVariation | None:
        r = await self.session.execute(
            select(ProductVariation)
            .options(selectinload(ProductVariation.product))
            .where(
                ProductVariation.id == variation_id,
                ProductVariation.product_id == product_id,
            )
        )
        return r.scalar_one_or_none()
