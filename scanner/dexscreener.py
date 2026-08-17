"""DexScreener API — yangi Solana juftliklarini skanerlash."""
from __future__ import annotations
import aiohttp
from typing import Any, Dict, List, Set
from utils.logger import logger
from utils.helpers import utc_now, safe_float


# Eng so'nggi token profillari va boostlar
TOKEN_PROFILES_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
TOKEN_BOOSTS_URL = "https://api.dexscreener.com/token-boosts/latest/v1"
TOKEN_BOOSTS_TOP_URL = "https://api.dexscreener.com/token-boosts/top/v1"
# Token bo'yicha juftliklar
TOKENS_URL = "https://api.dexscreener.com/tokens/v1/solana/{addresses}"
# Qidiruv
SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"


async def fetch_new_pairs(
    session: aiohttp.ClientSession,
    min_liquidity: float = 10000,
) -> List[Dict]:
    """
    Yangi / faol Solana tokenlarini bir necha manbadan yig'adi.
    Eski kod WSOL juftliklarini qaytarardi — shuning uchun doim 29 ta bir xil juftlik kelardi.
    """
    token_addresses: List[str] = []
    seen: Set[str] = set()

    # 1) Latest token profiles
    for addr in await _fetch_profile_tokens(session, TOKEN_PROFILES_URL):
        if addr not in seen:
            seen.add(addr)
            token_addresses.append(addr)

    # 2) Latest boosts
    for addr in await _fetch_profile_tokens(session, TOKEN_BOOSTS_URL):
        if addr not in seen:
            seen.add(addr)
            token_addresses.append(addr)

    # 3) Top boosts
    for addr in await _fetch_profile_tokens(session, TOKEN_BOOSTS_TOP_URL):
        if addr not in seen:
            seen.add(addr)
            token_addresses.append(addr)

    # 4) Qidiruv orqali qo'shimcha (pump / solana faol juftliklar)
    for addr in await _fetch_search_tokens(session):
        if addr not in seen:
            seen.add(addr)
            token_addresses.append(addr)

    if not token_addresses:
        logger.warning("[SCAN] Hech qanday token topilmadi")
        return []

    # Token addresslar bo'yicha juftlik ma'lumotlarini olish (30 tadan)
    results: List[Dict] = []
    for i in range(0, min(len(token_addresses), 90), 30):
        batch = token_addresses[i : i + 30]
        pairs = await _fetch_token_pairs(session, batch, min_liquidity)
        results.extend(pairs)

    # Eng yangilarini oldinga qo'yish
    results.sort(key=lambda x: x.get("token_age_minutes", 9999))
    return results


async def _fetch_profile_tokens(session: aiohttp.ClientSession, url: str) -> List[str]:
    """token-profiles / token-boosts dan solana addresslarini olish."""
    out: List[str] = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return out
            data = await resp.json()
            if not isinstance(data, list):
                return out
            for item in data:
                if not isinstance(item, dict):
                    continue
                if item.get("chainId") != "solana":
                    continue
                addr = item.get("tokenAddress") or ""
                if addr and len(addr) >= 32:
                    out.append(addr)
    except Exception as e:
        logger.debug(f"Profile fetch xato ({url}): {e}")
    return out


async def _fetch_search_tokens(session: aiohttp.ClientSession) -> List[str]:
    """Qidiruv orqali faol solana juftliklaridan token address olish."""
    out: List[str] = []
    queries = ["pump", "sol", "meme"]
    try:
        for q in queries:
            async with session.get(
                SEARCH_URL,
                params={"q": q},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json()
                pairs = data.get("pairs") or []
                for pair in pairs:
                    if pair.get("chainId") != "solana":
                        continue
                    # Juda eski juftliklarni tashlab ketamiz (24 soatdan oshsa)
                    created = pair.get("pairCreatedAt") or 0
                    if created:
                        age_h = (utc_now().timestamp() * 1000 - created) / 3_600_000
                        if age_h > 24:
                            continue
                    addr = (pair.get("baseToken") or {}).get("address", "")
                    if addr and len(addr) >= 32:
                        out.append(addr)
    except Exception as e:
        logger.debug(f"Search fetch xato: {e}")
    return out


async def _fetch_token_pairs(
    session: aiohttp.ClientSession,
    addresses: List[str],
    min_liquidity: float,
) -> List[Dict]:
    """Bir nechta token address bo'yicha juftliklarni olish."""
    results: List[Dict] = []
    if not addresses:
        return results
    url = TOKENS_URL.format(addresses=",".join(addresses))
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return results
            data = await resp.json()
            # API ba'zan list, ba'zan {"pairs": [...]} qaytaradi
            pairs = data if isinstance(data, list) else (data.get("pairs") or [])
            for pair in pairs:
                if not isinstance(pair, dict):
                    continue
                if pair.get("chainId") != "solana":
                    continue
                liq = safe_float((pair.get("liquidity") or {}).get("usd"))
                if liq < min_liquidity:
                    continue
                # Quote SOL yoki USDC/USDT bo'lsin (oddiy meme juftliklar)
                quote = (pair.get("quoteToken") or {}).get("symbol", "").upper()
                if quote not in ("SOL", "WSOL", "USDC", "USDT", ""):
                    continue
                results.append(_normalize_pair(pair))
    except Exception as e:
        logger.warning(f"Token pairs fetch xato: {e}")
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
    txns = (pair.get("txns") or {}).get("h1") or {}
    buys = safe_float(txns.get("buys"))
    sells = safe_float(txns.get("sells")) or 1.0

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
