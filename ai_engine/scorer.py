"""AI Trading Engine – heuristic multi-factor score (0–100) + recommendation.

Production path: replace weighted formula with trained model (e.g. LightGBM /
neural net) loaded from disk; TradeLearner updates weights or model periodically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from utils.helpers import safe_float, safe_int
from utils.logger import logger
from config.settings import settings


class AIRecommendation(str, Enum):
    STRONG_BUY = "Kuchli xarid"
    BUY = "Xarid"
    NEUTRAL = "Neytral"
    AVOID = "Saqlanish kerak"


@dataclass
class AIScoreResult:
    score: float
    recommendation: AIRecommendation
    factors: Dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


class AIScorer:
    """
    Computes AI Score from token features.
    All weights come from settings (Admin Panel controllable).
    """

    def __init__(self, custom_weights: Optional[Dict[str, float]] = None):
        self.weights = custom_weights or {
            "liquidity": settings.AI_WEIGHT_LIQUIDITY,
            "volume": settings.AI_WEIGHT_VOLUME,
            "holders": settings.AI_WEIGHT_HOLDERS,
            "whale": settings.AI_WEIGHT_WHALE,
            "smart_money": settings.AI_WEIGHT_SMART_MONEY,
            "momentum": settings.AI_WEIGHT_MOMENTUM,
            "security": settings.AI_WEIGHT_SECURITY,
            "social": settings.AI_WEIGHT_SOCIAL,
            "age": settings.AI_WEIGHT_AGE,
            "similar": settings.AI_WEIGHT_SIMILAR,
        }

    def _norm(self, value: float, low: float, high: float, invert: bool = False) -> float:
        """Normalize to 0–1, clamp."""
        if high <= low:
            return 0.5
        v = max(low, min(high, value))
        score = (v - low) / (high - low)
        return 1.0 - score if invert else score

    def score(self, data: Dict[str, Any]) -> AIScoreResult:
        if not settings.AI_ENABLED:
            return AIScoreResult(score=50.0, recommendation=AIRecommendation.NEUTRAL)

        factors: Dict[str, float] = {}
        reasons: list[str] = []

        # Liquidity (higher better, cap at 500k)
        liq = safe_float(data.get("liquidity_usd"))
        if liq <= 0:
            ov = data.get("birdeye_overview") or {}
            liq = safe_float(ov.get("liquidity"))
        factors["liquidity"] = self._norm(liq, 10_000, 500_000)

        # Volume 24h
        vol = safe_float(data.get("volume_24h"))
        if vol <= 0:
            ov = data.get("birdeye_overview") or {}
            vol = safe_float(ov.get("v24h_usd"))
        factors["volume"] = self._norm(vol, 20_000, 1_000_000)

        # Holders
        holders = safe_int(data.get("holder_count"))
        if holders <= 0:
            sec = data.get("security") or {}
            holders = safe_int(sec.get("holder_count"))
        factors["holders"] = self._norm(float(holders), 50, 5000)

        # Whale activity (from whale module injection)
        whale_score = safe_float(data.get("whale_activity_score"), 0.5)
        factors["whale"] = max(0.0, min(1.0, whale_score))

        # Smart money (from smart_money module)
        sm_score = safe_float(data.get("smart_money_score"), 0.5)
        factors["smart_money"] = max(0.0, min(1.0, sm_score))

        # Momentum: volume spike + price change
        vol_5m = safe_float(data.get("volume_5m"))
        vol_1h = safe_float(data.get("volume_1h"))
        spike = (vol_5m / (vol_1h / 12)) if vol_1h > 0 else 1.0
        price_chg = safe_float(data.get("price_change_1h") or data.get("priceChange", {}).get("h1"))
        mom = 0.5 * self._norm(spike, 0.5, 5.0) + 0.5 * self._norm(price_chg, -20, 50)
        factors["momentum"] = max(0.0, min(1.0, mom))

        # Security (mint/freeze disabled, not honeypot)
        sec = data.get("security") or {}
        sec_ok = 1.0
        if sec.get("mint_authority") or sec.get("is_mintable"):
            sec_ok -= 0.4
            reasons.append("Mint authority active")
        if sec.get("freeze_authority") or sec.get("is_freezable"):
            sec_ok -= 0.3
            reasons.append("Freeze authority active")
        if sec.get("is_honeypot") in (True, "true", "1"):
            sec_ok = 0.0
            reasons.append("Honeypot")
        top10 = safe_float(sec.get("top10_holder_pct") or sec.get("top10_user_pct"))
        if top10 > 1:
            top10 /= 100.0
        if top10 > 0.4:
            sec_ok -= 0.2
            reasons.append(f"Top10 high: {top10*100:.0f}%")
        factors["security"] = max(0.0, min(1.0, sec_ok))

        # Social (optional, default neutral)
        social = safe_float(data.get("social_score"), 0.5)
        factors["social"] = max(0.0, min(1.0, social))

        # Token age (prefer not brand-new rugs, not too old stagnant)
        age_min = safe_float(data.get("token_age_minutes") or data.get("pair_created_at_minutes"), 60)
        # sweet spot ~30min–24h
        if age_min < 5:
            factors["age"] = 0.2
        elif age_min < 30:
            factors["age"] = 0.6
        elif age_min < 1440:
            factors["age"] = 1.0
        else:
            factors["age"] = 0.7

        # Similar token success (injected or default)
        factors["similar"] = safe_float(data.get("similar_success_rate"), 0.5)

        # Weighted sum → 0–100
        total_w = sum(self.weights.values()) or 1.0
        raw = sum(factors.get(k, 0.5) * w for k, w in self.weights.items())
        score = (raw / total_w) * 100.0

        # External boosts already applied in factors; clamp
        score = max(0.0, min(100.0, score))

        if score >= settings.AI_STRONG_BUY_THRESHOLD:
            rec = AIRecommendation.STRONG_BUY
        elif score >= settings.AI_BUY_THRESHOLD:
            rec = AIRecommendation.BUY
        elif score >= settings.AI_MIN_SCORE:
            rec = AIRecommendation.NEUTRAL
        else:
            rec = AIRecommendation.AVOID

        logger.debug(f"AI Score {score:.1f} → {rec.value} | factors={ {k: round(v,2) for k,v in factors.items()} }")
        return AIScoreResult(score=round(score, 2), recommendation=rec, factors=factors, reasons=reasons)

    def passes_threshold(self, result: AIScoreResult) -> bool:
        return result.score >= settings.AI_MIN_SCORE and result.recommendation != AIRecommendation.AVOID
