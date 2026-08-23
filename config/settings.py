"""Barcha sozlamalar — .env dan o'qiladi."""
from __future__ import annotations
import os
from pathlib import Path

def _bool(val: str, default: bool = False) -> bool:
    if val is None:
        return default
    val_str = str(val).strip("'\"").lower()
    return val_str in ("1", "true", "yes", "on")

def _float(val, default: float = 0.0) -> float:
    try:
        if isinstance(val, str):
            val = val.strip("'\"")
        return float(val)
    except (TypeError, ValueError):
        return default

def _int(val, default: int = 0) -> int:
    try:
        if isinstance(val, str):
            val = val.strip("'\"")
        return int(float(val))
    except (TypeError, ValueError):
        return default

# .env ni yuklash
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

g = os.environ.get

class Settings:
    # === Wallet ===
    PRIVATE_KEY: str = g("PRIVATE_KEY", "")
    RPC_URL: str = g("RPC_URL", "https://api.mainnet-beta.solana.com")

    # === API kalitlari ===
    BIRDEYE_API_KEY: str = g("BIRDEYE_API_KEY", "")
    JUPITER_API_KEY: str = g("JUPITER_API_KEY", "")
    HELIUS_API_KEY: str = g("HELIUS_API_KEY", "")
    OPENAI_API_KEY: str = g("OPENAI_API_KEY", "")
    TELEGRAM_BOT_TOKEN: str = g("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = g("TELEGRAM_CHAT_ID", "")
    # true = oddiy foydalanuvchilar ham botdan foydalanishi mumkin
    # (token tekshirish, status, stats). Admin buyruqlari faqat TELEGRAM_CHAT_ID da.
    PUBLIC_BOT_ENABLED: bool = _bool(g("PUBLIC_BOT_ENABLED"), True)
    DISCORD_WEBHOOK_URL: str = g("DISCORD_WEBHOOK_URL", "")
    X_API_BEARER_TOKEN: str = g("X_API_BEARER_TOKEN", "")
    EMAIL_SMTP_HOST: str = g("EMAIL_SMTP_HOST", "")
    EMAIL_SMTP_PORT: int = _int(g("EMAIL_SMTP_PORT"), 587)
    EMAIL_USER: str = g("EMAIL_USER", "")
    EMAIL_PASSWORD: str = g("EMAIL_PASSWORD", "")
    EMAIL_TO: str = g("EMAIL_TO", "")

    # === Savdo ===
    PAPER_TRADING: bool = _bool(g("PAPER_TRADING"), True)
    TRADE_AMOUNT_USD: float = _float(g("TRADE_AMOUNT_USD"), 1.0)
    MAX_OPEN_POSITIONS: int = _int(g("MAX_OPEN_POSITIONS"), 5)
    STOP_LOSS_PCT: float = _float(g("STOP_LOSS_PCT"), 0.10)
    TAKE_PROFIT_PCT: float = _float(g("TAKE_PROFIT_PCT"), 0.30)
    TRAILING_STOP_PCT: float = _float(g("TRAILING_STOP_PCT"), 0.15)
    COOLDOWN_MINUTES: int = _int(g("COOLDOWN_MINUTES"), 30)
    MAX_DAILY_LOSS_USD: float = _float(g("MAX_DAILY_LOSS_USD"), 20.0)
    MAX_RISK_PER_TOKEN_USD: float = _float(g("MAX_RISK_PER_TOKEN_USD"), 10.0)
    MAX_CONSECUTIVE_LOSSES: int = _int(g("MAX_CONSECUTIVE_LOSSES"), 5)
    MAX_DAILY_TRADES: int = _int(g("MAX_DAILY_TRADES"), 50)
    SLIPPAGE_BPS: int = _int(g("SLIPPAGE_BPS"), 300)
    PRIORITY_FEE_MICROLAMPORTS: int = _int(g("PRIORITY_FEE_MICROLAMPORTS"), 50000)
    SELL_RETRY_ATTEMPTS: int = _int(g("SELL_RETRY_ATTEMPTS"), 3)
    PARTIAL_TP_ENABLED: bool = _bool(g("PARTIAL_TP_ENABLED"), False)
    PARTIAL_TP_PCT: float = _float(g("PARTIAL_TP_PCT"), 0.5)
    PARTIAL_TP_TRIGGER_PCT: float = _float(g("PARTIAL_TP_TRIGGER_PCT"), 0.30)

    # === Filtrlar ===
    # Defaultlar yangi memecoinlar uchun realistikroq qilindi —
    # avvalgi 20k vol5m / ratio 2.0 / age 15m deyarli hech narsa o'tkazmas edi.
    MIN_TOKEN_AGE_MINUTES: float = _float(g("MIN_TOKEN_AGE_MINUTES"), 0.5)
    MAX_TOKEN_AGE_MINUTES: float = _float(g("MAX_TOKEN_AGE_MINUTES"), 60.0)
    MIN_LIQUIDITY_USD: float = _float(g("MIN_LIQUIDITY_USD"), 8000)
    MAX_LIQUIDITY_USD: float = _float(g("MAX_LIQUIDITY_USD"), 0)
    MIN_MARKET_CAP_USD: float = _float(g("MIN_MARKET_CAP_USD"), 15000)
    MAX_MARKET_CAP_USD: float = _float(g("MAX_MARKET_CAP_USD"), 2_000_000)
    MIN_24H_VOLUME_USD: float = _float(g("MIN_24H_VOLUME_USD"), 0)
    MIN_VOLUME_5M_USD: float = _float(g("MIN_VOLUME_5M_USD"), 3000)
    MIN_VOLUME_SPIKE_PCT: float = _float(g("MIN_VOLUME_SPIKE_PCT"), 1.5)
    MIN_BUY_SELL_RATIO: float = _float(g("MIN_BUY_SELL_RATIO"), 1.15)
    MIN_HOLDERS: int = _int(g("MIN_HOLDERS"), 30)
    MAX_TOP10_HOLDER_PCT: float = _float(g("MAX_TOP10_HOLDER_PCT"), 0.45)
    MAX_DEV_WALLET_PCT: float = _float(g("MAX_DEV_WALLET_PCT"), 0.15)
    REQUIRE_LP_LOCKED: bool = _bool(g("REQUIRE_LP_LOCKED"), False)

    # === AI ===
    AI_ENABLED: bool = _bool(g("AI_ENABLED"), True)
    AI_MIN_SCORE: float = _float(g("AI_MIN_SCORE"), 55.0)
    AI_STRONG_BUY_THRESHOLD: float = _float(g("AI_STRONG_BUY_THRESHOLD"), 80.0)
    AI_BUY_THRESHOLD: float = _float(g("AI_BUY_THRESHOLD"), 65.0)
    AI_LEARNING_RATE: float = _float(g("AI_LEARNING_RATE"), 0.01)
    AI_WEIGHT_LIQUIDITY: float = _float(g("AI_WEIGHT_LIQUIDITY"), 0.12)
    AI_WEIGHT_VOLUME: float = _float(g("AI_WEIGHT_VOLUME"), 0.10)
    AI_WEIGHT_HOLDERS: float = _float(g("AI_WEIGHT_HOLDERS"), 0.08)
    AI_WEIGHT_WHALE: float = _float(g("AI_WEIGHT_WHALE"), 0.12)
    AI_WEIGHT_SMART_MONEY: float = _float(g("AI_WEIGHT_SMART_MONEY"), 0.15)
    AI_WEIGHT_MOMENTUM: float = _float(g("AI_WEIGHT_MOMENTUM"), 0.10)
    AI_WEIGHT_SECURITY: float = _float(g("AI_WEIGHT_SECURITY"), 0.15)
    AI_WEIGHT_SOCIAL: float = _float(g("AI_WEIGHT_SOCIAL"), 0.08)
    AI_WEIGHT_AGE: float = _float(g("AI_WEIGHT_AGE"), 0.05)
    AI_WEIGHT_SIMILAR: float = _float(g("AI_WEIGHT_SIMILAR"), 0.05)

    # === Smart Money ===
    SMART_MONEY_ENABLED: bool = _bool(g("SMART_MONEY_ENABLED"), True)
    SMART_MONEY_MIN_ROI_PCT: float = _float(g("SMART_MONEY_MIN_ROI_PCT"), 200.0)
    SMART_MONEY_MIN_WIN_RATE: float = _float(g("SMART_MONEY_MIN_WIN_RATE"), 0.70)
    SMART_MONEY_MIN_TRADES: int = _int(g("SMART_MONEY_MIN_TRADES"), 100)
    SMART_MONEY_SCORE_BOOST: float = _float(g("SMART_MONEY_SCORE_BOOST"), 15.0)

    # === Whale ===
    WHALE_TRACKING_ENABLED: bool = _bool(g("WHALE_TRACKING_ENABLED"), True)
    WHALE_THRESHOLDS_USD: str = g("WHALE_THRESHOLDS_USD", "100000,250000,500000,1000000")
    WHALE_BUY_SCORE_BOOST: float = _float(g("WHALE_BUY_SCORE_BOOST"), 10.0)
    WHALE_SELL_SCORE_PENALTY: float = _float(g("WHALE_SELL_SCORE_PENALTY"), 12.0)

    # === Social ===
    SOCIAL_INTELLIGENCE_ENABLED: bool = _bool(g("SOCIAL_INTELLIGENCE_ENABLED"), False)
    SOCIAL_API_TIMEOUT_SEC: float = _float(g("SOCIAL_API_TIMEOUT_SEC"), 5.0)
    SOCIAL_CACHE_TTL_MIN: float = _float(g("SOCIAL_CACHE_TTL_MIN"), 30.0)
    SOCIAL_MAX_CALLS_PER_DAY: int = _int(g("SOCIAL_MAX_CALLS_PER_DAY"), 150)
    SOCIAL_MIN_MENTIONS_FOR_SIGNAL: int = _int(g("SOCIAL_MIN_MENTIONS_FOR_SIGNAL"), 3)
    SOCIAL_INFLUENCER_FOLLOWER_THRESHOLD: int = _int(g("SOCIAL_INFLUENCER_FOLLOWER_THRESHOLD"), 20000)

    # === MEV ===
    MEV_PROTECTION_ENABLED: bool = _bool(g("MEV_PROTECTION_ENABLED"), True)
    MEV_MAX_SLIPPAGE_BPS: int = _int(g("MEV_MAX_SLIPPAGE_BPS"), 500)
    MEV_SANDWICH_RISK_THRESHOLD: float = _float(g("MEV_SANDWICH_RISK_THRESHOLD"), 0.7)
    MEV_DYNAMIC_SLIPPAGE: bool = _bool(g("MEV_DYNAMIC_SLIPPAGE"), True)
    MEV_RETRY_ATTEMPTS: int = _int(g("MEV_RETRY_ATTEMPTS"), 3)

    # === Blacklist ===
    AUTO_BLACKLIST_ENABLED: bool = _bool(g("AUTO_BLACKLIST_ENABLED"), True)
    BLACKLIST_HONEYPOT: bool = _bool(g("BLACKLIST_HONEYPOT"), True)
    BLACKLIST_RUG_PULL: bool = _bool(g("BLACKLIST_RUG_PULL"), True)
    BLACKLIST_FAKE_VOLUME: bool = _bool(g("BLACKLIST_FAKE_VOLUME"), True)
    BLACKLIST_MALICIOUS: bool = _bool(g("BLACKLIST_MALICIOUS"), True)

    # === Advanced Risk ===
    EMERGENCY_STOP: bool = _bool(g("EMERGENCY_STOP"), False)
    AUTO_PAUSE_ON_ERROR: bool = _bool(g("AUTO_PAUSE_ON_ERROR"), True)
    MAX_DRAWDOWN_PCT: float = _float(g("MAX_DRAWDOWN_PCT"), 0.25)

    # === Portfolio ===
    PORTFOLIO_MAX_SECTOR_PCT: float = _float(g("PORTFOLIO_MAX_SECTOR_PCT"), 0.40)
    PORTFOLIO_DIVERSIFICATION_MIN: int = _int(g("PORTFOLIO_DIVERSIFICATION_MIN"), 3)
    MAX_TOKEN_ALLOCATION_PCT: float = _float(g("MAX_TOKEN_ALLOCATION_PCT"), 0.25)
    POSITION_RISK_PCT: float = _float(g("POSITION_RISK_PCT"), 0.02)

    # === Notifications ===
    NOTIFY_TELEGRAM: bool = _bool(g("NOTIFY_TELEGRAM"), True)
    NOTIFY_DISCORD: bool = _bool(g("NOTIFY_DISCORD"), False)
    NOTIFY_EMAIL: bool = _bool(g("NOTIFY_EMAIL"), False)
    NOTIFY_ON_BUY: bool = _bool(g("NOTIFY_ON_BUY"), True)
    NOTIFY_ON_SELL: bool = _bool(g("NOTIFY_ON_SELL"), True)
    NOTIFY_ON_AI_SIGNAL: bool = _bool(g("NOTIFY_ON_AI_SIGNAL"), True)
    NOTIFY_ON_WHALE: bool = _bool(g("NOTIFY_ON_WHALE"), True)
    NOTIFY_ON_ERROR: bool = _bool(g("NOTIFY_ON_ERROR"), True)

    # === Monitoring ===
    POSITION_MONITOR_INTERVAL_SEC: int = _int(g("POSITION_MONITOR_INTERVAL_SEC"), 15)
    SCANNER_INTERVAL_SEC: int = _int(g("SCANNER_INTERVAL_SEC"), 60)
    RPC_HEALTH_CHECK_INTERVAL_SEC: int = _int(g("RPC_HEALTH_CHECK_INTERVAL_SEC"), 60)
    API_LATENCY_THRESHOLD_MS: int = _int(g("API_LATENCY_THRESHOLD_MS"), 2000)
    AUTO_RECOVERY_ENABLED: bool = _bool(g("AUTO_RECOVERY_ENABLED"), True)

    # === Backtest ===
    BACKTEST_DEFAULT_DAYS: int = _int(g("BACKTEST_DEFAULT_DAYS"), 30)

    # === DB & Redis ===
    DATABASE_URL: str = g("DATABASE_URL", "sqlite+aiosqlite:///./data/memebot.db")
    REDIS_URL: str = g("REDIS_URL", "redis://localhost:6379/0")

    # === Admin ===
    ADMIN_API_HOST: str = g("ADMIN_API_HOST", "0.0.0.0")
    ADMIN_API_PORT: int = _int(g("ADMIN_API_PORT"), 8080)
    ADMIN_API_KEY: str = g("ADMIN_API_KEY", "change-me-in-production")
    ADMIN_USERNAME: str = g("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = g("ADMIN_PASSWORD", "admin123")
    ADMIN_SESSION_SECRET: str = g("ADMIN_SESSION_SECRET", "change-this-session-secret")

    # === Runtime (koddan o'zgartiriladi) ===
    BOT_RUNNING: bool = False

    def model_dump(self):
        return {k: getattr(self, k) for k in dir(self)
                if not k.startswith("_") and not callable(getattr(self, k))}

settings = Settings()
