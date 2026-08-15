"""Database layer tests.

test_repo_degrades_without_db: always runs, no Postgres required — proves
the core bot can't be broken by a missing/unreachable database.

test_trade_repo_roundtrip: only runs if TEST_DATABASE_URL env var points
at a real (throwaway) Postgres instance; otherwise skipped. Run locally:

    docker compose up -d postgres
    TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/memebot \
        pytest tests/test_database.py -v
"""
import os

import pytest


@pytest.mark.asyncio
async def test_repo_degrades_without_db(monkeypatch):
    """Point at an address nothing is listening on; every repository call
    must return an empty/None result instead of raising."""
    import database.session as session_mod
    from database.repository import trade_repo

    monkeypatch.setattr(
        session_mod, "_engine", None, raising=False
    )
    monkeypatch.setattr(
        session_mod, "_session_factory", None, raising=False
    )
    monkeypatch.setattr(
        "config.settings.settings.DATABASE_URL",
        "postgresql+asyncpg://baduser:badpass@127.0.0.1:1/nodb",
        raising=False,
    )

    result_id = await trade_repo.add(
        token_address="TestToken111",
        symbol="TST",
        pnl_usd=-5.0,
        pnl_pct=-2.0,
        reason="stop_loss",
    )
    assert result_id is None

    rows = await trade_repo.recent(limit=10)
    assert rows == []


@pytest.mark.asyncio
async def test_trade_repo_roundtrip():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set – skipping live DB roundtrip test")

    import database.session as session_mod
    from database.repository import trade_repo

    session_mod._engine = None
    session_mod._session_factory = None
    from config.settings import settings as app_settings
    app_settings.DATABASE_URL = url

    await session_mod.init_models()

    row_id = await trade_repo.add(
        token_address="RoundtripToken111",
        symbol="RTT",
        amount_usd=10.0,
        entry_price=0.001,
        exit_price=0.0012,
        pnl_usd=2.0,
        pnl_pct=20.0,
        reason="take_profit",
        paper=True,
    )
    assert row_id is not None

    rows = await trade_repo.by_token("RoundtripToken111", limit=5)
    assert len(rows) >= 1
    assert rows[0].symbol == "RTT"

    await session_mod.close_engine()
