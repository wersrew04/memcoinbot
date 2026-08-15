"""Central configuration – all parameters controllable via Admin Panel / .env."""
from __future__ import annotations

from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    # ---------- Wallet ----------
    PRIVATE_KEY: str = ""
    RPC_URL: str = "https://api.mainnet-beta.solana.com"

    # ---------- APIs ----------
    BIRDEYE_API_KEY: str = ""
    JUPITER_API_KEY: Optional[str] = None
    HELIUS_API_KEY: str = ""
    OPENAI_API_KEY: Optional[str] = None
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    DISCORD_WEBHOOK_URL: str = ""
    EMAIL_SMTP_HOST: str = ""
    EMAIL_SMTP_PORT: int = 587
    EMAIL_USER: str = ""
    EMAIL_PASSWORD: str = ""
    EMAIL_TO: str = ""

    # ---------- Trading ----------
    TRADE_AMOUNT_USD: float = 10.0
    MAX_OPEN_POSITIONS: int = 5
    STOP_LOSS_PCT: float = 0.10
    TAKE_PROFIT_PCT: float = 0.30
    TRAILING_STOP_PCT: float = 0.15
    COOLDOWN_MINUTES: int = 30
    MAX_DAILY_LOSS_USD: float = 20.0
    MAX_RISK_PER_TOKEN_USD: float = 10.0
    MAX_CONSECUTIVE_LOSSES: int = 5
    MAX_DAILY_TRADES: int = 50
    MAX_TOKEN_ALLOCATION_PCT: float = 0.25  # portfolio share
    SLIPPAGE_BPS: int = 300
    PAPER_TRADING: bool = True
    PRIORITY_FEE_MICROLAMPORTS: int = 50_000

    # ---------- Filter thresholds (memecoin sniper profile) ----------
    # Token yoshi: 1–15 daqiqa
    MIN_TOKEN_AGE_MINUTES: float = 1.0
    MAX_TOKEN_AGE_MINUTES: float = 15.0
    # Liquidity: $20K–100K+
    MIN_LIQUIDITY_USD: float = 20_000
    MAX_LIQUIDITY_USD: float = 0  # 0 = yuqori chegara yo'q
    # Market Cap: $50K–500K
    MIN_MARKET_CAP_USD: float = 50_000
    MAX_MARKET_CAP_USD: float = 500_000
    # Volume
    MIN_24H_VOLUME_USD: float = 0  # yangi tokenlar uchun 24h majburiy emas
    MIN_VOLUME_5M_USD: float = 20_000  # 5 daqiqalik volume $20K+
    MIN_VOLUME_SPIKE_PCT: float = 2.0
    # Buy/Sell nisbati 2:1 yoki yuqori (5m txns)
    MIN_BUY_SELL_RATIO: float = 2.0
    # Holders
    MIN_HOLDERS: int = 100
    MAX_TOP10_HOLDER_PCT: float = 0.30  # 30% dan kam
    MAX_DEV_WALLET_PCT: float = 0.10
    # LP locked/burned majburiy (ma'lumot bo'lsa)
    REQUIRE_LP_LOCKED: bool = True

    # ---------- AI Engine ----------
    AI_ENABLED: bool = True
    AI_MIN_SCORE: float = 55.0          # 0-100
    AI_STRONG_BUY_THRESHOLD: float = 80.0
    AI_BUY_THRESHOLD: float = 65.0
    AI_LEARNING_RATE: float = 0.01
    AI_WEIGHT_LIQUIDITY: float = 0.12
    AI_WEIGHT_VOLUME: float = 0.10
    AI_WEIGHT_HOLDERS: float = 0.08
    AI_WEIGHT_WHALE: float = 0.12
    AI_WEIGHT_SMART_MONEY: float = 0.15
    AI_WEIGHT_MOMENTUM: float = 0.10
    AI_WEIGHT_SECURITY: float = 0.15
    AI_WEIGHT_SOCIAL: float = 0.08
    AI_WEIGHT_AGE: float = 0.05
    AI_WEIGHT_SIMILAR: float = 0.05

    # ---------- Smart Money ----------
    SMART_MONEY_ENABLED: bool = True
    SMART_MONEY_MIN_ROI_PCT: float = 200.0
    SMART_MONEY_MIN_WIN_RATE: float = 0.70
    SMART_MONEY_MIN_TRADES: int = 100
    SMART_MONEY_SCORE_BOOST: float = 15.0  # added to AI score when multi-wallet buy

    # ---------- Whale Tracking ----------
    WHALE_TRACKING_ENABLED: bool = True
    WHALE_THRESHOLDS_USD: str = "100000,250000,500000,1000000"  # comma-separated
    WHALE_BUY_SCORE_BOOST: float = 10.0
    WHALE_SELL_SCORE_PENALTY: float = 12.0

    # ---------- Social Intelligence (X.com official API only) ----------
    SOCIAL_INTELLIGENCE_ENABLED: bool = False  # X_API_BEARER_TOKEN o'rnatilmaguncha default OFF
    X_API_BEARER_TOKEN: Optional[str] = None
    SOCIAL_API_TIMEOUT_SEC: float = 5.0
    SOCIAL_CACHE_TTL_MIN: float = 30.0  # bir xil token uchun qayta so'rov yubormaslik
    SOCIAL_MAX_CALLS_PER_DAY: int = 150  # X API kvotangizga mos sozlang
    SOCIAL_MIN_MENTIONS_FOR_SIGNAL: int = 3
    SOCIAL_INFLUENCER_FOLLOWER_THRESHOLD: int = 20000

    # ---------- MEV Protection ----------
    MEV_PROTECTION_ENABLED: bool = True
    MEV_MAX_SLIPPAGE_BPS: int = 500
    MEV_SANDWICH_RISK_THRESHOLD: float = 0.7
    MEV_DYNAMIC_SLIPPAGE: bool = True
    MEV_RETRY_ATTEMPTS: int = 3

    # ---------- Blacklist ----------
    AUTO_BLACKLIST_ENABLED: bool = True
    BLACKLIST_HONEYPOT: bool = True
    BLACKLIST_RUG_PULL: bool = True
    BLACKLIST_FAKE_VOLUME: bool = True
    BLACKLIST_MALICIOUS: bool = True

    # ---------- Advanced Risk ----------
    EMERGENCY_STOP: bool = False
    AUTO_PAUSE_ON_ERROR: bool = True
    MAX_DRAWDOWN_PCT: float = 0.25

    # ---------- Portfolio ----------
    PORTFOLIO_MAX_SECTOR_PCT: float = 0.40
    PORTFOLIO_DIVERSIFICATION_MIN: int = 3

    # ---------- Notifications ----------
    NOTIFY_TELEGRAM: bool = True
    NOTIFY_DISCORD: bool = False
    NOTIFY_EMAIL: bool = False
    NOTIFY_ON_BUY: bool = True
    NOTIFY_ON_SELL: bool = True
    NOTIFY_ON_AI_SIGNAL: bool = True
    NOTIFY_ON_WHALE: bool = True
    NOTIFY_ON_ERROR: bool = True

    # ---------- Monitoring ----------
    RPC_HEALTH_CHECK_INTERVAL_SEC: int = 60
    API_LATENCY_THRESHOLD_MS: int = 2000
    AUTO_RECOVERY_ENABLED: bool = True

    # ---------- Backtest ----------
    BACKTEST_DEFAULT_DAYS: int = 30

    # ---------- Monitor interval ----------
    POSITION_MONITOR_INTERVAL_SEC: int = 15
    SCANNER_INTERVAL_SEC: int = 60
    SELL_RETRY_ATTEMPTS: int = 3
    PARTIAL_TP_ENABLED: bool = False
    PARTIAL_TP_PCT: float = 0.5  # 50% of position
    PARTIAL_TP_TRIGGER_PCT: float = 0.30  # at +30%

    # ---------- Database & Redis ----------
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/memebot"
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---------- Admin / API ----------
    ADMIN_API_HOST: str = "0.0.0.0"
    ADMIN_API_PORT: int = 8080  # overridden by $PORT in main.py for Railway/Heroku/Render
    ADMIN_API_KEY: str = "change-me-in-production"

    # ---------- Admin Panel (web login) ----------
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    ADMIN_SESSION_SECRET: str = "change-this-session-secret-in-production"

    # ---------- Bot control ----------
    BOT_RUNNING: bool = True

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }

    def whale_thresholds_list(self) -> List[float]:
        return [float(x.strip()) for x in self.WHALE_THRESHOLDS_USD.split(",") if x.strip()]


settings = Settings()
