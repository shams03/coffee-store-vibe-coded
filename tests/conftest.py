"""
Pytest fixtures: test client, DB session, mock payment/notification.
Integration tests use Postgres (TEST_DATABASE_URL or default).
"""
import asyncio
import os
import sys
from typing import AsyncGenerator, Generator

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://coffee_user:coffee_pass@localhost:5432/coffee_shop_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_db
from app.main import app


@pytest_asyncio.fixture
async def engine():
    """Create test engine for each test."""
    eng = create_async_engine(TEST_DATABASE_URL, echo=False, pool_pre_ping=True)
    async with eng.begin() as conn:
        # Create tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for each test."""
    # Also update the app's global engine to use the test engine
    import app.db
    old_engine = app.db.engine
    app.db.engine = engine
    app.db.AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False
    )

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False
    )

    async with async_session() as s:
        yield s

    # Restore original engine
    app.db.engine = old_engine


@pytest_asyncio.fixture
async def client(session: AsyncSession):
    # Seed test user if not already exists
    from app.models.user import User, UserRole
    from app.core.security import hash_password
    from sqlalchemy import select

    result = await session.execute(select(User).where(User.email == "customer@example.com"))
    existing_user = result.scalars().first()

    # If user(customer) does not exists create one
    if not existing_user:
        test_user = User(
            email="customer@example.com",
            hashed_password=hash_password("customer123"),
            role=UserRole.CUSTOMER,
        )
        session.add(test_user)
        await session.commit()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    # Creates a fake client
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()

