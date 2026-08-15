# Extended Modules

## Architecture
scanner -> FilterPipeline (classic + blacklist + AI + smart money + whale)
        -> BuyExecutor (advanced risk + portfolio + MEV)
        -> PositionMonitor (TP/SL/trail)

## Modules
- ai_engine/ - AI score 0-100 + TradeLearner
- smart_money/ - high-ROI wallet DB + score boost
- whale_tracking/ - large transfer events
- social_intelligence/ - X.com (rasmiy API) mention/sentiment/virality/fake-hype
  signali → `data["social_score"]` orqali AI Score ichiga qo'shiladi
  (ai_engine/scorer.py da `AI_WEIGHT_SOCIAL` allaqachon mavjud edi).
  `SOCIAL_INTELLIGENCE_ENABLED=false` yoki `X_API_BEARER_TOKEN` bo'sh
  bo'lsa — hech qanday tarmoq so'rovi yubormay, neytral (0.5) ball
  qaytaradi. Sentiment/fake-hype/bot-activity hozircha oddiy
  leksikon/evristika bilan hisoblanadi (haqiqiy NLP model emas) —
  keyinchalik ML modeli bilan almashtirilishi mumkin.
- mev_protection/ - sandwich heuristics + dynamic slippage
- blacklist/ - auto + manual blacklist
- advanced_risk/ - consecutive losses, daily cap, emergency stop
- portfolio/ - allocation limits
- notifications/ - Telegram / Discord / Email
- monitoring/ - RPC/API health
- backtest_engine/ - metrics + backtest scaffold
- admin_panel/ - FastAPI control (port 8080)
- database/ - optional async Postgres layer (models/session/repository) —
  see below. The bot fully works without it (paper trading, JSON-based
  history/blacklist/AI-weights all keep working as before).

## Database (optional Postgres layer)
Additive only — does not replace utils/history.py, blacklist/manager.py's
JSON files, or ai_engine/learner.py's weight file. Those keep working
unchanged. New modules (Smart Money real-data ingestion, ML, Social
Intelligence, Backtest-on-real-history) persist through
`database/repository.py`'s repositories instead of talking to SQLAlchemy
directly.

Tables (see `database/models.py`): `trades`, `ml_predictions`, `ai_scores`,
`whale_events`, `social_scores`, `blacklist`, `wallet_stats`.

Setup:
```bash
docker compose up -d postgres
alembic upgrade head
```
Every repository method degrades gracefully (returns `None`/`[]` + a
warning log) if Postgres is unreachable — the core trading loop never
depends on the database being up.

## Admin API
Header: X-Admin-Key
GET /settings, /status, /modules, /ai/weights, /blacklist
POST /settings, /control/start|stop|emergency-stop|paper-toggle

## Security
Never commit .env. Rotate keys. Paper mode default.
