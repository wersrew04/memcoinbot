"""SQLAlchemy 2.0 async ORM models.

Bu modul mavjud JSON/JSONL asosidagi saqlash (utils/history.py,
ai_engine/learner.py, blacklist/manager.py va h.k.) ni ALMASHTIRMAYDI —
ular hozir ishlab turibdi va ishlashda davom etadi. Bu yerdagi modellar
YANGI, ixtiyoriy Postgres qatlami: yangi modullar (Smart Money ingestion,
ML, Social Intelligence, Backtest) shu jadvallarga yozadi/o'qiydi.

Production'da schema Alembic migratsiyalari orqali boshqariladi
(``alembic upgrade head``). ``Base.metadata.create_all`` faqat lokal /
test muhitlarda tezkor boshlash uchun (``database.session.init_models``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TradeRecord(Base):
    """Yopilgan savdolar — utils/history.py dagi JSONL bilan bir xil
    ma'lumot, lekin so'rov/agregatsiya (backtest, dashboard) uchun qulay."""

    __tablename__ = "trades"
    __table_args__ = (Index("ix_trades_token_closed", "token_address", "closed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_address: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), default="")
    side: Mapped[str] = mapped_column(String(8), default="sell")  # trade yopilishi doim "sell"
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    entry_price: Mapped[float] = mapped_column(Float, default=0.0)
    exit_price: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_usd: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(32), default="")  # stop_loss/take_profit/trailing_stop
    ai_score: Mapped[float] = mapped_column(Float, default=0.0)
    tx_hash: Mapped[str] = mapped_column(String(128), default="")
    paper: Mapped[bool] = mapped_column(Boolean, default=True)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class MLPrediction(Base):
    """ML/Prediction History — Section 2 va 10: pump/rug probability,
    trend strength, confidence, future return estimate."""

    __tablename__ = "ml_predictions"
    __table_args__ = (Index("ix_ml_pred_token_created", "token_address", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_address: Mapped[str] = mapped_column(String(64), index=True)
    model_version: Mapped[str] = mapped_column(String(32), default="")
    pump_probability: Mapped[float] = mapped_column(Float, default=0.0)
    rug_probability: Mapped[float] = mapped_column(Float, default=0.0)
    trend_strength: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    future_return_estimate_pct: Mapped[float] = mapped_column(Float, default=0.0)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Haqiqiylashgan natija (trade yopilgach to'ldiriladi) — model qayta train uchun
    realized_pnl_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class AIScoreRecord(Base):
    """AI Score History — har bir hisoblangan Overall AI Score + faktorlar."""

    __tablename__ = "ai_scores"
    __table_args__ = (Index("ix_ai_scores_token_created", "token_address", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_address: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    recommendation: Mapped[str] = mapped_column(String(16), default="")
    factors: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class WhaleEventRecord(Base):
    """Whale History — katta xarid/sotish/accumulation/distribution hodisalari."""

    __tablename__ = "whale_events"
    __table_args__ = (Index("ix_whale_token_created", "token_address", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_address: Mapped[str] = mapped_column(String(64), index=True)
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(16))  # buy|sell|transfer|accumulation|distribution
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    tier: Mapped[str] = mapped_column(String(16), default="")
    tx_hash: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class SocialScoreRecord(Base):
    """Social History — Section 5: X.com orqali olingan ijtimoiy signal."""

    __tablename__ = "social_scores"
    __table_args__ = (Index("ix_social_token_created", "token_address", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_address: Mapped[str] = mapped_column(String(64), index=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=0)
    mention_growth_pct: Mapped[float] = mapped_column(Float, default=0.0)
    engagement: Mapped[int] = mapped_column(Integer, default=0)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    repost_count: Mapped[int] = mapped_column(Integer, default=0)
    verified_mentions: Mapped[int] = mapped_column(Integer, default=0)
    influencer_mentions: Mapped[int] = mapped_column(Integer, default=0)
    developer_posts: Mapped[int] = mapped_column(Integer, default=0)
    sentiment_positive_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment_negative_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment_neutral_pct: Mapped[float] = mapped_column(Float, default=0.0)
    trend_score: Mapped[float] = mapped_column(Float, default=0.0)
    virality_score: Mapped[float] = mapped_column(Float, default=0.0)
    fake_hype_score: Mapped[float] = mapped_column(Float, default=0.0)
    bot_activity_score: Mapped[float] = mapped_column(Float, default=0.0)
    social_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    social_score: Mapped[float] = mapped_column(Float, default=0.0)  # AI Score ichiga qo'shiladigan yakuniy qiymat
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class BlacklistRecord(Base):
    """Blacklist — blacklist/manager.py dagi data/blacklist.json bilan bir xil
    ma'lumot, ko'p-instansli/ko'p-worker joylashuvlar uchun DB'da ham saqlash."""

    __tablename__ = "blacklist"
    __table_args__ = (UniqueConstraint("token_address", name="uq_blacklist_token"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_address: Mapped[str] = mapped_column(String(64), index=True)
    reason: Mapped[str] = mapped_column(String(32))
    details: Mapped[str] = mapped_column(String(500), default="")
    source: Mapped[str] = mapped_column(String(16), default="auto")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class WalletStat(Base):
    """Wallet Stats — Smart Money uchun wallet trust/profitability/consistency."""

    __tablename__ = "wallet_stats"
    __table_args__ = (UniqueConstraint("wallet_address", name="uq_wallet_stats_address"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_address: Mapped[str] = mapped_column(String(64), index=True)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_roi_pct: Mapped[float] = mapped_column(Float, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    avg_hold_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    trust_score: Mapped[float] = mapped_column(Float, default=0.0)
    consistency_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    label: Mapped[str] = mapped_column(String(64), default="")
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)
