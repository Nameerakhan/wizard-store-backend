"""
Async PostgreSQL connection via SQLAlchemy.

Reads DATABASE_URL from environment. Falls back to None (safe for non-DB deployments).
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("wizard_store.database")

_DATABASE_URL = os.getenv("DATABASE_URL")

# Engine and session factory are None when DATABASE_URL is not configured.
# Services that require the DB must check for None and return 503.
engine = None
AsyncSessionLocal = None


def _init_engine():
    global engine, AsyncSessionLocal
    if _DATABASE_URL:
        engine = create_async_engine(
            _DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
        )
        AsyncSessionLocal = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("Database engine created")
    else:
        logger.warning("DATABASE_URL not set — PostgreSQL features are disabled")


_init_engine()


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """
    Called at application startup to verify the database connection.
    Logs a warning (does not crash) if DATABASE_URL is not set.
    """
    if engine is None:
        logger.warning("Skipping DB init — DATABASE_URL not configured")
        return
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__('sqlalchemy').text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception as e:
        logger.error("Database connection failed: %s", e)
        raise
