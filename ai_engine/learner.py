"""Trade outcome learner – updates AI weights from closed trades (simple online learning)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from utils.logger import logger
from utils.helpers import utc_now, safe_float
from config.settings import settings

WEIGHTS_PATH = Path("data/ai_weights.json")
TRADES_PATH = Path("data/ai_trade_history.jsonl")


class TradeLearner:
    """
    Stores closed trade features + PnL and adjusts scorer weights.
    Production: replace with proper model retrain (e.g. sklearn / lightgbm).
    """

    def __init__(self):
        WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.weights: Dict[str, float] = self._load_weights()

    def _load_weights(self) -> Dict[str, float]:
        if WEIGHTS_PATH.exists():
            try:
                return json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"AI weights load failed: {e}")
        return {
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

    def _save_weights(self):
        try:
            WEIGHTS_PATH.write_text(json.dumps(self.weights, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"AI weights save failed: {e}")

    def record_trade(
        self,
        token: str,
        factors: Dict[str, float],
        score: float,
        pnl_usd: float,
        pnl_pct: float,
        reason: str,
    ):
        """Append trade outcome for learning."""
        record = {
            "ts": utc_now().isoformat(),
            "token": token,
            "factors": factors,
            "score": score,
            "pnl_usd": pnl_usd,
            "pnl_pct": pnl_pct,
            "reason": reason,
        }
        try:
            with TRADES_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as e:
            logger.error(f"Trade history write failed: {e}")

        self._update_weights(factors, pnl_pct)

    def _update_weights(self, factors: Dict[str, float], pnl_pct: float):
        """Very simple online update: boost factors present on wins, dampen on losses."""
        lr = settings.AI_LEARNING_RATE
        if abs(pnl_pct) < 1.0:
            return
        direction = 1.0 if pnl_pct > 0 else -1.0
        for k, v in factors.items():
            if k not in self.weights:
                continue
            # move weight slightly toward successful factor magnitude
            delta = lr * direction * (v - 0.5)
            self.weights[k] = max(0.01, min(0.4, self.weights[k] + delta))
        # renormalize
        total = sum(self.weights.values()) or 1.0
        self.weights = {k: v / total for k, v in self.weights.items()}
        self._save_weights()
        logger.info(f"AI weights updated after trade (PnL {pnl_pct:+.1f}%)")

    def get_weights(self) -> Dict[str, float]:
        return dict(self.weights)
