from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Any

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default

def safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(val)) if val is not None else default
    except (TypeError, ValueError):
        return default

def pnl_percent(entry: float, current: float) -> float:
    if entry <= 0:
        return 0.0
    return ((current - entry) / entry) * 100.0

def pnl_usd(amount_usd: float, entry: float, current: float) -> float:
    if entry <= 0:
        return 0.0
    return amount_usd * ((current - entry) / entry)

def roundtrip_fee_usd(amount_usd: float = 0.0) -> float:
    """Buy + sell komissiya (Phantom/Solana priority + base + ATA taxminan).
    FEE_USD_ROUNDTRIP (fixed) va FEE_PCT_ROUNDTRIP (% of size) dan kattasini oladi.
    """
    try:
        from config.settings import settings
        fixed = float(getattr(settings, "FEE_USD_ROUNDTRIP", 0.25) or 0)
        pct = float(getattr(settings, "FEE_PCT_ROUNDTRIP", 0.02) or 0)
        return max(fixed, amount_usd * pct)
    except Exception:
        return max(0.25, amount_usd * 0.02)

def net_pnl_usd(amount_usd: float, entry: float, current: float) -> float:
    """Komissiya ayirilgan sof PnL (USD)."""
    gross = pnl_usd(amount_usd, entry, current)
    return gross - roundtrip_fee_usd(amount_usd)

def net_pnl_percent(amount_usd: float, entry: float, current: float) -> float:
    """Komissiya ayirilgan sof PnL (% of position size)."""
    if amount_usd <= 0:
        return pnl_percent(entry, current)
    return (net_pnl_usd(amount_usd, entry, current) / amount_usd) * 100.0

async def retry_async(coro_fn, attempts: int = 3, delay: float = 1.0, *args, **kwargs):
    for i in range(attempts):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as e:
            if i == attempts - 1:
                raise
            await asyncio.sleep(delay * (i + 1))
