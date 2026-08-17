"""
Advanced Risk Manager — kengaytirilgan risk boshqaruvi.
Kunlik savdolar, consecutive losses, drawdown, emergency stop.
"""
from __future__ import annotations
import asyncio
from typing import Any, Dict, Tuple
from utils.logger import logger
from utils.helpers import utc_now, safe_float
from config.settings import settings


class AdvancedRiskManager:
    def __init__(self, base_risk_manager):
        self.base = base_risk_manager
        self.daily_trades: int = 0
        self.consecutive_losses: int = 0
        self.peak_balance: float = 0.0
        self.current_balance: float = 0.0
        self._daily_date: str = utc_now().date().isoformat()
        self._lock = asyncio.Lock()
        self._paused: bool = False
        self._pause_reason: str = ""

    def _reset_daily_if_needed(self):
        today = utc_now().date().isoformat()
        if self._daily_date != today:
            self.daily_trades = 0
            self._daily_date = today
            logger.info("Kunlik hisoblagichlar yangilandi")

    def pause(self, reason: str = ""):
        """Risk menejerni pauzaga qo'yadi (yangi savdolar bloklanadi)."""
        self._paused = True
        self._pause_reason = reason or "Manual pause"
        logger.warning("AdvancedRiskManager PAUSED: {}".format(self._pause_reason))

    def resume(self):
        """Pauzani olib tashlaydi va consecutive losses hisoblagichini nolga tushiradi."""
        was_paused = self._paused
        self._paused = False
        self._pause_reason = ""
        self.consecutive_losses = 0
        if was_paused:
            logger.info("AdvancedRiskManager RESUMED (consecutive_losses reset)")
        else:
            logger.info("AdvancedRiskManager resume chaqirildi (allaqachon aktiv edi)")

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def pause_reason(self) -> str:
        return self._pause_reason

    async def pre_trade_check(self, token: str, amount_usd: float) -> Tuple[bool, str]:
        async with self._lock:
            self._reset_daily_if_needed()

            # Manual / auto pause
            if self._paused:
                return False, "Paused: {}".format(self._pause_reason or "risk pause")

            # Emergency stop
            if settings.EMERGENCY_STOP:
                return False, "Emergency stop faol"

            # Bot ishlamayotgan bo'lsa
            if not settings.BOT_RUNNING:
                return False, "Bot to'xtatilgan"

            # Kunlik savdolar limiti
            if self.daily_trades >= settings.MAX_DAILY_TRADES:
                return False, "Kunlik savdolar limiti: {}".format(settings.MAX_DAILY_TRADES)

            # Consecutive losses — avtomatik pause
            if self.consecutive_losses >= settings.MAX_CONSECUTIVE_LOSSES:
                reason = "Ketma-ket {}ta zarar — to'xtatildi".format(self.consecutive_losses)
                self.pause(reason)
                return False, reason

            # Max drawdown
            if self.peak_balance > 0 and self.current_balance > 0:
                drawdown = (self.peak_balance - self.current_balance) / self.peak_balance
                if drawdown >= settings.MAX_DRAWDOWN_PCT:
                    reason = "Max drawdown: {:.1f}%".format(drawdown * 100)
                    self.pause(reason)
                    return False, reason

            # Base risk check
            ok, reason = await self.base.pre_trade_check(token, amount_usd)
            return ok, reason

    def record_win(self, pnl_usd: float):
        self.consecutive_losses = 0
        self.current_balance += pnl_usd
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance

    def record_loss(self, pnl_usd: float):
        self.consecutive_losses += 1
        self.current_balance += pnl_usd  # pnl_usd manfiy
        logger.warning("Ketma-ket zarar: {}ta".format(self.consecutive_losses))

    def record_trade_result(self, pnl_usd: float):
        if pnl_usd >= 0:
            self.record_win(pnl_usd)
        else:
            self.record_loss(pnl_usd)

    @property
    def emergency_stop(self) -> bool:
        return settings.EMERGENCY_STOP

    def set_emergency_stop(self, val: bool):
        settings.EMERGENCY_STOP = val
        logger.warning("EMERGENCY_STOP changed to: {}".format(val))

    def status(self) -> Dict[str, Any]:
        base_status = {}
        if self.base:
            base_status = {
                "open_positions": len(self.base.positions) if hasattr(self.base, "positions") else 0,
                "daily_loss_usd": self.base.daily_loss_usd if hasattr(self.base, "daily_loss_usd") else 0.0,
            }
        return {
            **base_status,
            "daily_trades": self.daily_trades,
            "consecutive_losses": self.consecutive_losses,
            "peak_balance": round(self.peak_balance, 2),
            "current_balance": round(self.current_balance, 2),
            "drawdown_pct": round(
                (self.peak_balance - self.current_balance) / self.peak_balance * 100, 2
            ) if self.peak_balance > 0 else 0,
            "emergency_stop": settings.EMERGENCY_STOP,
            "paused": self._paused,
            "pause_reason": self._pause_reason,
            "max_daily_trades": getattr(settings, "MAX_DAILY_TRADES", None),
        }

    async def get_risk_summary(self) -> Dict[str, Any]:
        base_status = await self.base.get_status_summary()
        return {
            **base_status,
            "daily_trades": self.daily_trades,
            "consecutive_losses": self.consecutive_losses,
            "peak_balance": round(self.peak_balance, 2),
            "current_balance": round(self.current_balance, 2),
            "drawdown_pct": round(
                (self.peak_balance - self.current_balance) / self.peak_balance * 100, 2
            ) if self.peak_balance > 0 else 0,
            "emergency_stop": settings.EMERGENCY_STOP,
            "paused": self._paused,
            "pause_reason": self._pause_reason,
            "max_daily_trades": getattr(settings, "MAX_DAILY_TRADES", None),
        }

