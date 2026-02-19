#!/usr/bin/env python3
"""
Seed catalog for Trio Coffee Shop (Trio technical challenge spec).
Products: Latte, Espresso, Macchiato, Iced Coffee, Donuts with variations and price changes.
Run after migrations: python -m scripts.seed_catalog (or via docker-compose).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Catalog as per spec: product name -> base_price_cents, list of (variation_name, price_change_cents)
CATALOG = [
    ("Latte", 450, [("Small", 0), ("Medium", 50), ("Large", 100)]),
    ("Espresso", 350, [("Single", 0), ("Double", 100)]),
    ("Macchiato", 400, [("Small", 0), ("Large", 80)]),
    ("Iced Coffee", 400, [("Regular", 0), ("Large", 50)]),
    ("Donuts", 300, [("Glazed", 0), ("Chocolate", 50), ("Sugar", 30)]),
]


async def seed(db_url: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        for name, base_cents, variations in CATALOG:
            r = await session.execute(
                text(
                    "INSERT INTO products (name, base_price_cents) VALUES (:name, :base) RETURNING id"
                ),
                {"name": name, "base": base_cents},
            )
            (product_id,) = r.one()
            for var_name, price_change in variations:
                await session.execute(
                    text(
                        """
                        INSERT INTO product_variations (product_id, name, price_change_cents)
                        VALUES (:pid, :name, :change)
                        """
                    ),
                    {"pid": product_id, "name": var_name, "change": price_change},
                )
        await session.commit()
    await engine.dispose()
    print("Catalog seeded successfully.")


def main() -> None:
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://coffee_user:coffee_pass@localhost:5432/coffee_shop",
    )
    asyncio.run(seed(db_url))


if __name__ == "__main__":
    main()
