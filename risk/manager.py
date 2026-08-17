"""Risk Manager — ochiq pozitsiyalar, kunlik zarar, cooldown."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from utils.logger import logger
from utils.helpers import utc_now, safe_float
from config.settings import settings

class RiskManager:
    def __init__(self):
        self._positions: Dict[str, Dict] = {}
        self._cooldowns: Dict[str, datetime] = {}
        self._processed: set = set()
        self._daily_loss_usd: float = 0.0
        self._daily_date: str = utc_now().date().isoformat()
        self._lock = asyncio.Lock()
        self._running: bool = True

    def _reset_daily_if_needed(self):
        today = utc_now().date().isoformat()
        if self._daily_date != today:
            self._daily_loss_usd = 0.0
            self._daily_date = today

    async def pre_trade_check(self, token: str, amount_usd: float) -> Tuple[bool, str]:
        async with self._lock:
            if not self._running:
                return False, "Bot to'xtatilgan"
            self._reset_daily_if_needed()
            if len(self._positions) >= settings.MAX_OPEN_POSITIONS:
                return False, f"Max ochiq pozitsiya: {settings.MAX_OPEN_POSITIONS}"
            if self._daily_loss_usd >= settings.MAX_DAILY_LOSS_USD:
                return False, f"Kunlik zarar limiti: ${settings.MAX_DAILY_LOSS_USD}"
            if token in self._positions:
                return False, "Pozitsiya allaqachon ochiq"
            if token in self._cooldowns:
                diff = (utc_now() - self._cooldowns[token]).total_seconds() / 60
                if diff < settings.COOLDOWN_MINUTES:
                    return False, f"Cooldown: {settings.COOLDOWN_MINUTES - int(diff)} daqiqa qoldi"
            if token in self._processed:
                return False, "Token allaqachon qayta ishlangan"
            return True, "OK"

    async def open_position(self, token: str, data: Dict) -> bool:
        async with self._lock:
            if token in self._positions:
                return False
            self._positions[token] = {**data, "opened_at": utc_now().isoformat()}
            self._processed.add(token)
            logger.info(f"Pozitsiya ochildi: {data.get('symbol', token[:8])}")
            return True

    async def close_position(self, token: str, pnl_usd: float):
        async with self._lock:
            if token not in self._positions:
                return None
            pos = self._positions.pop(token)
            self._cooldowns[token] = utc_now()
            self._reset_daily_if_needed()
            if pnl_usd < 0:
                self._daily_loss_usd += abs(pnl_usd)
            logger.info(f"Pozitsiya yopildi: {pos.get('symbol', token[:8])} PnL=${pnl_usd:+.2f}")
            return pos

    async def update_position(self, token: str, updates: Dict):
        async with self._lock:
            if token in self._positions:
                self._positions[token].update(updates)

    async def get_open_positions(self) -> Dict[str, Dict]:
        async with self._lock:
            return dict(self._positions)

    async def get_status_summary(self) -> Dict[str, Any]:
        async with self._lock:
            self._reset_daily_if_needed()
            return {
                "open_positions": len(self._positions),
                "positions": dict(self._positions),
                "daily_loss_usd": self._daily_loss_usd,
                "running": self._running,
            }

    async def set_bot_running(self, running: bool):
        self._running = running

    async def reset_daily_loss(self):
        async with self._lock:
            self._daily_loss_usd = 0.0

    def clear_cooldowns(self):
        self._cooldowns.clear()

    def clear_processed(self):
        self._processed.clear()
