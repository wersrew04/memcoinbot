"""Birdeye API – token overview, security, holders, price."""
from __future__ import annotations

import httpx
import time
import asyncio
from typing import Any, Dict, List, Optional
from utils.logger import logger
from utils.retry import async_retry
from utils.helpers import safe_float, safe_int
from config.settings import settings
from config.constants import (
    BIRDEYE_TOKEN_OVERVIEW,
    BIRDEYE_TOKEN_SECURITY,
    BIRDEYE_TOKEN_HOLDERS,
    BIRDEYE_PRICE,
)


class BirdeyeClient:
    def __init__(self, api_key: Optional[str] = None, timeout: float = 20.0):
        self.api_key = api_key or settings.BIRDEYE_API_KEY
        self.timeout = timeout
        self.headers = {
            "Accept": "application/json",
            "x-chain": "solana",
        }
        if self.api_key:
            self.headers["X-API-KEY"] = self.api_key
        self._overview_cache = {}
        self._price_cache = {}
        self._cache_ttl = 300
        self._client = httpx.AsyncClient(timeout=self.timeout, headers=self.headers)
        self._semaphore = asyncio.Semaphore(5)
        self._security_unavailable = False  # True once we learn the plan can't access /token_security

    @async_retry(max_attempts=3)
    async def get_token_overview(self, address: str) -> Optional[Dict[str, Any]]:
        now = time.time()
        cached = self._overview_cache.get(address)
        if cached and cached["expires"] > now:
            return cached["data"]

        async with self._semaphore:
            for delay in (1,2,4):
                resp = await self._client.get(BIRDEYE_TOKEN_OVERVIEW, params={"address": address})
                if resp.status_code == 404:
                    return None
                if resp.status_code == 429:
                    logger.warning(f"BirdEye rate limit: {address}; retry in {delay}s")
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                break
            else:
                return None
            data = resp.json()
            if not data.get("success"):
                return None
            result=data.get("data")
            self._overview_cache[address]={"data":result,"expires":now+self._cache_ttl}
            return result

    async def get_token_security(self, address: str) -> Optional[Dict[str, Any]]:
        """Mint/freeze authority, honeypot flags va boshqa xavfsizlik.

        Ba'zi Birdeye tariflarida (Starter/bepul) bu endpoint yopiq bo'ladi
        (401/403 "lacks sufficient permissions"). Bunday holatda qayta-qayta
        urinish foydasiz (ruxsat qayta yozilmaguncha o'zgarmaydi), shuning
        uchun buni bir marta aniqlab, keyingi chaqiruvlarda darhol None
        qaytaramiz - vaqt va so'rov limitini tejash uchun.
        """
        if self._security_unavailable:
            return None
        try:
            resp = await self._client.get(BIRDEYE_TOKEN_SECURITY, params={"address": address})
        except (httpx.HTTPError, httpx.TimeoutException, ConnectionError) as e:
            logger.debug(f"Birdeye security so'rov xatosi {address}: {e}")
            return None

        if resp.status_code in (401, 403):
            self._security_unavailable = True
            logger.warning(
                "Birdeye /token_security ushbu API kalit/tarif uchun yopiq "
                "(401/403 - 'lacks sufficient permissions'). Mint/freeze "
                "authority va honeypot tekshiruvlari SHU SESSIYADA o'chiriladi. "
                "To'liq xavfsizlik tekshiruvi uchun Birdeye tarifini "
                "yangilash kerak (Standard/Business)."
            )
            return None
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logger.debug(f"Birdeye security kutilmagan status {resp.status_code}: {address}")
            return None

        data = resp.json()
        return data.get("data") if data.get("success") else None

    @async_retry(max_attempts=3)
    async def get_token_holders(self, address: str, limit: int = 20) -> List[Dict[str, Any]]:
        resp = await self._client.get(
            BIRDEYE_TOKEN_HOLDERS,
            params={"address": address, "offset": 0, "limit": limit},
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = (data.get("data") or {}).get("items") or []
        return items

    @async_retry(max_attempts=3)
    async def get_price(self, address: str) -> Optional[float]:
        now = time.time()
        cached = self._price_cache.get(address)
        if cached and cached["expires"] > now:
            return cached["data"]
        resp = await self._client.get(BIRDEYE_PRICE, params={"address": address})
        if resp.status_code in (404, 429):
            return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("success"):
            price = safe_float((data.get("data") or {}).get("value"))
            self._price_cache[address] = {"data": price, "expires": now + 30}
            return price
        return None

    async def close(self):
        """HTTP client ulanishini yopish (shutdown paytida chaqirish kerak)."""
        try:
            await self._client.aclose()
        except Exception:
            pass

    def normalize_security(self, sec: Dict[str, Any]) -> Dict[str, Any]:
        """Security ma'lumotini soddalashtirish."""
        if not sec:
            return {}
        return {
            "owner_address": sec.get("ownerAddress"),
            "creator_address": sec.get("creatorAddress"),
            "mint_authority": sec.get("mintAuthority"),
            "freeze_authority": sec.get("freezeAuthority"),
            "is_mutable": sec.get("isMutable"),
            "is_mintable": bool(sec.get("mintAuthority")),
            "is_freezable": bool(sec.get("freezeAuthority")),
            "top10_holder_pct": safe_float(sec.get("top10HolderPercent")),
            "top10_user_pct": safe_float(sec.get("top10UserPercent")),
            "owner_pct": safe_float(sec.get("ownerPercentage")),
            "creator_pct": safe_float(sec.get("creatorPercentage")),
            "holder_count": safe_int(sec.get("holder")),
            "lp_holder_count": safe_int(sec.get("lpHolderCount")),
            "is_honeypot": sec.get("isHoneypot") or sec.get("honeypot"),
            "raw": sec,
        }

    def normalize_overview(self, ov: Dict[str, Any]) -> Dict[str, Any]:
        if not ov:
            return {}
        return {
            "address": ov.get("address"),
            "name": ov.get("name"),
            "symbol": ov.get("symbol"),
            "decimals": safe_int(ov.get("decimals")),
            "price": safe_float(ov.get("price")),
            "liquidity": safe_float(ov.get("liquidity")),
            "mc": safe_float(ov.get("mc") or ov.get("marketCap")),
            "v24h_usd": safe_float(ov.get("v24hUSD")),
            "v24h_change_pct": safe_float(ov.get("v24hChangePercent")),
            "holder": safe_int(ov.get("holder")),
            "number_markets": safe_int(ov.get("numberMarkets")),
            "raw": ov,
        }
