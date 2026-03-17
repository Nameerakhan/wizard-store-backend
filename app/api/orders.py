"""
Guest order API — no authentication required.
"""

import logging
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.database.models import Order, OrderItem
from app.services.email import send_order_confirmation

logger = logging.getLogger("wizard_store.orders")

router = APIRouter(prefix="/orders", tags=["Orders"])


# ── Request models ────────────────────────────────────────────────────────────

class ShippingAddress(BaseModel):
    full_name: str = Field(..., max_length=255)
    line1: str = Field(..., max_length=255)
    line2: Optional[str] = Field(None, max_length=255)
    city: str = Field(..., max_length=100)
    state: str = Field(..., max_length=100)
    postal_code: str = Field(..., max_length=20)
    country: str = Field("United States", max_length=100)


class OrderItemIn(BaseModel):
    product_name: str = Field(..., max_length=255)
    product_price: float = Field(..., gt=0)
    quantity: int = Field(..., ge=1, le=100)


class GuestOrderRequest(BaseModel):
    customer_name: str = Field(..., max_length=255)
    customer_email: EmailStr
    shipping_address: ShippingAddress
    items: List[OrderItemIn] = Field(..., min_length=1)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/guest")
async def create_guest_order(
    body: GuestOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a guest order — no auth required. Prices trusted from client."""
    subtotal = Decimal(str(sum(i.product_price * i.quantity for i in body.items))).quantize(Decimal("0.01"))
    shipping_cost = Decimal("0.00") if subtotal >= Decimal("75.00") else Decimal("9.99")
    total = subtotal + shipping_cost

    order = Order(
        user_id=None,
        status="pending",
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        total=total,
        shipping_address_snapshot=body.shipping_address.model_dump(),
        customer_email=body.customer_email,
    )
    db.add(order)
    await db.flush()  # get order.id before inserting items

    for item in body.items:
        db.add(OrderItem(
            order_id=order.id,
            product_id=None,
            product_name=item.product_name,
            product_price=Decimal(str(item.product_price)).quantize(Decimal("0.01")),
            quantity=item.quantity,
            line_total=(Decimal(str(item.product_price)) * item.quantity).quantize(Decimal("0.01")),
        ))

    await db.commit()
    await db.refresh(order)

    logger.info("Guest order created | id=%s email=%s total=%s", order.id, body.customer_email, total)

    # Send confirmation email (non-blocking — skips gracefully if no API key)
    import asyncio
    asyncio.create_task(send_order_confirmation(
        to_email=body.customer_email,
        order_id=str(order.id),
        items=[{"product_name": i.product_name, "product_price": float(i.product_price), "quantity": i.quantity} for i in body.items],
        subtotal=float(subtotal),
        shipping_cost=float(shipping_cost),
        total=float(total),
        shipping_address=body.shipping_address.model_dump(),
    ))

    return {
        "order_id": str(order.id),
        "status": order.status,
        "subtotal": float(subtotal),
        "shipping_cost": float(shipping_cost),
        "total": float(total),
    }


@router.get("/guest/{order_id}")
async def get_guest_order(order_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch a guest order by ID for the confirmation page."""
    try:
        uid = UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Order not found.")

    result = await db.execute(select(Order).where(Order.id == uid))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    items_result = await db.execute(select(OrderItem).where(OrderItem.order_id == uid))
    items = items_result.scalars().all()

    return {
        "order_id": str(order.id),
        "status": order.status,
        "subtotal": float(order.subtotal),
        "shipping_cost": float(order.shipping_cost),
        "total": float(order.total),
        "customer_email": order.customer_email,
        "shipping_address": order.shipping_address_snapshot,
        "items": [
            {
                "product_name": i.product_name,
                "product_price": float(i.product_price),
                "quantity": i.quantity,
                "line_total": float(i.line_total),
            }
            for i in items
        ],
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }
