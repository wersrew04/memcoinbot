"""DexScreener API — yangi Solana juftliklarini skanerlash."""
from __future__ import annotations
import asyncio
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

    # Token addresslar bo'yicha juftliklar (kichik batch — timeout kamayadi)
    results: List[Dict] = []
    batch_size = 10
    max_tokens = 60
    for i in range(0, min(len(token_addresses), max_tokens), batch_size):
        batch = token_addresses[i : i + batch_size]
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
    pairs_raw: list = []
    # sock_connect + total — Railway dan DexScreener sekin bo'lishi mumkin
    timeout = aiohttp.ClientTimeout(total=25, sock_connect=10, sock_read=20)
    try:
        async with session.get(url, timeout=timeout) as resp:
            if resp.status == 429:
                logger.warning(
                    "Token pairs: rate-limit 429 (n=%s). SCANNER_INTERVAL_SEC ni oshiring.",
                    len(addresses),
                )
                return results
            if resp.status != 200:
                logger.warning(
                    "Token pairs HTTP %s (n=%s): %s",
                    resp.status,
                    len(addresses),
                    resp.reason,
                )
            else:
                data = await resp.json(content_type=None)
                pairs_raw = data if isinstance(data, list) else (data.get("pairs") or [])
    except asyncio.TimeoutError:
        logger.warning(
            "Token pairs timeout (n=%s) — fallback ishlatiladi",
            len(addresses),
        )
        pairs_raw = await _fetch_token_pairs_fallback(session, addresses)
    except Exception as e:
        logger.warning(
            "Token pairs xato (%s): %s — fallback",
            type(e).__name__,
            e or repr(e),
        )
        pairs_raw = await _fetch_token_pairs_fallback(session, addresses)

    for pair in pairs_raw:
        if not isinstance(pair, dict):
            continue
        if pair.get("chainId") and pair.get("chainId") != "solana":
            continue
        liq = safe_float((pair.get("liquidity") or {}).get("usd"))
        if liq < min_liquidity:
            continue
        quote = (pair.get("quoteToken") or {}).get("symbol", "").upper()
        if quote not in ("SOL", "WSOL", "USDC", "USDT", ""):
            continue
        results.append(_normalize_pair(pair))
    return results


async def _fetch_token_pairs_fallback(
    session: aiohttp.ClientSession,
    addresses: List[str],
) -> list:
    """Eski /latest/dex/tokens/{addr} — asosiy API timeout/xato bo'lsa."""
    out: list = []
    timeout = aiohttp.ClientTimeout(total=10, sock_connect=5, sock_read=8)

    async def _one(addr: str) -> list:
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{addr}"
            async with session.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
                pairs = data.get("pairs") if isinstance(data, dict) else data
                return pairs if isinstance(pairs, list) else []
        except Exception:
            return []

    # Parallel, lekin 5 tadan (rate-limit)
    for i in range(0, len(addresses), 5):
        chunk = addresses[i : i + 5]
        parts = await asyncio.gather(*[_one(a) for a in chunk])
        for p in parts:
            out.extend(p)
    return out


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
