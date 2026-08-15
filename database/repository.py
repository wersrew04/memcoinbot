"""Repository Pattern — DB bilan ishlaydigan yagona qatlam.

Boshqa modullar (Smart Money ingestion, ML, Social, Backtest, Admin Panel)
to'g'ridan-to'g'ri SQLAlchemy bilan emas, shu repositorylar orqali ishlaydi.

Muhim: har bir metod DB mavjud bo'lmasa ham xato tashlamaydi (bo'sh
ro'yxat/None qaytaradi + warning log). Bu mavjud botning DB'siz (yoki
Postgres hali sozlanmagan) holatda ham to'liq ishlashini kafolatlaydi.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from sqlalchemy import select, update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from utils.logger import logger
from database.session import get_session
from database.models import (
    TradeRecord,
    MLPrediction,
    AIScoreRecord,
    WhaleEventRecord,
    SocialScoreRecord,
    BlacklistRecord,
    WalletStat,
)


class _BaseRepository:
    model: type

    async def add(self, **fields: Any) -> Optional[int]:
        async with get_session() as session:
            if session is None:
                return None
            try:
                obj = self.model(**fields)
                session.add(obj)
                await session.commit()
                await session.refresh(obj)
                return obj.id
            except Exception as e:
                logger.warning(f"{self.model.__name__} yozishda xato: {e}")
                await session.rollback()
                return None

    async def recent(self, limit: int = 50) -> Sequence[Any]:
        async with get_session() as session:
            if session is None:
                return []
            try:
                stmt = select(self.model).order_by(self.model.id.desc()).limit(limit)
                res = await session.execute(stmt)
                return list(res.scalars().all())
            except Exception as e:
                logger.warning(f"{self.model.__name__} o'qishda xato: {e}")
                return []

    async def by_token(self, token_address: str, limit: int = 50) -> Sequence[Any]:
        async with get_session() as session:
            if session is None:
                return []
            try:
                stmt = (
                    select(self.model)
                    .where(self.model.token_address == token_address)
                    .order_by(self.model.id.desc())
                    .limit(limit)
                )
                res = await session.execute(stmt)
                return list(res.scalars().all())
            except Exception as e:
                logger.warning(f"{self.model.__name__} by_token xato: {e}")
                return []


class TradeRepository(_BaseRepository):
    model = TradeRecord


class MLPredictionRepository(_BaseRepository):
    model = MLPrediction

    async def mark_realized(self, prediction_id: int, realized_pnl_pct: float) -> bool:
        """Trade yopilgach bashoratni haqiqiy natija bilan bog'lash (model
        qayta-train qilish uchun label)."""
        async with get_session() as session:
            if session is None:
                return False
            try:
                stmt = (
                    sa_update(MLPrediction)
                    .where(MLPrediction.id == prediction_id)
                    .values(realized_pnl_pct=realized_pnl_pct)
                )
                await session.execute(stmt)
                await session.commit()
                return True
            except Exception as e:
                logger.warning(f"ML prediction realize xato: {e}")
                await session.rollback()
                return False

    async def training_dataset(self, limit: int = 5000) -> Sequence[MLPrediction]:
        """Faqat natijasi ma'lum (realized_pnl_pct to'ldirilgan) yozuvlar —
        model qayta-train qilish uchun."""
        async with get_session() as session:
            if session is None:
                return []
            try:
                stmt = (
                    select(MLPrediction)
                    .where(MLPrediction.realized_pnl_pct.is_not(None))
                    .order_by(MLPrediction.id.desc())
                    .limit(limit)
                )
                res = await session.execute(stmt)
                return list(res.scalars().all())
            except Exception as e:
                logger.warning(f"ML training dataset o'qishda xato: {e}")
                return []


class AIScoreRepository(_BaseRepository):
    model = AIScoreRecord


class WhaleEventRepository(_BaseRepository):
    model = WhaleEventRecord


class SocialScoreRepository(_BaseRepository):
    model = SocialScoreRecord


class BlacklistRepository(_BaseRepository):
    """blacklist/manager.py (JSON fayl) bilan parallel, ixtiyoriy DB nusxasi —
    ko'p-worker joylashuvlarda (masalan bir nechta bot instansi) markaziy
    ro'yxat sifatida foydali. Asosiy tekshiruv hamon JSON fayl orqali."""

    model = BlacklistRecord

    async def upsert(self, token_address: str, reason: str, details: str = "", source: str = "auto") -> bool:
        async with get_session() as session:
            if session is None:
                return False
            try:
                stmt = pg_insert(BlacklistRecord).values(
                    token_address=token_address,
                    reason=reason,
                    details=details,
                    source=source,
                )
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_blacklist_token",
                    set_={"reason": reason, "details": details, "source": source},
                )
                await session.execute(stmt)
                await session.commit()
                return True
            except Exception as e:
                logger.warning(f"Blacklist DB upsert xato: {e}")
                await session.rollback()
                return False


class WalletStatRepository(_BaseRepository):
    model = WalletStat

    async def upsert(self, wallet_address: str, **fields: Any) -> bool:
        async with get_session() as session:
            if session is None:
                return False
            try:
                stmt = pg_insert(WalletStat).values(wallet_address=wallet_address, **fields)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_wallet_stats_address",
                    set_=fields,
                )
                await session.execute(stmt)
                await session.commit()
                return True
            except Exception as e:
                logger.warning(f"WalletStat DB upsert xato: {e}")
                await session.rollback()
                return False


# Singletonlar — boshqa modullar shu instansiyalarni import qiladi
trade_repo = TradeRepository()
ml_prediction_repo = MLPredictionRepository()
ai_score_repo = AIScoreRepository()
whale_event_repo = WhaleEventRepository()
social_score_repo = SocialScoreRepository()
blacklist_repo = BlacklistRepository()
wallet_stat_repo = WalletStatRepository()
