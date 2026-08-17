"""Savdo tarixi va eventlar."""
from __future__ import annotations
import json
from pathlib import Path
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List

Path("data").mkdir(exist_ok=True)
TRADES_FILE = Path("data/trade_history.jsonl")
EVENTS_FILE = Path("data/events.jsonl")


def reset_today_stats():
    """Bugungi statistikani nollash (kunlik reset)."""
    pass  # history singleton orqali boshqariladi


class TradeHistory:
    def __init__(self, maxlen: int = 500):
        self._trades: deque = deque(maxlen=maxlen)
        self._rejections: deque = deque(maxlen=300)
        self._events: deque = deque(maxlen=300)
        self._load()

    def _load(self):
        if TRADES_FILE.exists():
            for line in TRADES_FILE.read_text(encoding="utf-8").splitlines()[-300:]:
                try:
                    self._trades.append(json.loads(line))
                except Exception:
                    pass

    def add_trade(
        self,
        symbol: str,
        token: str,
        pnl_usd: float,
        pnl_pct: float,
        reason: str,
        ai_score: Any = None,
        ai_breakdown: Any = None,
        paper: bool = True,
    ):
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "token": token,
            "pnl_usd": round(pnl_usd, 4),
            "pnl_pct": round(pnl_pct, 2),
            "reason": reason,
            "ai_score": ai_score,
            "ai_breakdown": ai_breakdown,
            "paper": paper,
        }
        self._trades.append(rec)
        try:
            with TRADES_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, default=str) + "\n")
        except Exception:
            pass

    def add_rejection(self, symbol: str, token: str, stage: str, last_reason: str):
        self._rejections.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "token": token,
            "stage": stage,
            "last_reason": last_reason,
        })

    def add_event(self, level: str, message: str):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        }
        self._events.append(entry)
        try:
            with EVENTS_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def list_trades(self, limit: int = 40) -> List[Dict]:
        return list(self._trades)[-limit:][::-1]

    def list_rejections(self, limit: int = 40) -> List[Dict]:
        return list(self._rejections)[-limit:][::-1]

    def list_events(self, limit: int = 40) -> List[Dict]:
        return list(self._events)[-limit:][::-1]

    def pnl_summary(self) -> Dict[str, Any]:
        trades = list(self._trades)
        if not trades:
            return {
                "net_pnl": 0.0, "profit": 0.0, "loss": 0.0,
                "win_rate": 0, "total_trades": 0,
                "best": 0.0, "worst": 0.0,
                "paper_trades": 0, "live_trades": 0,
            }
        pnls = [t.get("pnl_usd", 0) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        paper = sum(1 for t in trades if t.get("paper", True))
        return {
            "net_pnl": round(sum(pnls), 2),
            "profit": round(sum(wins), 2),
            "loss": round(abs(sum(losses)), 2),
            "win_rate": round(len(wins) / len(pnls) * 100, 1) if pnls else 0,
            "total_trades": len(pnls),
            "best": round(max(pnls), 2) if pnls else 0,
            "worst": round(min(pnls), 2) if pnls else 0,
            "paper_trades": paper,
            "live_trades": len(trades) - paper,
        }

    def clear_trades(self):
        self._trades.clear()
        try:
            TRADES_FILE.write_text("", encoding="utf-8")
        except Exception:
            pass


history = TradeHistory()
