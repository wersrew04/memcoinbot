"""Smart Money Copy Trading – track high-performance wallets and boost AI score."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from utils.logger import logger
from utils.helpers import safe_float, utc_now
from config.settings import settings

DB_PATH = Path("data/smart_wallets.json")


class SmartMoneyTracker:
    """
    Maintains a database of smart wallets with performance metrics.
    When multiple smart wallets buy the same token, AI score is boosted.
    """

    def __init__(self):
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.wallets: Dict[str, Dict[str, Any]] = self._load()
        self._token_buyers: Dict[str, Set[str]] = {}  # token -> set of smart wallets

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if DB_PATH.exists():
            try:
                return json.loads(DB_PATH.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Smart wallet DB load failed: {e}")
        return {}

    def _save(self):
        try:
            DB_PATH.write_text(json.dumps(self.wallets, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Smart wallet DB save failed: {e}")

    def add_or_update_wallet(
        self,
        address: str,
        win_rate: float,
        avg_roi_pct: float,
        total_trades: int,
        avg_hold_minutes: float = 0.0,
        label: str = "",
    ):
        self.wallets[address] = {
            "address": address,
            "win_rate": win_rate,
            "avg_roi_pct": avg_roi_pct,
            "total_trades": total_trades,
            "avg_hold_minutes": avg_hold_minutes,
            "label": label,
            "rating": self._compute_rating(win_rate, avg_roi_pct, total_trades),
            "updated_at": utc_now().isoformat(),
        }
        self._save()

    def _compute_rating(self, win_rate: float, avg_roi: float, trades: int) -> float:
        """0–100 rating."""
        if trades < settings.SMART_MONEY_MIN_TRADES:
            return 0.0
        wr = min(1.0, max(0.0, win_rate))
        roi = min(10.0, max(0.0, avg_roi / 100.0))  # normalize ~1000% → 10
        t = min(1.0, trades / 500.0)
        return round((0.4 * wr + 0.4 * (roi / 10) + 0.2 * t) * 100, 1)

    def is_qualified(self, address: str) -> bool:
        w = self.wallets.get(address)
        if not w:
            return False
        return (
            w.get("avg_roi_pct", 0) >= settings.SMART_MONEY_MIN_ROI_PCT
            and w.get("win_rate", 0) >= settings.SMART_MONEY_MIN_WIN_RATE
            and w.get("total_trades", 0) >= settings.SMART_MONEY_MIN_TRADES
        )

    def qualified_wallets(self) -> List[Dict[str, Any]]:
        return [w for a, w in self.wallets.items() if self.is_qualified(a)]

    def record_buy(self, token: str, wallet: str):
        if not self.is_qualified(wallet):
            return
        self._token_buyers.setdefault(token, set()).add(wallet)
        logger.info(f"Smart money buy: {wallet[:8]}... → {token[:8]}...")

    def get_smart_money_score(self, token: str) -> float:
        """0–1 score based on how many qualified wallets bought this token."""
        if not settings.SMART_MONEY_ENABLED:
            return 0.5
        buyers = self._token_buyers.get(token, set())
        n = len(buyers)
        if n == 0:
            return 0.4
        if n == 1:
            return 0.65
        if n >= 3:
            return 1.0
        return 0.85

    def score_boost(self, token: str) -> float:
        """Extra points to add to AI score (0–boost)."""
        n = len(self._token_buyers.get(token, set()))
        if n >= 2:
            return settings.SMART_MONEY_SCORE_BOOST
        if n == 1:
            return settings.SMART_MONEY_SCORE_BOOST * 0.4
        return 0.0
