from __future__ import annotations

import hashlib
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import IdempotencyKey


# Idempotency key TTL (e.g. 24h); duplicate requests after this return same result
IDEMPOTENCY_TTL_HOURS = 24


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_key(self, key_hash: str) -> IdempotencyKey | None:
        r = await self.session.execute(
            select(IdempotencyKey).where(IdempotencyKey.key_hash == key_hash)
        )
        return r.scalar_one_or_none()

    async def create_key(
        self,
        key_hash: str,
        key_preview: str | None,
    ) -> IdempotencyKey:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=IDEMPOTENCY_TTL_HOURS)
        row = IdempotencyKey(
            key_hash=key_hash,
            key_preview=key_preview[:32] if key_preview else None,
            expires_at=expires_at,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def link_order_and_payment(
        self,
        key_row: IdempotencyKey,
        order_id: UUID,
        payment_id: UUID,
    ) -> None:
        key_row.order_id = order_id
        key_row.payment_id = payment_id
