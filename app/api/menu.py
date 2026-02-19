"""
GET /api/v1/menu — full catalog with products, variations, price changes.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.repositories.product_repo import ProductRepository
from app.schemas.menu import MenuResponse, ProductMenuSchema, VariationSchema

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get(
    "",
    response_model=MenuResponse,
    summary="Get full menu",
    description="Returns all products with base_price and variations (id, name, price_change_cents).",
)
async def get_menu(session: AsyncSession = Depends(get_db)) -> MenuResponse:
    repo = ProductRepository(session)
    products = await repo.get_all_products_with_variations()
    return MenuResponse(
        products=[
            ProductMenuSchema(
                id=p.id,
                name=p.name,
                base_price_cents=p.base_price_cents,
                variations=[
                    VariationSchema(
                        id=v.id,
                        name=v.name,
                        price_change_cents=v.price_change_cents,
                    )
                    for v in p.variations
                ],
            )
            for p in products
        ]
    )
