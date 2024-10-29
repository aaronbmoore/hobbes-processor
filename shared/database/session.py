from typing import AsyncGenerator
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import ssl
import os
# from dotenv import load_dotenv
from ..utils import get_database_url

# Create SSL context for Neon
ssl_context = ssl.create_default_context()
ssl_context.verify_mode = ssl.CERT_REQUIRED

# Create async engine with Neon SSL configuration
engine = create_async_engine(
    get_database_url(),
    connect_args={
        "ssl": ssl_context,
        "server_settings": {
            "ssl": "true"
        }
    },
    pool_pre_ping=True,  # Added for Lambda cold starts
    pool_size=5,         # Configured for Lambda concurrent executions
    max_overflow=10
)

# Create async session factory
AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Context manager for Lambda functions
@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional scope around a series of operations."""
    session: AsyncSession = AsyncSessionFactory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

# FastAPI dependency
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database sessions"""
    async with AsyncSessionFactory() as session:
        try:
            yield session
        finally:
            await session.close()

# Optional: Database initialization functions
async def init_db() -> None:
    """Initialize database - use for testing or first-time setup"""
    from .models import Base  # Import here to avoid circular imports
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def cleanup_db() -> None:
    """Cleanup database - use for testing"""
    from .models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)