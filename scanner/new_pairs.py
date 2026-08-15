"""Yangi juftliklarni skanerlash, filterlash va buy ga yuborish."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Set, Callable, Awaitable

from utils.logger import logger
from utils.helpers import utc_now, safe_float

from scanner.dexscreener import DexScreenerClient
from scanner.birdeye import BirdeyeClient
from filters.pipeline import FilterPipeline
from config.settings import settings


class NewPairsScanner:
    def __init__(
        self,
        on_passed: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        pipeline: Optional[FilterPipeline] = None,
    ):
        self.dex = DexScreenerClient()
        self.birdeye = BirdeyeClient()
        self.pipeline = pipeline or FilterPipeline()
        self.seen_tokens: Set[str] = set()
        self.running = False
        self.on_passed = on_passed

    async def fetch_candidates(self) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []

        # DexScreener Token Profiles
        try:
            profiles = await self.dex.get_latest_token_profiles()

            for p in profiles:
                if p.get("chainId") != "solana":
                    continue

                addr = p.get("tokenAddress")

                if not addr:
                    continue

                if addr in self.seen_tokens:
                    continue

                candidates.append(
                    {
                        "source": "token_profile",
                        "token_address": addr,
                        "name": p.get("description") or addr,
                        "url": p.get("url"),
                    }
                )

        except Exception as e:
            logger.error(f"Token profiles olishda xato: {e}")

        # Dex Search
        for q in ["raydium", "pump", "solana"]:

            try:
                pairs = await self.dex.search_pairs(q)

                for pair in pairs:

                    if pair.get("chainId") != "solana":
                        continue

                    norm = self.dex.normalize_pair(pair)

                    addr = norm.get("token_address")

                    if not addr:
                        continue

                    if addr in self.seen_tokens:
                        continue

                    if norm.get("liquidity_usd", 0) < 1000:
                        continue

                    norm["source"] = "search"

                    candidates.append(norm)

            except Exception as e:
                logger.warning(f"Search '{q}' xato: {e}")

        unique = {}

        for c in candidates:
            addr = c.get("token_address")
            if addr:
                unique[addr] = c

        return list(unique.values())

    async def enrich_token(
        self,
        token_address: str,
        base_data: Optional[Dict] = None,
    ) -> Dict[str, Any]:

        result = (
            base_data.copy()
            if base_data
            else {"token_address": token_address}
        )

        # Dex pair ma'lumotlari
        try:
            pairs = await self.dex.get_token_pairs(token_address)

            if pairs:

                best = max(
                    pairs,
                    key=lambda p: safe_float(
                        (p.get("liquidity") or {}).get("usd")
                    ),
                )

                norm = self.dex.normalize_pair(best)

                result.update(norm)

        except Exception as e:
            logger.debug(f"Dex pairs enrich xato {token_address}: {e}")

        # BirdEye Overview
        try:
            overview = await self.birdeye.get_token_overview(token_address)

            if overview:

                ov = self.birdeye.normalize_overview(overview)

                result["birdeye_overview"] = ov

                if not result.get("liquidity_usd"):
                    result["liquidity_usd"] = ov.get("liquidity")

                if not result.get("market_cap"):
                    result["market_cap"] = ov.get("mc")

                if not result.get("volume_24h"):
                    result["volume_24h"] = ov.get("v24h_usd")

                if not result.get("holder_count"):
                    result["holder_count"] = ov.get("holder")

                if not result.get("token_name"):
                    result["token_name"] = ov.get("name")

                if not result.get("token_symbol"):
                    result["token_symbol"] = ov.get("symbol")

        except Exception as e:
            logger.debug(f"Birdeye overview xato {token_address}: {e}")

        # BirdEye Security (mint/freeze authority, honeypot, top10/dev holder %)
        # BUG FIX: bu bo'lim avval umuman yo'q edi -> mint/freeze/honeypot
        # filterlari va AI security factori doim "xavfsiz" deb hisoblardi,
        # chunki data["security"] hech qachon to'ldirilmagan edi.
        try:
            security = await self.birdeye.get_token_security(token_address)

            if security:
                result["security"] = self.birdeye.normalize_security(security)

        except Exception as e:
            logger.debug(f"Birdeye security xato {token_address}: {e}")

        # Holderlar
        try:
            holders = await self.birdeye.get_token_holders(
                token_address,
                limit=15,
            )

            result["top_holders"] = holders

        except Exception as e:
            logger.debug(f"Holders xato {token_address}: {e}")

        result["scanned_at"] = utc_now().isoformat()

        return result

    async def scan_once(self) -> List[Dict[str, Any]]:

        candidates = await self.fetch_candidates()

        logger.info(f"Topildi {len(candidates)} ta kandidat")

        passed = []

        for cand in candidates[:30]:

            addr = cand.get("token_address")

            if not addr:
                continue

            if addr in self.seen_tokens:
                continue

            try:

                enriched = await self.enrich_token(addr, cand)

                ok, reasons = await self.pipeline.run(enriched)

                if ok:

                    logger.info(
                        f"✅ Filter o'tdi: "
                        f"{enriched.get('token_symbol')} "
                        f"({addr})"
                    )

                    passed.append(enriched)

                    self.seen_tokens.add(addr)

                    if self.on_passed:

                        try:
                            await self.on_passed(enriched)

                        except Exception as e:
                            logger.error(
                                f"on_passed callback xato: {e}"
                            )

                else:

                    logger.debug(
                        f"❌ Filter o'tmadi {addr}: {reasons}"
                    )

                    self.seen_tokens.add(addr)

            except Exception as e:

                logger.error(
                    f"Token {addr} qayta ishlashda xato: {e}"
                )

            await asyncio.sleep(0.3)

        return passed

    async def run_loop(self, interval_sec: int = 45):

        self.running = True

        logger.info("NewPairsScanner ishga tushdi")

        while self.running:

            try:

                if not settings.BOT_RUNNING:
                    await asyncio.sleep(5)
                    continue

                passed = await self.scan_once()

                if passed:

                    logger.info(
                        f"Skanerlash yakunlandi: "
                        f"{len(passed)} ta token filterdan o'tdi"
                    )

            except Exception as e:

                logger.exception(f"Skaner loop xato: {e}")

            await asyncio.sleep(interval_sec)

    def stop(self):
        self.running = False