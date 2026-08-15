"""DexScreener scanner – yangi juftliklar va token ma'lumotlari."""
from __future__ import annotations

import httpx
from typing import Any, Dict, List, Optional
from utils.logger import logger
from utils.retry import async_retry
from utils.helpers import safe_float, safe_int
from config.constants import (
    DEXSCREENER_TOKEN_PROFILES,
    DEXSCREENER_SEARCH,
    DEXSCREENER_PAIRS,
    DEXSCREENER_TOKEN_PAIRS,
)


class DexScreenerClient:
    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout
        self.headers = {"Accept": "application/json", "User-Agent": "MemeBot/1.0"}

    @async_retry(max_attempts=3)
    async def get_latest_token_profiles(self) -> List[Dict[str, Any]]:
        """Eng so'nggi token profile'lar (yangi launchlar uchun foydali)."""
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(DEXSCREENER_TOKEN_PROFILES)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return []

    @async_retry(max_attempts=3)
    async def search_pairs(self, query: str = "solana") -> List[Dict[str, Any]]:
        """Qidiruv orqali juftliklar."""
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(DEXSCREENER_SEARCH, params={"q": query})
            resp.raise_for_status()
            data = resp.json()
            return data.get("pairs") or []

    @async_retry(max_attempts=3)
    async def get_pair(self, pair_address: str) -> Optional[Dict[str, Any]]:
        """Bitta juftlik ma'lumoti."""
        url = f"{DEXSCREENER_PAIRS}/{pair_address}"
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            pairs = data.get("pairs") or []
            return pairs[0] if pairs else None

    @async_retry(max_attempts=3)
    async def get_token_pairs(self, token_address: str) -> List[Dict[str, Any]]:
        """Token bo'yicha barcha juftliklar."""
        url = f"{DEXSCREENER_TOKEN_PAIRS}/{token_address}"
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("pairs") or []

    def normalize_pair(self, pair: Dict[str, Any]) -> Dict[str, Any]:
        """Juftlikni standart formatga keltirish."""
        base = pair.get("baseToken") or {}
        quote = pair.get("quoteToken") or {}
        liquidity = pair.get("liquidity") or {}
        volume = pair.get("volume") or {}
        txns = pair.get("txns") or {}
        price_change = pair.get("priceChange") or {}

        return {
            "pair_address": pair.get("pairAddress"),
            "dex_id": pair.get("dexId"),
            "url": pair.get("url"),
            "token_address": base.get("address"),
            "token_name": base.get("name"),
            "token_symbol": base.get("symbol"),
            "quote_address": quote.get("address"),
            "quote_symbol": quote.get("symbol"),
            "price_usd": safe_float(pair.get("priceUsd")),
            "price_native": safe_float(pair.get("priceNative")),
            "liquidity_usd": safe_float(liquidity.get("usd")),
            "volume_5m": safe_float(volume.get("m5")),
            "volume_1h": safe_float(volume.get("h1")),
            "volume_6h": safe_float(volume.get("h6")),
            "volume_24h": safe_float(volume.get("h24")),
            "price_change_5m": safe_float(price_change.get("m5")),
            "price_change_1h": safe_float(price_change.get("h1")),
            "price_change_6h": safe_float(price_change.get("h6")),
            "price_change_24h": safe_float(price_change.get("h24")),
            "txns_5m_buys": safe_int((txns.get("m5") or {}).get("buys")),
            "txns_5m_sells": safe_int((txns.get("m5") or {}).get("sells")),
            "txns_1h_buys": safe_int((txns.get("h1") or {}).get("buys")),
            "txns_1h_sells": safe_int((txns.get("h1") or {}).get("sells")),
            "fdv": safe_float(pair.get("fdv")),
            "market_cap": safe_float(pair.get("marketCap")),
            "pair_created_at": pair.get("pairCreatedAt"),
            "labels": pair.get("labels") or [],
            "raw": pair,
        }
