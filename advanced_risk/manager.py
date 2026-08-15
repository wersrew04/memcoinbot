"""Advanced Risk Manager – consecutive losses, daily trades, emergency stop, auto-pause."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from utils.logger import logger
from utils.helpers import utc_now, safe_float
from config.settings import settings
from risk.manager import RiskManager


class AdvancedRiskManager:
    """
    Wraps / extends existing RiskManager with extra controls.
    Does not replace the original – composes it.
    """

    def __init__(self, base: RiskManager):
        self.base = base
        self.consecutive_losses: int = 0
        self.daily_trades: int = 0
        self._daily_trades_date: str = utc_now().date().isoformat()
        self.emergency_stop: bool = settings.EMERGENCY_STOP
        self.paused: bool = False
        self.pause_reason: str = ""

    def _reset_daily_if_needed(self):
        today = utc_now().date().isoformat()
        if self._daily_trades_date != today:
            self.daily_trades = 0
            self._daily_trades_date = today

    async def pre_trade_check(self, token: str, amount_usd: float) -> Tuple[bool, str]:
        if self.emergency_stop or settings.EMERGENCY_STOP:
            return False, "Favqulodda to'xtatish faol"

        if self.paused:
            return False, f"Bot to'xtatilgan: {self.pause_reason}"

        # base checks
        ok, reason = await self.base.pre_trade_check(token, amount_usd)
        if not ok:
            return False, reason

        self._reset_daily_if_needed()
        if self.daily_trades >= settings.MAX_DAILY_TRADES:
            return False, f"Kunlik savdo limiti tugadi ({settings.MAX_DAILY_TRADES})"

        if self.consecutive_losses >= settings.MAX_CONSECUTIVE_LOSSES:
            self.pause(f"Ketma-ket zararlar: {self.consecutive_losses}")
            return False, "Ketma-ket zararlar limiti – avtomatik to'xtatildi"

        return True, "OK"

    def record_trade_result(self, pnl_usd: float):
        """Sotishdan keyin: consecutive losses. daily_trades buy da oshadi."""
        self._reset_daily_if_needed()
        if pnl_usd < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def pause(self, reason: str):
        self.paused = True
        self.pause_reason = reason
        logger.warning(f"AdvancedRisk PAUSE: {reason}")

    def resume(self):
        self.paused = False
        self.pause_reason = ""
        self.consecutive_losses = 0
        logger.info("AdvancedRisk RESUME")

    def set_emergency_stop(self, active: bool):
        self.emergency_stop = active
        logger.warning(f"Emergency stop = {active}")

    def status(self) -> Dict[str, Any]:
        return {
            "emergency_stop": self.emergency_stop or settings.EMERGENCY_STOP,
            "paused": self.paused,
            "pause_reason": self.pause_reason,
            "consecutive_losses": self.consecutive_losses,
            "daily_trades": self.daily_trades,
            "max_daily_trades": settings.MAX_DAILY_TRADES,
            "max_consecutive_losses": settings.MAX_CONSECUTIVE_LOSSES,
        }
