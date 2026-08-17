"""DexScreener API — yangi Solana juftliklarini skanerlash."""
from __future__ import annotations
import aiohttp
from typing import Any, Dict, List
from utils.logger import logger
from utils.helpers import utc_now, safe_float

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/pairs/solana"
NEW_PAIRS_URL = "https://api.dexscreener.com/latest/dex/search?q=solana"


async def fetch_new_pairs(session: aiohttp.ClientSession, min_liquidity: float = 10000) -> List[Dict]:
    """DexScreener dan yangi tokenlarni olish."""
    results = []
    try:
        async with session.get(
            "https://api.dexscreener.com/latest/dex/tokens/So11111111111111111111111111111111111111112",
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                return results
            data = await resp.json()
            pairs = data.get("pairs") or []
            for pair in pairs:
                if pair.get("chainId") != "solana":
                    continue
                liq = safe_float(pair.get("liquidity", {}).get("usd"))
                if liq < min_liquidity:
                    continue
                results.append(_normalize_pair(pair))
    except Exception as e:
        logger.warning(f"DexScreener xato: {e}")
    return results


def _normalize_pair(pair: Dict) -> Dict:
    from datetime import datetime, timezone
    created_at = pair.get("pairCreatedAt", 0)
    age_minutes = 0.0
    if created_at:
        try:
            created_dt = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc)
            age_minutes = (utc_now() - created_dt).total_seconds() / 60
        except Exception:
            pass
    pc = pair.get("priceChange") or {}
    vol = pair.get("volume") or {}
    txns = pair.get("txns", {}).get("h1") or {}
    buys = safe_float(txns.get("buys"))
    sells = safe_float(txns.get("sells")) or 1

    return {
        "token": (pair.get("baseToken") or {}).get("address", ""),
        "symbol": (pair.get("baseToken") or {}).get("symbol", "?"),
        "name": (pair.get("baseToken") or {}).get("name", ""),
        "pair_address": pair.get("pairAddress", ""),
        "price_usd": safe_float(pair.get("priceUsd")),
        "liquidity_usd": safe_float((pair.get("liquidity") or {}).get("usd")),
        "volume_5m": safe_float(vol.get("m5")),
        "volume_1h": safe_float(vol.get("h1")),
        "volume_24h": safe_float(vol.get("h24")),
        "price_change_5m": safe_float(pc.get("m5")),
        "price_change_1h": safe_float(pc.get("h1")),
        "market_cap": safe_float(pair.get("marketCap")),
        "fdv": safe_float(pair.get("fdv")),
        "buy_sell_ratio": buys / sells if sells > 0 else 1.0,
        "token_age_minutes": age_minutes,
        "dex_id": pair.get("dexId", ""),
        "url": pair.get("url", ""),
        "source": "dexscreener",
    }
