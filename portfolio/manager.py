"""Portfolio Manager – allocation, exposure, risk score."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from utils.helpers import safe_float
from utils.logger import logger
from config.settings import settings
from risk.manager import RiskManager


class PortfolioManager:
    def __init__(self, risk: RiskManager):
        self.risk = risk

    async def allocation(self) -> Dict[str, Any]:
        positions = await self.risk.get_open_positions()
        total = sum(safe_float(p.get("amount_usd")) for p in positions.values()) or 1.0
        items = []
        for token, pos in positions.items():
            usd = safe_float(pos.get("amount_usd"))
            items.append({
                "token": token,
                "symbol": pos.get("symbol", token[:8]),
                "amount_usd": usd,
                "pct": round(usd / total * 100, 2),
            })
        return {
            "total_exposure_usd": round(total, 2),
            "position_count": len(positions),
            "allocations": sorted(items, key=lambda x: -x["pct"]),
            "max_single_pct": settings.MAX_TOKEN_ALLOCATION_PCT * 100,
        }

    async def can_allocate(self, amount_usd: float) -> tuple[bool, str]:
        positions = await self.risk.get_open_positions()
        total = sum(safe_float(p.get("amount_usd")) for p in positions.values())
        new_total = total + amount_usd
        if new_total <= 0:
            return True, "OK"

        # Concentration cap only makes sense once there's an actual portfolio
        # to be concentrated relative to. With 0 (or few) open positions, a
        # single new trade is mathematically ~100% of the book, which would
        # always exceed MAX_TOKEN_ALLOCATION_PCT and block every early trade.
        # Skip the check until we have a real diversification base.
        min_positions_for_check = max(1, settings.PORTFOLIO_DIVERSIFICATION_MIN)
        if len(positions) < min_positions_for_check:
            return True, "OK"

        share = amount_usd / new_total
        if share > settings.MAX_TOKEN_ALLOCATION_PCT:
            return False, f"Token ulushi {settings.MAX_TOKEN_ALLOCATION_PCT*100:.0f}% dan oshib ketadi"
        return True, "OK"

    async def risk_score(self) -> float:
        """Simple 0–100 portfolio risk (higher = riskier)."""
        positions = await self.risk.get_open_positions()
        n = len(positions)
        if n == 0:
            return 0.0
        # concentration
        total = sum(safe_float(p.get("amount_usd")) for p in positions.values()) or 1.0
        max_share = max(safe_float(p.get("amount_usd")) / total for p in positions.values())
        concentration = max_share * 50
        # count vs diversification target
        div = max(0, (settings.PORTFOLIO_DIVERSIFICATION_MIN - n) / settings.PORTFOLIO_DIVERSIFICATION_MIN) * 30
        size = min(30.0, n * 5)
        return round(min(100.0, concentration + div + size), 1)
