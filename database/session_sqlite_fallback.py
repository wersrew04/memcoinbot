"""Async SQLAlchemy engine + session factory. Falls back gracefully if DB unavailable."""
from __future__ import annotations

from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager

from utils.logger import logger
from config.settings import settings

_engine = None
_session_factory = None
_initialized: bool = False


async def init_db() -> bool:
    """Create engine, session factory and tables. Returns True if OK."""
    global _engine, _session_factory, _initialized
    if _initialized and _engine is not None:
        return True
    try:
        from sqlalchemy.ext.asyncio import (
            create_async_engine,
            AsyncSession,
            async_sessionmaker,
        )
        from sqlalchemy.pool import StaticPool

        url = (settings.DATABASE_URL or "").strip()
        if not url:
            logger.warning("DATABASE_URL empty – DB disabled")
            return False

        # Normalize sqlite URL for aiosqlite
        if url.startswith("sqlite:///"):
            url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        elif url.startswith("sqlite+aiosqlite:///"):
            pass
        elif url.startswith("sqlite+aiosqlite://"):
            pass

        engine_kwargs = {
            "echo": False,
        }
        if "sqlite" in url:
            # SQLite async: check_same_thread + StaticPool for file DB
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url:
                engine_kwargs["poolclass"] = StaticPool
        else:
            engine_kwargs["pool_pre_ping"] = True
            engine_kwargs["pool_size"] = 5
            engine_kwargs["max_overflow"] = 10

        _engine = create_async_engine(url, **engine_kwargs)
        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        from database.models import Base

        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        _initialized = True
        logger.info(f"Database initialized ({url.split('://')[0]})")
        return True
    except Exception as e:
        logger.warning(f"Database init failed (continuing without DB): {e}")
        _engine = None
        _session_factory = None
        _initialized = False
        return False


async def close_db() -> None:
    global _engine, _session_factory, _initialized
    if _engine is not None:
        try:
            await _engine.dispose()
        except Exception:
            pass
    _engine = None
    _session_factory = None
    _initialized = False


def is_db_ready() -> bool:
    return _initialized and _session_factory is not None


@asynccontextmanager
async def get_session() -> AsyncGenerator:
    if not _session_factory:
        yield None
        return
    session = _session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise
    finally:
        await session.close()
