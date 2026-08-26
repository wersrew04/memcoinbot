"""Birdeye API client — Solana token security/overview.

Important:
- API headers are built at request time so runtime env/admin-panel changes are respected.
- HTTP/API errors are logged instead of being silently swallowed.
- 429/5xx responses are retried with exponential backoff.
- Successful responses are cached briefly to reduce Birdeye rate-limit pressure.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional, Tuple

import aiohttp

from config.settings import settings
from utils.logger import logger


BASE = "https://public-api.birdeye.so"
_SECURITY_PATH = "/defi/token_security"
_OVERVIEW_PATH = "/defi/token_overview"

# Birdeye security is relatively expensive/rate-limited. A short cache prevents
# scanner + final scam gate from asking for the same token twice in one cycle.
_CACHE_TTL_SECONDS = 90.0
_MAX_RETRIES = 3

_security_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_overview_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _api_key() -> str:
    """Read the key at call time, not at module-import time."""
    return (getattr(settings, "BIRDEYE_API_KEY", "") or "").strip()


def _headers() -> Dict[str, str]:
    key = _api_key()
    return {
        "X-API-KEY": key,
        "x-chain": "solana",
        "accept": "application/json",
    }


def _cache_get(cache: Dict[str, Tuple[float, Dict[str, Any]]], token: str) -> Optional[Dict[str, Any]]:
    item = cache.get(token)
    if not item:
        return None
    created_at, value = item
    if time.monotonic() - created_at >= _CACHE_TTL_SECONDS:
        cache.pop(token, None)
        return None
    return dict(value)


def _cache_put(cache: Dict[str, Tuple[float, Dict[str, Any]]], token: str, value: Dict[str, Any]) -> None:
    cache[token] = (time.monotonic(), dict(value))


async def _get_json(
    session: aiohttp.ClientSession,
    path: str,
    token: str,
    label: str,
) -> Dict[str, Any]:
    """GET one Birdeye endpoint with retries and useful diagnostics."""
    key = _api_key()
    if not key:
        logger.warning("[BIRDEYE %s] API key yo'q", label)
        return {}

    url = f"{BASE}{path}"
    timeout = aiohttp.ClientTimeout(total=12)
    retryable = {429, 500, 502, 503, 504}

    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with session.get(
                url,
                params={"address": token},
                headers=_headers(),
                timeout=timeout,
            ) as response:
                # Read the body once so error responses can be diagnosed.
                raw = await response.text()

                if response.status == 200:
                    try:
                        payload = await _json_from_text(raw)
                    except Exception as exc:
                        logger.warning(
                            "[BIRDEYE %s] %s JSON parse xato: %s",
                            label,
                            token[:8],
                            exc,
                        )
                        return {}

                    if not isinstance(payload, dict):
                        logger.warning(
                            "[BIRDEYE %s] %s noto'g'ri response turi: %s",
                            label,
                            token[:8],
                            type(payload).__name__,
                        )
                        return {}

                    if payload.get("success") is False:
                        logger.warning(
                            "[BIRDEYE %s] %s HTTP 200, success=false, msg=%s",
                            label,
                            token[:8],
                            payload.get("message") or payload.get("error"),
                        )
                        return {}

                    data = payload.get("data")
                    if not isinstance(data, dict):
                        logger.warning(
                            "[BIRDEYE %s] %s HTTP 200, data bo'sh yoki dict emas",
                            label,
                            token[:8],
                        )
                        return {}

                    return data

                # Authentication / permission errors are not transient.
                if response.status in (400, 401, 403):
                    logger.error(
                        "[BIRDEYE %s] %s HTTP %s — %s",
                        label,
                        token[:8],
                        response.status,
                        _compact_error(raw),
                    )
                    return {}

                if response.status in retryable and attempt < _MAX_RETRIES:
                    retry_after = response.headers.get("Retry-After")
                    delay = _retry_delay(attempt, retry_after)
                    logger.warning(
                        "[BIRDEYE %s] %s HTTP %s — retry %d/%d %.1fs",
                        label,
                        token[:8],
                        response.status,
                        attempt + 1,
                        _MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(
                    "[BIRDEYE %s] %s HTTP %s — %s",
                    label,
                    token[:8],
                    response.status,
                    _compact_error(raw),
                )
                return {}

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            if attempt < _MAX_RETRIES:
                delay = _retry_delay(attempt, None)
                logger.warning(
                    "[BIRDEYE %s] %s request xato: %s — retry %d/%d %.1fs",
                    label,
                    token[:8],
                    type(exc).__name__,
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            logger.error(
                "[BIRDEYE %s] %s request muvaffaqiyatsiz: %s: %s",
                label,
                token[:8],
                type(exc).__name__,
                exc,
            )
            return {}
        except Exception as exc:
            logger.exception(
                "[BIRDEYE %s] %s kutilmagan xato: %s",
                label,
                token[:8],
                exc,
            )
            return {}

    return {}


async def _json_from_text(raw: str) -> Any:
    # Keep parsing independent from aiohttp response state because the body has
    # already been consumed for diagnostics.
    import json

    return json.loads(raw)


def _compact_error(raw: str, limit: int = 300) -> str:
    text = " ".join((raw or "").split())
    return text[:limit] if text else "response body bo'sh"


def _retry_delay(attempt: int, retry_after: Optional[str]) -> float:
    if retry_after:
        try:
            return min(max(float(retry_after), 0.5), 8.0)
        except ValueError:
            pass
    return min(1.0 * (2 ** attempt), 8.0)


async def get_token_security(session: aiohttp.ClientSession, token: str) -> Dict[str, Any]:
    """Return Birdeye token security data for a Solana mint address."""
    token = (token or "").strip()
    if not token:
        return {}
    if not _api_key():
        logger.warning("[BIRDEYE SECURITY] API key yo'q")
        return {}

    cached = _cache_get(_security_cache, token)
    if cached is not None:
        return cached

    data = await _get_json(session, _SECURITY_PATH, token, "SECURITY")
    if data:
        _cache_put(_security_cache, token, data)
        logger.debug("[BIRDEYE SECURITY] %s OK (%d fields)", token[:8], len(data))
    return data


async def get_token_overview(session: aiohttp.ClientSession, token: str) -> Dict[str, Any]:
    """Return Birdeye token overview data for a Solana mint address."""
    token = (token or "").strip()
    if not token:
        return {}
    if not _api_key():
        logger.warning("[BIRDEYE OVERVIEW] API key yo'q")
        return {}

    cached = _cache_get(_overview_cache, token)
    if cached is not None:
        return cached

    data = await _get_json(session, _OVERVIEW_PATH, token, "OVERVIEW")
    if data:
        _cache_put(_overview_cache, token, data)
    return data


async def clear_cache() -> None:
    """Clear Birdeye response caches (useful after changing API settings)."""
    _security_cache.clear()
    _overview_cache.clear()
