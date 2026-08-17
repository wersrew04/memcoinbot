"""
AI Scorer — tokenni ko'p parametrli baholash.
Score: 0–100. 65+ → BUY, 80+ → STRONG BUY.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple
from utils.helpers import safe_float, safe_int
from config.settings import settings


class Recommendation(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY        = "BUY"
    HOLD       = "HOLD"
    AVOID      = "AVOID"


@dataclass
class ScoreResult:
    score: float = 0.0
    recommendation: Recommendation = Recommendation.AVOID
    breakdown: Dict[str, float] = field(default_factory=dict)
    signals: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class AIScorer:
    """
    Tokenni quyidagi omillar bo'yicha baholaydi:
      - Likvidlik
      - Hajm va momentum
      - Holderlar taqsimoti
      - Xavfsizlik
      - Token yoshi
      - Buy/Sell nisbati
      - Birdeye security
    """

    def score(self, data: Dict[str, Any]) -> ScoreResult:
        result = ScoreResult()
        total = 0.0
        max_score = 0.0

        checks = [
            self._score_liquidity(data),
            self._score_volume(data),
            self._score_momentum(data),
            self._score_holders(data),
            self._score_security(data),
            self._score_age(data),
            self._score_buy_sell(data),
        ]

        for name, earned, max_pts, signals, warnings in checks:
            result.breakdown[name] = round(earned, 2)
            total += earned
            max_score += max_pts
            result.signals.extend(signals)
            result.warnings.extend(warnings)

        # 0–100 ga normallashtirish
        result.score = round((total / max_score * 100) if max_score > 0 else 0, 2)

        # Tavsiya
        if result.score >= settings.AI_STRONG_BUY_THRESHOLD:
            result.recommendation = Recommendation.STRONG_BUY
        elif result.score >= settings.AI_BUY_THRESHOLD:
            result.recommendation = Recommendation.BUY
        elif result.score >= 45:
            result.recommendation = Recommendation.HOLD
        else:
            result.recommendation = Recommendation.AVOID

        return result

    def passes_threshold(self, result: ScoreResult) -> bool:
        if not settings.AI_ENABLED:
            return True
        return result.score >= settings.AI_MIN_SCORE

    # ─── BAHOLASH FUNKSIYALARI ───

    def _score_liquidity(self, d: Dict) -> Tuple:
        liq = safe_float(d.get("liquidity_usd"))
        signals, warnings = [], []
        max_pts = 20.0

        if liq >= 500_000:
            pts = 20.0; signals.append("Katta likvidlik: ${:,.0f}".format(liq))
        elif liq >= 200_000:
            pts = 17.0; signals.append("Yaxshi likvidlik: ${:,.0f}".format(liq))
        elif liq >= 100_000:
            pts = 14.0
        elif liq >= 50_000:
            pts = 10.0
        elif liq >= 20_000:
            pts = 6.0; warnings.append("Kam likvidlik: ${:,.0f}".format(liq))
        else:
            pts = 1.0; warnings.append("Juda kam likvidlik")

        return "liquidity", pts, max_pts, signals, warnings

    def _score_volume(self, d: Dict) -> Tuple:
        vol5m = safe_float(d.get("volume_5m"))
        vol1h = safe_float(d.get("volume_1h"))
        signals, warnings = [], []
        max_pts = 20.0

        pts = 0.0
        if vol5m >= 500_000:
            pts += 12.0; signals.append("Juda baland 5m hajm")
        elif vol5m >= 100_000:
            pts += 10.0; signals.append("Baland 5m hajm")
        elif vol5m >= 50_000:
            pts += 7.0
        elif vol5m >= 20_000:
            pts += 4.0
        else:
            warnings.append("Past 5m hajm")

        if vol1h >= 1_000_000:
            pts += 8.0; signals.append("Katta 1h hajm")
        elif vol1h >= 500_000:
            pts += 6.0
        elif vol1h >= 100_000:
            pts += 4.0
        elif vol1h >= 50_000:
            pts += 2.0
        else:
            warnings.append("Past 1h hajm")

        return "volume", min(pts, max_pts), max_pts, signals, warnings

    def _score_momentum(self, d: Dict) -> Tuple:
        pc5m = safe_float(d.get("price_change_5m"))
        pc1h = safe_float(d.get("price_change_1h"))
        signals, warnings = [], []
        max_pts = 15.0
        pts = 0.0

        # 5m
        if 5 <= pc5m <= 50:
            pts += 8.0; signals.append("Yaxshi 5m o'sish: {:.1f}%".format(pc5m))
        elif 0 < pc5m < 5:
            pts += 4.0
        elif pc5m > 50:
            pts += 3.0; warnings.append("Juda tez o'sish (dump xavfi)")
        elif pc5m < -10:
            pts += 0.0; warnings.append("5m tushish: {:.1f}%".format(pc5m))

        # 1h
        if 10 <= pc1h <= 100:
            pts += 7.0; signals.append("Kuchli 1h momentum: {:.1f}%".format(pc1h))
        elif 0 < pc1h < 10:
            pts += 3.0
        elif pc1h > 100:
            pts += 1.0; warnings.append("1h juda baland (late entry)")
        elif pc1h < -15:
            pts += 0.0; warnings.append("1h tushish: {:.1f}%".format(pc1h))

        return "momentum", min(pts, max_pts), max_pts, signals, warnings

    def _score_holders(self, d: Dict) -> Tuple:
        holders = safe_int(d.get("holder_count") or
                           d.get("security", {}).get("holder_count") or
                           d.get("birdeye_overview", {}).get("holder"))
        top10 = safe_float(
            d.get("security", {}).get("top10_holder_pct") or
            d.get("security", {}).get("top10_user_pct") or 0
        )
        if top10 > 1:
            top10 /= 100

        signals, warnings = [], []
        max_pts = 15.0
        pts = 0.0

        if holders >= 5000:
            pts += 8.0; signals.append("Ko'p holderlar: {:,}".format(holders))
        elif holders >= 1000:
            pts += 6.0
        elif holders >= 500:
            pts += 4.0
        elif holders >= 100:
            pts += 2.0
        else:
            warnings.append("Kam holderlar: {}".format(holders))

        if top10 <= 0.15:
            pts += 7.0; signals.append("Yaxshi taqsimot: top10={:.0f}%".format(top10*100))
        elif top10 <= 0.25:
            pts += 4.0
        elif top10 <= 0.35:
            pts += 2.0
        else:
            warnings.append("Konsentrlashgan: top10={:.0f}%".format(top10*100))

        return "holders", min(pts, max_pts), max_pts, signals, warnings

    def _score_security(self, d: Dict) -> Tuple:
        sec = d.get("security") or {}
        signals, warnings = [], []
        max_pts = 20.0
        pts = 10.0  # boshlang'ich

        if sec.get("is_honeypot") in (True, "true", 1):
            return "security", 0.0, max_pts, [], ["HONEYPOT aniqlandi!"]

        if not sec.get("mint_authority") and not sec.get("is_mintable"):
            pts += 4.0; signals.append("Mint o'chirilgan")
        else:
            pts -= 5.0; warnings.append("Mint authority faol!")

        if not sec.get("freeze_authority") and not sec.get("is_freezable"):
            pts += 3.0; signals.append("Freeze o'chirilgan")
        else:
            pts -= 3.0; warnings.append("Freeze authority faol!")

        if sec.get("lp_locked") or sec.get("is_lp_locked"):
            pts += 3.0; signals.append("LP qulflangan")
        elif settings.REQUIRE_LP_LOCKED:
            pts -= 2.0; warnings.append("LP qulflanmagan")

        return "security", max(0.0, min(pts, max_pts)), max_pts, signals, warnings

    def _score_age(self, d: Dict) -> Tuple:
        age = safe_float(d.get("token_age_minutes"))
        signals, warnings = [], []
        max_pts = 10.0

        if 2 <= age <= 8:
            pts = 10.0; signals.append("Ideal yosh: {:.1f} min".format(age))
        elif 1 <= age < 2 or 8 < age <= 12:
            pts = 7.0
        elif age < 1:
            pts = 3.0; warnings.append("Juda yangi: {:.1f} min".format(age))
        elif 12 < age <= 20:
            pts = 4.0; warnings.append("Biroz eski: {:.1f} min".format(age))
        else:
            pts = 1.0; warnings.append("Eski token: {:.1f} min".format(age))

        return "age", pts, max_pts, signals, warnings

    def _score_buy_sell(self, d: Dict) -> Tuple:
        bsr = safe_float(d.get("buy_sell_ratio"), 1.0)
        signals, warnings = [], []
        max_pts = 10.0

        if bsr >= 5.0:
            pts = 10.0; signals.append("Kuchli xarid bosimi: {:.1f}x".format(bsr))
        elif bsr >= 3.0:
            pts = 8.0; signals.append("Yaxshi xarid bosimi: {:.1f}x".format(bsr))
        elif bsr >= 2.0:
            pts = 6.0
        elif bsr >= 1.5:
            pts = 4.0
        elif bsr >= 1.0:
            pts = 2.0
        else:
            pts = 0.0; warnings.append("Sotuv bosimi ustun: {:.1f}x".format(bsr))

        return "buy_sell", pts, max_pts, signals, warnings
