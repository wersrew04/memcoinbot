"""Multi-source Solana juftlik skaneri.

Asosiy manbalar (DexScreener siz ishlaydi):
  1) GeckoTerminal — kalit kerak emas
  2) Birdeye new_listing — BIRDEYE_API_KEY bo'lsa
  3) DexScreener — faqat zaxira (429 bo'lsa o'tkazib yuboriladi)

main.py: from scanner.dexscreener import fetch_new_pairs  — o'zgarmaydi.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import aiohttp

from config.settings import settings
from utils.helpers import safe_float, utc_now
from utils.logger import logger

# ── URLs ──
GECKO_NEW = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"
GECKO_TRENDING = "https://api.geckoterminal.com/api/v2/networks/solana/trending_pools"
BIRDEYE_NEW = "https://public-api.birdeye.so/defi/v2/tokens/new_listing"
BIRDEYE_TRENDING = "https://public-api.birdeye.so/defi/token_trending"
DS_SEARCH = "https://api.dexscreener.com/latest/dex/search"

_TIMEOUT = aiohttp.ClientTimeout(total=18, sock_connect=8, sock_read=14)

_cache: List[Dict] = []
_cache_ts: float = 0.0
_ds_backoff: float = 0.0


def _save_cache(pairs: List[Dict]) -> None:
    global _cache, _cache_ts
    if pairs:
        _cache = list(pairs)
        _cache_ts = time.time()


def _load_cache(max_age: float = 300.0) -> List[Dict]:
    if _cache and (time.time() - _cache_ts) < max_age:
        return list(_cache)
    return []


async def fetch_new_pairs(
    session: aiohttp.ClientSession,
    min_liquidity: float = 10000,
) -> List[Dict]:
    """Gecko + Birdeye (+ ixtiyoriy DexScreener) dan juftlik yig'adi."""
    results: List[Dict] = []
    seen: Set[str] = set()

    def _add(item: Optional[Dict]) -> None:
        if not item:
            return
        tok = item.get("token") or ""
        if not tok or len(tok) < 32 or tok in seen:
            return
        if safe_float(item.get("liquidity_usd")) < min_liquidity:
            return
        seen.add(tok)
        results.append(item)

    # 1) GeckoTerminal (asosiy, kalit yo'q)
    for p in await _from_gecko(session):
        _add(p)

    # 2) Birdeye (kalit bo'lsa)
    if getattr(settings, "BIRDEYE_API_KEY", ""):
        for p in await _from_birdeye(session):
            _add(p)

    # 3) DexScreener — faqat kam natija va backoff yo'q bo'lsa
    if len(results) < 5 and time.time() >= _ds_backoff:
        for p in await _from_dexscreener(session):
            _add(p)

    if results:
        results.sort(key=lambda x: x.get("token_age_minutes", 9999))
        _save_cache(results)
        sources = {}
        for r in results:
            sources[r.get("source", "?")] = sources.get(r.get("source", "?"), 0) + 1
        logger.info(
            "[SCAN] %s ta juftlik | %s",
            len(results),
            ", ".join(f"{k}={v}" for k, v in sources.items()),
        )
        return results

    cached = _load_cache()
    if cached:
        logger.warning("[SCAN] yangi yo'q — cache %s ta", len(cached))
        return cached

    logger.warning(
        "[SCAN] Hech qanday juftlik topilmadi "
        "(Gecko/Birdeye javob bermadi. BIRDEYE_API_KEY bormi?)"
    )
    return []


# ─────────────────────────────────────────────
# GeckoTerminal
# ─────────────────────────────────────────────

async def _from_gecko(session: aiohttp.ClientSession) -> List[Dict]:
    out: List[Dict] = []
    headers = {"Accept": "application/json"}
    for url in (GECKO_NEW, GECKO_TRENDING):
        try:
            async with session.get(
                url, params={"page": 1}, headers=headers, timeout=_TIMEOUT
            ) as resp:
                if resp.status == 429:
                    logger.warning("[SCAN] GeckoTerminal 429")
                    continue
                if resp.status != 200:
                    logger.debug("[SCAN] gecko HTTP %s", resp.status)
                    continue
                data = await resp.json(content_type=None)
                items = data.get("data") if isinstance(data, dict) else None
                if not isinstance(items, list):
                    continue
                for it in items:
                    n = _norm_gecko(it)
                    if n:
                        out.append(n)
        except asyncio.TimeoutError:
            logger.warning("[SCAN] gecko timeout")
        except Exception as e:
            logger.warning("[SCAN] gecko xato: %s", type(e).__name__)
    if out:
        logger.info("[SCAN] GeckoTerminal: %s ta", len(out))
    return out


