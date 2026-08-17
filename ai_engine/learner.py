"""
Trade Learner — savdo natijalaridan o'rganish.
AI og'irliklarini muvaffaqiyatli/muvaffaqiyatsiz savdolarga qarab moslashtiradi.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List
from utils.logger import logger
from config.settings import settings

WEIGHTS_FILE = Path("data/ai_weights.json")

DEFAULT_WEIGHTS = {
    "liquidity": 0.20,
    "volume":    0.18,
    "momentum":  0.15,
    "holders":   0.15,
    "security":  0.15,
    "age":       0.08,
    "buy_sell":  0.09,
}


class TradeLearner:
    def __init__(self):
        self.weights: Dict[str, float] = dict(DEFAULT_WEIGHTS)
        self._history: List[Dict] = []
        self._load()

    def _load(self):
        if WEIGHTS_FILE.exists():
            try:
                data = json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
                self.weights = data.get("weights", DEFAULT_WEIGHTS)
                self._history = data.get("history", [])
                logger.info("AI og'irliklari yuklandi: {}".format(
                    {k: round(v, 3) for k, v in self.weights.items()}
                ))
            except Exception as e:
                logger.warning("AI og'irlik yuklash xato: {}".format(e))

    def _save(self):
        try:
            WEIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            WEIGHTS_FILE.write_text(
                json.dumps({"weights": self.weights, "history": self._history[-200:]},
                           indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.warning("AI og'irlik saqlash xato: {}".format(e))

    def record_trade(
        self,
        symbol: str,
        token: str,
        pnl_pct: float,
        score_breakdown: Dict[str, float],
        reason: str,
    ):
        """Savdo natijasini qayd etish va og'irliklarni yangilash."""
        if not score_breakdown:
            return

        win = pnl_pct > 0
        magnitude = min(abs(pnl_pct) / 100, 1.0)   # 0–1 oralig'ida
        lr = settings.AI_LEARNING_RATE * magnitude

        for factor, score_val in score_breakdown.items():
            if factor not in self.weights:
                continue
            if win:
                # Yuqori score bergan faktorni ko'tarish
                self.weights[factor] += lr * (score_val / 20.0)
            else:
                # Past score bergan faktorni tushirish
                self.weights[factor] -= lr * (1 - score_val / 20.0)

        # Normalizatsiya: yig'indi = 1.0
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: max(0.01, v / total) for k, v in self.weights.items()}

        # Qayd
        self._history.append({
            "symbol": symbol,
            "token": token[:8],
            "pnl_pct": round(pnl_pct, 2),
            "win": win,
            "reason": reason,
            "weights_after": {k: round(v, 4) for k, v in self.weights.items()},
        })

        self._save()
        logger.info("[LEARNER] {} {} pnl={:+.1f}% og'irliklar yangilandi".format(
            "WIN" if win else "LOSS", symbol, pnl_pct
        ))

    def get_weights(self) -> Dict[str, float]:
        return dict(self.weights)

    def reset_weights(self):
        self.weights = dict(DEFAULT_WEIGHTS)
        self._save()
        logger.info("AI og'irliklari default ga qaytarildi")

    def get_performance_summary(self) -> Dict[str, Any]:
        if not self._history:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0}
        wins = [h for h in self._history if h.get("win")]
        return {
            "total": len(self._history),
            "wins": len(wins),
            "losses": len(self._history) - len(wins),
            "win_rate": round(len(wins) / len(self._history) * 100, 1),
            "weights": self.weights,
        }
