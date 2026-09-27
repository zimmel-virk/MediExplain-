"""Async SQLAlchemy session setup."""

# This file sets up the asynchronous database connection used throughout
# MediExplain+. It creates the SQLAlchemy engine and reusable async session
# factory, provides the database dependency used by API routes, and makes sure
# each request is either committed successfully or rolled back if an error
# occurs. The initialisation function also runs the existing database setup
# routine so required schema changes are applied when the application starts.


from sqlalchemy.ext.asyncio import AsyncSession,async_sessionmaker,create_async_engine
from app.core.base import Base
from app.core.config import settings

engine=create_async_engine(settings.DATABASE_URL,echo=settings.DEBUG,future=True)
AsyncSessionLocal=async_sessionmaker(
    bind=engine,class_=AsyncSession,expire_on_commit=False,autoflush=False
)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def init_db()->None:
    from app.core.migrations import ensure_database
    ensure_database()
