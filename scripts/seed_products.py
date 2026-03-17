"""
Seed products from backend/data/products.json into PostgreSQL.

Usage:
  cd backend
  python scripts/seed_products.py

Skips any product whose name already exists (idempotent).
Requires DATABASE_URL to be set in .env or environment.
"""

import asyncio
import json
import sys
from pathlib import Path

# Allow running from the backend/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select
from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import Product

_DATA_FILE = Path(__file__).parent.parent / 'data' / 'products.json'


async def seed():
    await init_db()

    with open(_DATA_FILE, 'r', encoding='utf-8') as f:
        products = json.load(f)

    async with AsyncSessionLocal() as session:
        seeded = 0
        skipped = 0
        for p in products:
            existing = await session.scalar(
                select(Product).where(Product.name == p['name'])
            )
            if existing:
                skipped += 1
                continue

            session.add(Product(
                name=p['name'],
                category=p['category'],
                house=p.get('house', ''),
                price=p['price'],
                description=p['description'],
                tags=p.get('tags', []),
                stock_status=p.get('stock_status', 'In Stock'),
                image_url=p.get('image_url'),
            ))
            seeded += 1

        await session.commit()

    print(f"Seeded {seeded} products into PostgreSQL (skipped {skipped} existing)")


if __name__ == '__main__':
    asyncio.run(seed())
