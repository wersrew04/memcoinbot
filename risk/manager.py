"""Risk management – kunlik zarar, ochiq pozitsiyalar, cooldown, limitlar."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from utils.logger import logger
from utils.helpers import utc_now, safe_float
from config.settings import settings
from config.constants import (
    REDIS_DAILY_LOSS,
    REDIS_OPEN_POSITIONS,
    REDIS_COOLDOWN_PREFIX,
    REDIS_BOT_STATUS,
)

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None


class RiskManager:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: Any = None
        # In-memory fallback (Redis bo'lmasa)
        self._memory: Dict[str, Any] = {
            "daily_loss": 0.0,
            "daily_loss_date": utc_now().date().isoformat(),
            "open_positions": {},  # token -> position dict
            "cooldowns": {},       # token -> expiry iso
            "bot_running": True,
        }

    async def connect(self):
        if aioredis is None:
            logger.warning("redis paketi topilmadi, in-memory risk ishlatiladi")
            return
        try:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("RiskManager Redisga ulandi")
        except Exception as e:
            logger.warning(f"Redis ulanish xato, in-memory ishlatiladi: {e}")
            self._redis = None

    async def close(self):
        if self._redis:
            await self._redis.close()

    # ---------- Daily Loss ----------
    async def _get_daily_loss(self) -> float:
        today = utc_now().date().isoformat()
        if self._redis:
            raw = await self._redis.get(REDIS_DAILY_LOSS)
            if raw:
                data = json.loads(raw)
                if data.get("date") == today:
                    return safe_float(data.get("loss"))
                # yangi kun – reset
                await self._redis.set(REDIS_DAILY_LOSS, json.dumps({"date": today, "loss": 0.0}))
                return 0.0
            return 0.0
        # memory
        if self._memory["daily_loss_date"] != today:
            self._memory["daily_loss"] = 0.0
            self._memory["daily_loss_date"] = today
        return self._memory["daily_loss"]

    async def add_realized_pnl(self, pnl_usd: float) -> float:
        """Sotishdan keyin real P&L qo'shish (manfiy bo'lsa loss)."""
        today = utc_now().date().isoformat()
        current = await self._get_daily_loss()
        # Faqat zarar qismini hisoblaymiz (yoki net)
        if pnl_usd < 0:
            new_loss = current + abs(pnl_usd)
        else:
            new_loss = max(0.0, current - pnl_usd)  # foyda lossni kamaytiradi
        if self._redis:
            await self._redis.set(
                REDIS_DAILY_LOSS,
                json.dumps({"date": today, "loss": new_loss}),
            )
        else:
            self._memory["daily_loss"] = new_loss
            self._memory["daily_loss_date"] = today
        logger.info(f"Daily loss yangilandi: ${new_loss:.2f} (PnL: {pnl_usd:+.2f})")
        return new_loss

    async def is_daily_loss_limit_reached(self) -> bool:
        loss = await self._get_daily_loss()
        if loss >= settings.MAX_DAILY_LOSS_USD:
            logger.warning(f"Kunlik zarar limiti yetdi: ${loss:.2f} >= ${settings.MAX_DAILY_LOSS_USD}")
            await self.set_bot_running(False)
            return True
        return False

    # ---------- Open Positions ----------
    async def get_open_positions(self) -> Dict[str, Dict[str, Any]]:
        if self._redis:
            raw = await self._redis.get(REDIS_OPEN_POSITIONS)
            return json.loads(raw) if raw else {}
        return self._memory["open_positions"]

    async def get_open_count(self) -> int:
        pos = await self.get_open_positions()
        return len(pos)

    async def can_open_new_position(self) -> tuple[bool, str]:
        if not await self.is_bot_running():
            return False, "Bot to'xtatilgan"
        if await self.is_daily_loss_limit_reached():
            return False, "Kunlik zarar limiti"
        count = await self.get_open_count()
        if count >= settings.MAX_OPEN_POSITIONS:
            return False, f"Maksimal ochiq pozitsiya: {count}/{settings.MAX_OPEN_POSITIONS}"
        return True, "OK"

    async def add_position(self, token: str, position: Dict[str, Any]):
        pos = await self.get_open_positions()
        pos[token] = position
        if self._redis:
            await self._redis.set(REDIS_OPEN_POSITIONS, json.dumps(pos))
        else:
            self._memory["open_positions"] = pos
        logger.info(f"Pozitsiya qo'shildi: {token}")

    async def remove_position(self, token: str) -> Optional[Dict[str, Any]]:
        pos = await self.get_open_positions()
        removed = pos.pop(token, None)
        if self._redis:
            await self._redis.set(REDIS_OPEN_POSITIONS, json.dumps(pos))
        else:
            self._memory["open_positions"] = pos
        if removed:
            logger.info(f"Pozitsiya yopildi: {token}")
        return removed

    async def update_position(self, token: str, updates: Dict[str, Any]):
        pos = await self.get_open_positions()
        if token in pos:
            pos[token].update(updates)
            if self._redis:
                await self._redis.set(REDIS_OPEN_POSITIONS, json.dumps(pos))
            else:
                self._memory["open_positions"] = pos

    # ---------- Cooldown ----------
    async def set_cooldown(self, token: str, minutes: Optional[int] = None):
        minutes = minutes or settings.COOLDOWN_MINUTES
        expiry = utc_now() + timedelta(minutes=minutes)
        key = f"{REDIS_COOLDOWN_PREFIX}{token}"
        if self._redis:
            await self._redis.setex(key, minutes * 60, expiry.isoformat())
        else:
            self._memory["cooldowns"][token] = expiry.isoformat()

    async def is_on_cooldown(self, token: str) -> bool:
        key = f"{REDIS_COOLDOWN_PREFIX}{token}"
        if self._redis:
            exists = await self._redis.exists(key)
            return bool(exists)
        exp = self._memory["cooldowns"].get(token)
        if not exp:
            return False
        return utc_now() < datetime.fromisoformat(exp)

    # ---------- Bot status ----------
    async def set_bot_running(self, running: bool):
        if self._redis:
            await self._redis.set(REDIS_BOT_STATUS, "1" if running else "0")
        self._memory["bot_running"] = running
        settings.BOT_RUNNING = running
        logger.info(f"Bot status: {'RUNNING' if running else 'STOPPED'}")

    async def is_bot_running(self) -> bool:
        if self._redis:
            val = await self._redis.get(REDIS_BOT_STATUS)
            if val is not None:
                return val == "1"
        return self._memory.get("bot_running", True)

    # ---------- Pre-trade check ----------
    async def pre_trade_check(self, token: str, amount_usd: float) -> tuple[bool, str]:
        """Sotib olishdan oldin to'liq tekshiruv."""
        can, reason = await self.can_open_new_position()
        if not can:
            return False, reason
        if await self.is_on_cooldown(token):
            return False, f"Cooldown faol: {token}"
        if amount_usd > settings.MAX_RISK_PER_TOKEN_USD:
            return False, f"Token uchun risk limiti: ${amount_usd} > ${settings.MAX_RISK_PER_TOKEN_USD}"
        # Allaqachon ochiqmi?
        pos = await self.get_open_positions()
        if token in pos:
            return False, "Bu token allaqachon ochiq"
        return True, "Pre-trade OK"

    async def get_status_summary(self) -> Dict[str, Any]:
        return {
            "bot_running": await self.is_bot_running(),
            "daily_loss_usd": await self._get_daily_loss(),
            "max_daily_loss_usd": settings.MAX_DAILY_LOSS_USD,
            "open_positions": await self.get_open_count(),
            "max_open_positions": settings.MAX_OPEN_POSITIONS,
            "positions": await self.get_open_positions(),
        }
