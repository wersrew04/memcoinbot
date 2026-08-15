"""RPC / API health, latency, auto-recovery."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional
import httpx
from utils.logger import logger
from config.settings import settings
from config.constants import DEXSCREENER_BASE, BIRDEYE_BASE


class HealthMonitor:
    def __init__(self, rpc=None, on_unhealthy=None):
        self.rpc = rpc
        self.on_unhealthy = on_unhealthy  # async callback
        self.running = False
        self.stats: Dict[str, Any] = {
            "rpc_ok": True,
            "rpc_latency_ms": 0,
            "birdeye_ok": True,
            "dexscreener_ok": True,
            "errors": 0,
        }

    async def check_rpc(self) -> bool:
        if not self.rpc:
            return True
        t0 = time.perf_counter()
        try:
            # assume rpc has get_health or get_slot
            if hasattr(self.rpc, "get_slot"):
                await self.rpc.get_slot()
            elif hasattr(self.rpc, "is_connected"):
                await self.rpc.is_connected()
            else:
                return True
            ms = (time.perf_counter() - t0) * 1000
            self.stats["rpc_latency_ms"] = round(ms, 1)
            self.stats["rpc_ok"] = ms < settings.API_LATENCY_THRESHOLD_MS
            return self.stats["rpc_ok"]
        except Exception as e:
            self.stats["rpc_ok"] = False
            self.stats["errors"] += 1
            logger.error(f"RPC health fail: {e}")
            return False

    async def check_http(self, name: str, url: str) -> bool:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(url)
                ok = r.status_code < 500
            ms = (time.perf_counter() - t0) * 1000
            self.stats[f"{name}_ok"] = ok and ms < settings.API_LATENCY_THRESHOLD_MS
            self.stats[f"{name}_latency_ms"] = round(ms, 1)
            return self.stats[f"{name}_ok"]
        except Exception as e:
            self.stats[f"{name}_ok"] = False
            self.stats["errors"] += 1
            logger.debug(f"{name} health fail: {e}")
            return False

    async def check_once(self):
        await self.check_rpc()
        await self.check_http("dexscreener", f"{DEXSCREENER_BASE}/token-profiles/latest/v1")
        # Birdeye needs key – skip full check if no key
        if settings.BIRDEYE_API_KEY:
            await self.check_http("birdeye", f"{BIRDEYE_BASE}/defi/price?address=So11111111111111111111111111111111111111112")

        unhealthy = not self.stats.get("rpc_ok", True)
        if unhealthy and settings.AUTO_RECOVERY_ENABLED and self.on_unhealthy:
            try:
                await self.on_unhealthy(self.stats)
            except Exception as e:
                logger.error(f"Recovery callback failed: {e}")

    async def run_loop(self, interval: Optional[int] = None):
        interval = interval or settings.RPC_HEALTH_CHECK_INTERVAL_SEC
        self.running = True
        logger.info(f"HealthMonitor started (every {interval}s)")
        while self.running:
            try:
                await self.check_once()
            except Exception as e:
                logger.exception(f"Health loop error: {e}")
            await asyncio.sleep(interval)

    def stop(self):
        self.running = False

    def status(self) -> Dict[str, Any]:
        return dict(self.stats)
