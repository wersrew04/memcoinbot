"""Async engine / session factory.

Ishlatilishi::

    from database.session import get_session

    async with get_session() as session:
        session.add(obj)
        await session.commit()

Postgres mavjud bo'lmasa yoki ulanish muvaffaqiyatsiz bo'lsa, bu qatlamdan
foydalanadigan chaqiruvchi kod (repository.py) xatoni yutib, ``None``/bo'sh
natija qaytaradi — DB YO'QLIGI asosiy botni (paper trading, scanner, buy/sell)
TO'XTATMASLIGI KERAK. DB faqat qo'shimcha tahlil/tarix qatlami.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.settings import settings
from utils.logger import logger
from database.models import Base

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        url = (settings.DATABASE_URL or "").strip()
        if url.startswith("sqlite:///"):
            url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        # Ensure parent dir exists for sqlite files (e.g. ./data/memebot.db)
        if "sqlite" in url:
            from pathlib import Path
            try:
                path_part = url.split("///", 1)[-1]
                Path(path_part).parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        kwargs = {"echo": False}
        if "sqlite" in url:
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=10, pool_recycle=1800)
        _engine = create_async_engine(url, **kwargs)
        _session_factory = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
    return _engine


@asynccontextmanager
async def get_session() -> AsyncIterator[Optional[AsyncSession]]:
    """Yields an AsyncSession, or None if the DB is unreachable.

    Callers should treat ``None`` as "DB layer unavailable this time" and
    degrade gracefully (matches repository.py behaviour).
    """
    get_engine()
    assert _session_factory is not None
    session: Optional[AsyncSession] = None
    try:
        session = _session_factory()
        yield session
    except Exception as e:
        logger.warning(f"DB session xatosi: {e}")
        yield None
    finally:
        if session is not None:
            await session.close()


async def init_models() -> bool:
    """Dev/test convenience: create tables directly from models
    (``Base.metadata.create_all``). Production should use Alembic
    (``alembic upgrade head``) instead — this is NOT a migration tool.
    Returns True on success, False if DB unreachable (non-fatal)."""
    try:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database jadvallari tayyor (init_models)")
        return True
    except Exception as e:
        logger.warning(f"init_models: DB ulanmadi, o'tkazib yuborildi: {e}")
        return False


async def close_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
