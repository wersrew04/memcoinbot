"""MEV Protection – sandwich / frontrun heuristics, dynamic slippage, retry."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from utils.logger import logger
from utils.helpers import safe_float
from config.settings import settings


class MEVProtector:
    """
    Pre-swap checks. True MEV detection needs mempool monitoring (Helius /
    Jito bundles). Here we apply practical heuristics + dynamic slippage.
    """

    def __init__(self):
        self._recent_quotes: list[Dict[str, Any]] = []

    def assess_risk(
        self,
        token: str,
        quote: Optional[Dict[str, Any]] = None,
        liquidity_usd: float = 0.0,
        volume_5m: float = 0.0,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Returns: (safe_to_trade, reason, meta)
        """
        if not settings.MEV_PROTECTION_ENABLED:
            return True, "MEV himoya o'chirilgan", {}

        meta: Dict[str, Any] = {"risk_score": 0.0}

        # Low liquidity → high sandwich risk
        risk = 0.0
        if liquidity_usd > 0 and liquidity_usd < 30_000:
            risk += 0.4
            meta["low_liq"] = True
        if liquidity_usd > 0 and liquidity_usd < 10_000:
            risk += 0.3

        # Sudden volume vs liquidity
        if liquidity_usd > 0 and volume_5m > liquidity_usd * 2:
            risk += 0.25
            meta["volume_spike"] = True

        # Quote price impact (if available)
        if quote:
            impact = safe_float(quote.get("priceImpactPct") or quote.get("price_impact"))
            if impact > 5:
                risk += 0.3
                meta["high_impact"] = impact
            elif impact > 2:
                risk += 0.15

        meta["risk_score"] = min(1.0, risk)

        if risk >= settings.MEV_SANDWICH_RISK_THRESHOLD:
            reason = f"MEV xavfi yuqori ({risk:.2f}) – savdo bekor qilindi"
            logger.warning(f"MEV block {token[:8]}...: {reason}")
            return False, reason, meta

        return True, "MEV xavfsiz", meta

    def dynamic_slippage_bps(self, base_bps: Optional[int] = None, risk_score: float = 0.0) -> int:
        base = base_bps or settings.SLIPPAGE_BPS
        if not settings.MEV_DYNAMIC_SLIPPAGE:
            return min(base, settings.MEV_MAX_SLIPPAGE_BPS)
        # higher risk → slightly higher slippage tolerance (or lower for safety)
        adjusted = int(base * (1.0 + risk_score * 0.3))
        return min(adjusted, settings.MEV_MAX_SLIPPAGE_BPS)

    def should_retry(self, attempt: int, error: str) -> bool:
        if attempt >= settings.MEV_RETRY_ATTEMPTS:
            return False
        retryable = ("timeout", "blockhash", "slippage", "429", "rate", "congest")
        return any(r in error.lower() for r in retryable)