def _norm_gecko(item: Dict) -> Optional[Dict]:
    if not isinstance(item, dict):
        return None
    attr = item.get("attributes") or {}
    rel = item.get("relationships") or {}

    base_id = ((rel.get("base_token") or {}).get("data") or {}).get("id") or ""
    token = base_id.split("_", 1)[-1] if isinstance(base_id, str) and "_" in base_id else ""
    if not token or len(token) < 32:
        return None

    # Quote SOL/USDC bo'lsin
    quote_id = ((rel.get("quote_token") or {}).get("data") or {}).get("id") or ""
    # solana_So111... = WSOL
    liq = safe_float(attr.get("reserve_in_usd"))
    name = attr.get("name") or "?"
    symbol = name.split("/")[0].strip() if "/" in str(name) else str(name)[:16]

    age_minutes = 0.0
    created = attr.get("pool_created_at") or ""
    if created:
        try:
            dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            age_minutes = (utc_now() - dt).total_seconds() / 60
        except Exception:
            pass

    vol_h24 = attr.get("volume_usd")
    if isinstance(vol_h24, dict):
        vol_h24 = vol_h24.get("h24")
    pc = attr.get("price_change_percentage")
    pc_h1 = pc.get("h1") if isinstance(pc, dict) else 0

    return {
        "token": token,
        "symbol": symbol,
        "name": name,
        "pair_address": attr.get("address") or "",
        "price_usd": safe_float(attr.get("base_token_price_usd")),
        "liquidity_usd": liq,
        "volume_5m": 0.0,
        "volume_1h": safe_float(attr.get("volume_usd_h1")),
        "volume_24h": safe_float(vol_h24),
        "price_change_5m": 0.0,
        "price_change_1h": safe_float(pc_h1),
        "market_cap": safe_float(attr.get("market_cap_usd") or attr.get("fdv_usd")),
        "fdv": safe_float(attr.get("fdv_usd")),
        "buy_sell_ratio": 1.0,
        "token_age_minutes": age_minutes,
        "dex_id": attr.get("dex_id") or "gecko",
        "url": "",
        "source": "geckoterminal",
    }


# ─────────────────────────────────────────────
# Birdeye
# ─────────────────────────────────────────────

