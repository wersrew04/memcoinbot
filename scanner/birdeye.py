"""Birdeye API — token xavfsizligi va holderlarini tekshirish."""
from __future__ import annotations
import aiohttp
from typing import Any, Dict, Optional
from utils.logger import logger
from utils.helpers import safe_float, safe_int
from config.settings import settings


BASE = "https://public-api.birdeye.so"
HEADERS = {"X-API-KEY": settings.BIRDEYE_API_KEY, "x-chain": "solana"}


async def get_token_security(session: aiohttp.ClientSession, token: str) -> Dict:
    """Token xavfsizligi ma'lumotlari."""
    if not settings.BIRDEYE_API_KEY:
        return {}
    try:
        url = f"{BASE}/defi/token_security?address={token}"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return {}
            data = await r.json()
            return data.get("data") or {}
    except Exception as e:
        logger.debug(f"Birdeye security xato {token[:8]}: {e}")
        return {}


async def get_token_overview(session: aiohttp.ClientSession, token: str) -> Dict:
    """Token umumiy ma'lumotlari."""
    if not settings.BIRDEYE_API_KEY:
        return {}
    try:
        url = f"{BASE}/defi/token_overview?address={token}"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                return {}
            data = await r.json()
            return data.get("data") or {}
    except Exception as e:
        logger.debug(f"Birdeye overview xato {token[:8]}: {e}")
        return {}
