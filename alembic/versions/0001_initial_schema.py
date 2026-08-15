"""initial schema — trades, ml_predictions, ai_scores, whale_events,
social_scores, blacklist, wallet_stats

Revision ID: 0001
Revises:
Create Date: 2026-07-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_address", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("side", sa.String(length=8), nullable=False, server_default="sell"),
        sa.Column("amount_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("entry_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("exit_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pnl_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pnl_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("ai_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tx_hash", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("paper", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trades_token_address", "trades", ["token_address"])
    op.create_index("ix_trades_token_closed", "trades", ["token_address", "closed_at"])

    op.create_table(
        "ml_predictions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_address", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("pump_probability", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rug_probability", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trend_strength", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("future_return_estimate_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("features", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("realized_pnl_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ml_predictions_token_address", "ml_predictions", ["token_address"])
    op.create_index("ix_ml_pred_token_created", "ml_predictions", ["token_address", "created_at"])

    op.create_table(
        "ai_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_address", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("recommendation", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("factors", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_scores_token_address", "ai_scores", ["token_address"])
    op.create_index("ix_ai_scores_token_created", "ai_scores", ["token_address", "created_at"])

    op.create_table(
        "whale_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_address", sa.String(length=64), nullable=False),
        sa.Column("wallet_address", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tier", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("tx_hash", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_whale_events_token_address", "whale_events", ["token_address"])
    op.create_index("ix_whale_events_wallet_address", "whale_events", ["wallet_address"])
    op.create_index("ix_whale_token_created", "whale_events", ["token_address", "created_at"])

    op.create_table(
        "social_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_address", sa.String(length=64), nullable=False),
        sa.Column("mention_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mention_growth_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("engagement", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("like_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reply_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repost_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_mentions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("influencer_mentions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("developer_posts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sentiment_positive_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sentiment_negative_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sentiment_neutral_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trend_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("virality_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fake_hype_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("bot_activity_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("social_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("social_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("raw", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_social_scores_token_address", "social_scores", ["token_address"])
    op.create_index("ix_social_token_created", "social_scores", ["token_address", "created_at"])

    op.create_table(
        "blacklist",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_address", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("details", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="auto"),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_address", name="uq_blacklist_token"),
    )
    op.create_index("ix_blacklist_token_address", "blacklist", ["token_address"])

    op.create_table(
        "wallet_stats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("wallet_address", sa.String(length=64), nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_roi_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_hold_minutes", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("consistency_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("rating", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("wallet_address", name="uq_wallet_stats_address"),
    )
    op.create_index("ix_wallet_stats_wallet_address", "wallet_stats", ["wallet_address"])


def downgrade() -> None:
    op.drop_table("wallet_stats")
    op.drop_table("blacklist")
    op.drop_table("social_scores")
    op.drop_table("whale_events")
    op.drop_table("ai_scores")
    op.drop_table("ml_predictions")
    op.drop_table("trades")
