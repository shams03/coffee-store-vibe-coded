from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order, OrderStatus


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        customer_id: UUID,
        total_cents: int,
        metadata_: dict,
    ) -> Order:
        order = Order(
            customer_id=customer_id,
            total_cents=total_cents,
            metadata_=metadata_ or {},
        )
        self.session.add(order)
        await self.session.flush()
        return order

    async def get_by_id(self, order_id: UUID) -> Order | None:
        r = await self.session.execute(
            select(Order)
            .options(
                selectinload(Order.items),
                selectinload(Order.customer),
                selectinload(Order.payment),
            )
            .where(Order.id == order_id)
        )
        return r.scalar_one_or_none()

    async def get_by_id_for_update(self, order_id: UUID) -> Order | None:
        """Lock row for status update (SELECT FOR UPDATE)."""
        r = await self.session.execute(
            select(Order)
            .options(
                selectinload(Order.items),
                selectinload(Order.customer),
                selectinload(Order.payment),
            )
            .where(Order.id == order_id)
            .with_for_update()
        )
        return r.scalar_one_or_none()

    async def get_orders_for_customer(self, customer_id: UUID) -> list[Order]:
        r = await self.session.execute(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.payment))
            .where(Order.customer_id == customer_id)
            .order_by(Order.created_at.desc())
        )
        return list(r.scalars().all())

    async def update_status(self, order: Order, new_status: OrderStatus) -> None:
        order.status = new_status
