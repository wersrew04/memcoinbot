"""Barcha filterlarni ketma-ket ishga tushirish + AI / Blacklist integratsiyasi."""
from __future__ import annotations

from typing import Dict, Any, List, Tuple, Callable, Optional
from utils.logger import logger

from filters.liquidity import check_liquidity
from filters.volume import (
    check_volume_24h,
    check_volume_5m,
    check_buy_sell_ratio,
    check_volume_spike,
)
from filters.holders import check_holder_count, check_top10_holders, check_dev_wallet
from filters.security import (
    check_mint_authority,
    check_freeze_authority,
    check_honeypot,
    check_market_cap,
    check_lp_locked,
)
from filters.age import check_token_age
from config.settings import settings
from utils.history import history


class FilterPipeline:
    def __init__(
        self,
        blacklist=None,
        ai_scorer=None,
        smart_money=None,
        whale_monitor=None,
        social=None,
    ):
        self.blacklist = blacklist
        self.ai_scorer = ai_scorer
        self.smart_money = smart_money
        self.whale_monitor = whale_monitor
        self.social = social

        # Tartib: arzon → qimmat; jadvaldagi barcha mezonlar
        self.filters: List[Callable[[Dict[str, Any]], Tuple[bool, str]]] = [
            check_token_age,          # 1–15 daqiqa
            check_liquidity,          # $20K+
            check_volume_5m,          # 5m volume $20K+
            check_buy_sell_ratio,     # Buy/Sell ≥ 2:1
            check_volume_24h,         # ixtiyoriy (default off)
            check_market_cap,         # $50K–500K
            check_holder_count,       # 100+
            check_top10_holders,      # < 30%
            check_dev_wallet,
            check_mint_authority,     # disabled
            check_freeze_authority,   # disabled
            check_honeypot,           # yo'q
            check_lp_locked,          # locked/burned
            check_volume_spike,
        ]

    async def run(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Barcha filterlardan o'tkazadi + blacklist + AI score.
        Returns: (passed: bool, reasons: list[str])
        """
        reasons: List[str] = []
        token = data.get("token_address") or data.get("address") or ""

        # 0) Blacklist
        symbol = data.get("token_symbol") or data.get("symbol") or token[:8]

        if self.blacklist:
            if self.blacklist.is_blacklisted(token):
                entry = self.blacklist.get_entry(token) or {}
                reasons = [f"Blacklisted: {entry.get('reason', 'unknown')}"]
                history.add_rejection(token, symbol, reasons, stage="blacklist")
                return False, reasons
            auto_reason = self.blacklist.auto_check(data)
            if auto_reason:
                reasons = [f"Auto-blacklist: {auto_reason}"]
                history.add_rejection(token, symbol, reasons, stage="blacklist")
                return False, reasons

        # 1) Classic filters
        for filt in self.filters:
            try:
                ok, msg = filt(data)
                reasons.append(msg)
                if not ok:
                    history.add_rejection(token, symbol, reasons, stage=filt.__name__)
                    return False, reasons
            except Exception as e:
                logger.error(f"Filter {filt.__name__} xato: {e}")
                reasons.append(f"{filt.__name__} exception: {e}")
                return False, reasons

        # 2) Enrich with Smart Money / Whale / Social scores for AI
        if self.smart_money and token:
            data["smart_money_score"] = self.smart_money.get_smart_money_score(token)
        if self.whale_monitor and token:
            data["whale_activity_score"] = self.whale_monitor.get_activity_score(token)
        if self.social and token:
            try:
                data["social_score"] = await self.social.get_social_score(token, symbol)
            except Exception as e:
                logger.debug(f"Social Intelligence enrichment xato (o'tkazib yuborildi): {e}")

        # 3) AI Score
        if self.ai_scorer and settings.AI_ENABLED:
            try:
                result = self.ai_scorer.score(data)
                data["ai_score"] = result.score
                data["ai_recommendation"] = result.recommendation.value
                data["ai_factors"] = result.factors
                reasons.append(f"AI Score: {result.score:.1f} ({result.recommendation.value})")

                if self.smart_money:
                    boost = self.smart_money.score_boost(token)
                    if boost:
                        result.score = min(100.0, result.score + boost)
                        data["ai_score"] = result.score
                        reasons.append(f"Smart money boost +{boost:.0f}")

                if self.whale_monitor:
                    delta = self.whale_monitor.score_delta(token)
                    if delta:
                        result.score = max(0.0, min(100.0, result.score + delta))
                        data["ai_score"] = result.score
                        reasons.append(f"Whale delta {delta:+.0f}")

                if not self.ai_scorer.passes_threshold(result):
                    history.add_rejection(token, symbol, reasons, stage="ai_score")
                    return False, reasons
            except Exception as e:
                logger.error(f"AI scorer xato: {e}")
                reasons.append(f"AI exception: {e}")
                if settings.AI_MIN_SCORE > 0:
                    return False, reasons

        return True, reasons
