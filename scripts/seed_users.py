#!/usr/bin/env python3
"""
Create default customer and manager users for local/dev (Trio challenge).
Passwords are set via env or defaults for dev only.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


async def seed_users(db_url: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    customer_password = os.environ.get("SEED_CUSTOMER_PASSWORD", "customer123")
    manager_password = os.environ.get("SEED_MANAGER_PASSWORD", "manager123")
    engine = create_async_engine(db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        for email, role, raw_password in [
            ("customer@example.com", "customer", customer_password),
            ("manager@example.com", "manager", manager_password),
        ]:
            hashed = pwd_context.hash(raw_password)
            await session.execute(
                text(
                    """
                    INSERT INTO users (email, hashed_password, role)
                    VALUES (:email, :hashed, CAST(:role AS user_role_enum))
                    ON CONFLICT (email) DO UPDATE SET hashed_password = EXCLUDED.hashed_password, role = EXCLUDED.role
                    """
                ),
                {"email": email, "hashed": hashed, "role": role},
            )
        await session.commit()
    await engine.dispose()
    print("Users seeded (customer@example.com, manager@example.com).")


def main() -> None:
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://coffee_user:coffee_pass@localhost:5432/coffee_shop",
    )
    asyncio.run(seed_users(db_url))


if __name__ == "__main__":
    main()
