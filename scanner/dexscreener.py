"""DexScreener API — yangi Solana juftliklarini skanerlash.

Eslatma: /tokens/v1/solana/{addr1,addr2,...} batch endpoint tez-tez
timeout yoki HTTP 500 beradi. Shu sabab faqat ishonchli manbalar:
  - /latest/dex/search
  - /latest/dex/tokens/{single}
  - token-profiles / token-boosts (faqat address ro'yxati)
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Set

import aiohttp

from utils.helpers import safe_float, utc_now
from utils.logger import logger

TOKEN_PROFILES_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
TOKEN_BOOSTS_URL = "https://api.dexscreener.com/token-boosts/latest/v1"
TOKEN_BOOSTS_TOP_URL = "https://api.dexscreener.com/token-boosts/top/v1"
SEARCH_URL = "https://api.dexscreener.com/latest/dex/search"
SINGLE_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/{address}"

# Umumiy timeout (Railway dan DexScreener sekin bo'lishi mumkin)
_TIMEOUT = aiohttp.ClientTimeout(total=18, sock_connect=8, sock_read=14)


async def fetch_new_pairs(
    session: aiohttp.ClientSession,
    min_liquidity: float = 10000,
) -> List[Dict]:
    """Yangi / faol Solana juftliklarini yig'adi."""
    results: List[Dict] = []
    seen: Set[str] = set()

    def _accept(pair: Dict) -> None:
        if not isinstance(pair, dict):
            return
        chain = pair.get("chainId") or ""
        if chain and chain != "solana":
            return
        liq = safe_float((pair.get("liquidity") or {}).get("usd"))
        if liq < min_liquidity:
            return
        quote = ((pair.get("quoteToken") or {}).get("symbol") or "").upper()
        if quote not in ("SOL", "WSOL", "USDC", "USDT", ""):
            return
        tok = (pair.get("baseToken") or {}).get("address") or ""
        if not tok or len(tok) < 32 or tok in seen:
            return
        # Juda eski juftliklar (7 kundan oshsa) — skip
        created = pair.get("pairCreatedAt") or 0
        if created:
            age_h = (utc_now().timestamp() * 1000 - created) / 3_600_000
            if age_h > 168:
                return
        seen.add(tok)
        results.append(_normalize_pair(pair))

    # ── 1) Search (to'liq pair data, eng ishonchli) ──
    for pair in await _search_pairs(session):
        _accept(pair)

    # ── 2) Profiles / boosts → alohida token lookup ──
    addrs: List[str] = []
    for url in (TOKEN_PROFILES_URL, TOKEN_BOOSTS_URL, TOKEN_BOOSTS_TOP_URL):
        for a in await _profile_addresses(session, url):
            if a not in seen and a not in addrs:
                addrs.append(a)

    if addrs:
        for pair in await _lookup_tokens(session, addrs[:25]):
            _accept(pair)

    if not results:
        logger.warning("[SCAN] Hech qanday juftlik topilmadi")
        return []

    results.sort(key=lambda x: x.get("token_age_minutes", 9999))
    logger.info("[SCAN] DexScreener: %s ta juftlik", len(results))
    return results


async def _search_pairs(session: aiohttp.ClientSession) -> List[Dict]:
    out: List[Dict] = []
    queries = ("pump", "solana", "meme", "bonk", "raydium")
    for q in queries:
        try:
            async with session.get(
                SEARCH_URL,
                params={"q": q},
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status == 429:
                    logger.warning("[SCAN] search 429 q=%s — kutish", q)
                    await asyncio.sleep(2)
                    continue
                if resp.status != 200:
                    logger.debug("[SCAN] search HTTP %s q=%s", resp.status, q)
                    continue
                data = await resp.json(content_type=None)
                pairs = data.get("pairs") if isinstance(data, dict) else data
                if isinstance(pairs, list):
                    out.extend(p for p in pairs if isinstance(p, dict))
        except asyncio.TimeoutError:
            logger.debug("[SCAN] search timeout q=%s", q)
        except Exception as e:
            logger.debug("[SCAN] search xato q=%s: %s", q, type(e).__name__)
        await asyncio.sleep(0.15)
    return out


async def _profile_addresses(session: aiohttp.ClientSession, url: str) -> List[str]:
    out: List[str] = []
    try:
        async with session.get(url, timeout=_TIMEOUT) as resp:
            if resp.status != 200:
                return out
            data = await resp.json(content_type=None)
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
    except Exception:
        pass
    return out


async def _lookup_tokens(
    session: aiohttp.ClientSession,
    addresses: List[str],
) -> List[Dict]:
    """Har bir token uchun /latest/dex/tokens/{addr} — barqaror."""
    out: List[Dict] = []
    if not addresses:
        return out

    async def _one(addr: str) -> List[Dict]:
        try:
            url = SINGLE_TOKEN_URL.format(address=addr)
            async with session.get(url, timeout=_TIMEOUT) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json(content_type=None)
                pairs = data.get("pairs") if isinstance(data, dict) else data
                return [p for p in pairs if isinstance(p, dict)] if isinstance(pairs, list) else []
        except Exception:
            return []

    for i in range(0, len(addresses), 4):
        chunk = addresses[i : i + 4]
        parts = await asyncio.gather(*[_one(a) for a in chunk])
        for plist in parts:
            out.extend(plist)
        await asyncio.sleep(0.1)
    return out


def _normalize_pair(pair: Dict) -> Dict:
    from datetime import datetime, timezone

    created_at = pair.get("pairCreatedAt") or 0
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