async def _from_birdeye(session: aiohttp.ClientSession) -> List[Dict]:
    key = getattr(settings, "BIRDEYE_API_KEY", "") or ""
    if not key:
        return []
    headers = {"X-API-KEY": key, "x-chain": "solana", "Accept": "application/json"}
    out: List[Dict] = []

    # New listings (meme platform)
    try:
        async with session.get(
            BIRDEYE_NEW,
            params={"limit": 20, "meme_platform_enabled": "true"},
            headers=headers,
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                items = (data.get("data") or {}).get("items") if isinstance(data, dict) else None
                if items is None and isinstance(data, dict):
                    items = data.get("data") if isinstance(data.get("data"), list) else None
                if isinstance(items, list):
                    for it in items:
                        n = _norm_birdeye(it, source="birdeye_new")
                        if n:
                            out.append(n)
            else:
                logger.debug("[SCAN] birdeye new_listing HTTP %s", resp.status)
    except Exception as e:
        logger.warning("[SCAN] birdeye new xato: %s", type(e).__name__)

    # Trending
    try:
        async with session.get(
            BIRDEYE_TRENDING,
            params={"sort_by": "rank", "sort_type": "asc", "offset": 0, "limit": 20},
            headers=headers,
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                items = (data.get("data") or {}).get("tokens") if isinstance(data, dict) else None
                if items is None and isinstance(data, dict):
                    d = data.get("data")
                    if isinstance(d, list):
                        items = d
                    elif isinstance(d, dict):
                        items = d.get("tokens") or d.get("items")
                if isinstance(items, list):
                    for it in items:
                        n = _norm_birdeye(it, source="birdeye_trend")
                        if n:
                            out.append(n)
            else:
                logger.debug("[SCAN] birdeye trending HTTP %s", resp.status)
    except Exception as e:
        logger.warning("[SCAN] birdeye trend xato: %s", type(e).__name__)

    if out:
        logger.info("[SCAN] Birdeye: %s ta", len(out))
    return out


def _norm_birdeye(it: Dict, source: str) -> Optional[Dict]:
    if not isinstance(it, dict):
        return None
    token = it.get("address") or it.get("tokenAddress") or it.get("mint") or ""
    if not token or len(token) < 32:
        return None

    liq = safe_float(
        it.get("liquidity")
        or it.get("liquidityUsd")
        or it.get("liq")
        or (it.get("liquidity") or {}).get("usd") if isinstance(it.get("liquidity"), dict) else 0
    )
    # Ba'zi new_listing da liquidity yo'q — 0 qoldiramiz, keyin min filter kesadi
    # Lekin yangi tokenlar uchun pastroq threshold foydali; shu yerda 0 ruxsat
    age_minutes = 0.0
    for key in ("liquidityAddedAt", "createdAt", "listingTime", "blockTime"):
        val = it.get(key)
        if not val:
            continue
        try:
            if isinstance(val, (int, float)) and val > 1e12:
                age_minutes = (utc_now().timestamp() - val / 1000) / 60
                break
            if isinstance(val, (int, float)) and val > 1e9:
                age_minutes = (utc_now().timestamp() - val) / 60
                break
        except Exception:
            pass

    return {
        "token": token,
        "symbol": it.get("symbol") or "?",
        "name": it.get("name") or it.get("symbol") or "?",
        "pair_address": it.get("pairAddress") or "",
        "price_usd": safe_float(it.get("price") or it.get("priceUsd") or it.get("value")),
        "liquidity_usd": liq,
        "volume_5m": safe_float(it.get("v5mUSD") or it.get("volume5m")),
        "volume_1h": safe_float(it.get("v1hUSD") or it.get("volume1h")),
        "volume_24h": safe_float(it.get("v24hUSD") or it.get("volume24h") or it.get("volume")),
        "price_change_5m": safe_float(it.get("priceChange5mPercent")),
        "price_change_1h": safe_float(it.get("priceChange1hPercent") or it.get("priceChange24hPercent")),
        "market_cap": safe_float(it.get("mc") or it.get("marketCap")),
        "fdv": safe_float(it.get("fdv")),
        "buy_sell_ratio": 1.0,
        "token_age_minutes": age_minutes,
        "dex_id": "birdeye",
        "url": "",
        "source": source,
    }


# ─────────────────────────────────────────────
# DexScreener (zaxira)
# ─────────────────────────────────────────────

async def _from_dexscreener(session: aiohttp.ClientSession) -> List[Dict]:
    global _ds_backoff
    out: List[Dict] = []
    try:
        async with session.get(
            DS_SEARCH, params={"q": "pump"}, timeout=_TIMEOUT
        ) as resp:
            if resp.status == 429:
                _ds_backoff = time.time() + 120
                logger.warning("[SCAN] DexScreener 429 — 2 daqiqa o'tkazib yuboriladi")
                return []
            if resp.status != 200:
                return []
            data = await resp.json(content_type=None)
            pairs = data.get("pairs") if isinstance(data, dict) else data
            if not isinstance(pairs, list):
                return []
            for p in pairs:
                n = _norm_ds(p)
                if n:
                    out.append(n)
    except Exception as e:
        logger.debug("[SCAN] ds zaxira xato: %s", type(e).__name__)
    if out:
        logger.info("[SCAN] DexScreener zaxira: %s ta", len(out))
    return out


def _norm_ds(pair: Dict) -> Optional[Dict]:
    if not isinstance(pair, dict) or pair.get("chainId") != "solana":
        return None
    tok = (pair.get("baseToken") or {}).get("address") or ""
    if not tok or len(tok) < 32:
        return None
    quote = ((pair.get("quoteToken") or {}).get("symbol") or "").upper()
    if quote not in ("SOL", "WSOL", "USDC", "USDT", ""):
        return None
    created = pair.get("pairCreatedAt") or 0
    age = 0.0
    if created:
        try:
            age = (utc_now().timestamp() * 1000 - created) / 60000
        except Exception:
            pass
    pc = pair.get("priceChange") or {}
    vol = pair.get("volume") or {}
    return {
        "token": tok,
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
        "buy_sell_ratio": 1.0,
        "token_age_minutes": age,
        "dex_id": pair.get("dexId", ""),
        "url": pair.get("url", ""),
        "source": "dexscreener",
    }


# admin/telegram uchun (eski import)
def _normalize_pair(pair: Dict) -> Dict:
    n = _norm_ds(pair)
    if n:
        return n
    return {
        "token": (pair.get("baseToken") or {}).get("address", ""),
        "symbol": (pair.get("baseToken") or {}).get("symbol", "?"),
        "name": (pair.get("baseToken") or {}).get("name", ""),
        "pair_address": pair.get("pairAddress", ""),
        "price_usd": safe_float(pair.get("priceUsd")),
        "liquidity_usd": safe_float((pair.get("liquidity") or {}).get("usd")),
        "volume_5m": 0.0,
        "volume_1h": 0.0,
        "volume_24h": 0.0,
        "price_change_5m": 0.0,
        "price_change_1h": 0.0,
        "market_cap": 0.0,
        "fdv": 0.0,
        "buy_sell_ratio": 1.0,
        "token_age_minutes": 0.0,
        "dex_id": pair.get("dexId", ""),
        "url": pair.get("url", ""),
        "source": "dexscreener",
    }
