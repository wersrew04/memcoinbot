"""X.com (Twitter) API v2 rasmiy klienti.

FAQAT rasmiy, hujjatlashtirilgan endpoint ishlatiladi:
``GET /2/tweets/search/recent`` (Bearer Token / App-only auth).
Hech qanday scraping, HTML parsing yoki noofitsial endpoint yo'q.

Talab qilinadigan narsa: ``X_API_BEARER_TOKEN`` (.env). Token bo'lmasa
yoki API xato/limit qaytarsa, klient ``None`` qaytaradi — chaqiruvchi
(``analyzer.py``) buni "ma'lumot yo'q, neytral ball" sifatida talqin
qiladi. Bu hech qachon botning asosiy oqimini to'xtatmasligi kerak.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from config.settings import settings
from utils.logger import logger
from utils.retry import async_retry

X_API_BASE = "https://api.x.com/2"

TWEET_FIELDS = "public_metrics,created_at,author_id,lang"
USER_FIELDS = "public_metrics,verified,username"
EXPANSIONS = "author_id"


class XApiClient:
    """Ingichka wrapper — X API v2 recent-search ustida."""

    def __init__(self, bearer_token: Optional[str] = None):
        self.bearer_token = bearer_token or settings.X_API_BEARER_TOKEN
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=X_API_BASE,
                timeout=settings.SOCIAL_API_TIMEOUT_SEC,
                headers={"Authorization": f"Bearer {self.bearer_token}"} if self.bearer_token else {},
            )
        return self._client

    @property
    def configured(self) -> bool:
        return bool(self.bearer_token)

    @async_retry(max_attempts=2, min_wait=1, max_wait=5)
    async def search_recent(self, query: str, max_results: int = 25) -> Optional[dict[str, Any]]:
        """So'nggi ~7 kunlik postlarni qidiradi. Rate-limit (429) yoki
        avtorizatsiya xatosida (401/403) None qaytaradi va log yozadi —
        bu holatlar odatiy holat (bepul/quyi tarif kvotasi tugashi mumkin),
        chaqiruvchini to'xtatmasligi kerak."""
        if not self.configured:
            return None

        client = self._get_client()
        params = {
            "query": query,
            "max_results": max(10, min(max_results, 100)),
            "tweet.fields": TWEET_FIELDS,
            "user.fields": USER_FIELDS,
            "expansions": EXPANSIONS,
        }
        try:
            resp = await client.get("/tweets/search/recent", params=params)
        except httpx.HTTPError as e:
            logger.debug(f"X API so'rov xatosi: {e}")
            return None

        if resp.status_code == 429:
            logger.warning("X API rate limit (429) — bu so'rov o'tkazib yuborildi")
            return None
        if resp.status_code in (401, 403):
            logger.warning(
                f"X API avtorizatsiya xatosi ({resp.status_code}) — X_API_BEARER_TOKEN "
                "yoki tarif rejasini tekshiring"
            )
            return None
        if resp.status_code != 200:
            logger.debug(f"X API kutilmagan status {resp.status_code}: {resp.text[:200]}")
            return None

        try:
            return resp.json()
        except ValueError:
            return None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
