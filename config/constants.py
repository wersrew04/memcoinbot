SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WSOL_MINT = SOL_MINT

# DexScreener
DEXSCREENER_BASE = "https://api.dexscreener.com"
DEXSCREENER_TOKEN_PROFILES = f"{DEXSCREENER_BASE}/token-profiles/latest/v1"
DEXSCREENER_SEARCH = f"{DEXSCREENER_BASE}/latest/dex/search"
DEXSCREENER_PAIRS = f"{DEXSCREENER_BASE}/latest/dex/pairs/solana"
DEXSCREENER_TOKEN_PAIRS = f"{DEXSCREENER_BASE}/token-pairs/v1/solana"

# Birdeye
BIRDEYE_BASE = "https://public-api.birdeye.so"
BIRDEYE_TOKEN_OVERVIEW = f"{BIRDEYE_BASE}/defi/token_overview"
BIRDEYE_TOKEN_SECURITY = f"{BIRDEYE_BASE}/defi/token_security"
BIRDEYE_TOKEN_HOLDERS = f"{BIRDEYE_BASE}/defi/v3/token/holder"
BIRDEYE_PRICE = f"{BIRDEYE_BASE}/defi/price"
BIRDEYE_OHLCV = f"{BIRDEYE_BASE}/defi/ohlcv"

# Jupiter Swap API (v6)
JUPITER_QUOTE = "https://lite-api.jup.ag/swap/v1/quote"
JUPITER_SWAP = "https://lite-api.jup.ag/swap/v1/swap"
JUPITER_PRICE = "https://lite-api.jup.ag/price/v2"

# Redis keys
REDIS_DAILY_LOSS = "risk:daily_loss"
REDIS_OPEN_POSITIONS = "risk:open_positions"
REDIS_COOLDOWN_PREFIX = "cooldown:"
REDIS_BOT_STATUS = "bot:status"
REDIS_PROCESSED_TOKENS = "scanner:processed"
