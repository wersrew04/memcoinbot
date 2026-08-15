"""Whale Tracking – detect large buys/sells/transfers and feed AI score."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from utils.logger import logger
from utils.helpers import safe_float, utc_now
from config.settings import settings


@dataclass
class WhaleEvent:
    token: str
    wallet: str
    event_type: str  # buy | sell | transfer | accumulation | distribution
    amount_usd: float
    tier: str  # 100k+ | 250k+ | ...
    ts: str = field(default_factory=lambda: utc_now().isoformat())


class WhaleMonitor:
    def __init__(self):
        self.thresholds = sorted(settings.whale_thresholds_list())
        self.events: List[WhaleEvent] = []
        self._token_net: Dict[str, float] = defaultdict(float)  # net USD flow
        self._token_buy_count: Dict[str, int] = defaultdict(int)
        self._token_sell_count: Dict[str, int] = defaultdict(int)

    def _tier(self, amount_usd: float) -> Optional[str]:
        for t in reversed(self.thresholds):
            if amount_usd >= t:
                return f"{int(t/1000)}k+"
        return None

    def record_event(
        self,
        token: str,
        wallet: str,
        event_type: str,
        amount_usd: float,
    ) -> Optional[WhaleEvent]:
        if not settings.WHALE_TRACKING_ENABLED:
            return None
        tier = self._tier(amount_usd)
        if not tier:
            return None

        ev = WhaleEvent(
            token=token,
            wallet=wallet,
            event_type=event_type,
            amount_usd=amount_usd,
            tier=tier,
        )
        self.events.append(ev)
        # keep last 5000
        if len(self.events) > 5000:
            self.events = self.events[-5000:]

        if event_type in ("buy", "accumulation"):
            self._token_net[token] += amount_usd
            self._token_buy_count[token] += 1
        elif event_type in ("sell", "distribution"):
            self._token_net[token] -= amount_usd
            self._token_sell_count[token] += 1

        logger.info(
            f"Whale {event_type.upper()} {tier} ${amount_usd:,.0f} | "
            f"{token[:8]}... by {wallet[:8]}..."
        )
        return ev

    def get_activity_score(self, token: str) -> float:
        """0–1 for AI: net positive flow + buy dominance → high."""
        if not settings.WHALE_TRACKING_ENABLED:
            return 0.5
        net = self._token_net.get(token, 0.0)
        buys = self._token_buy_count.get(token, 0)
        sells = self._token_sell_count.get(token, 0)
        total = buys + sells
        if total == 0:
            return 0.5
        buy_ratio = buys / total
        net_score = 0.5
        if net > 50_000:
            net_score = 0.9
        elif net > 0:
            net_score = 0.7
        elif net < -50_000:
            net_score = 0.15
        elif net < 0:
            net_score = 0.35
        return max(0.0, min(1.0, 0.5 * buy_ratio + 0.5 * net_score))

    def score_delta(self, token: str) -> float:
        """Points to add/subtract from AI score."""
        score = self.get_activity_score(token)
        if score >= 0.8:
            return settings.WHALE_BUY_SCORE_BOOST
        if score <= 0.3:
            return -settings.WHALE_SELL_SCORE_PENALTY
        return 0.0

    def recent_events(self, token: Optional[str] = None, limit: int = 20) -> List[WhaleEvent]:
        evs = self.events if not token else [e for e in self.events if e.token == token]
        return evs[-limit:]
